#!/usr/bin/env python3
"""Lokalni simulator progtestu.

Pouziti:  python3 progtester/progtest.py projekt [volby]
"""

import argparse
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pt import build, gen
from pt.checks import FAIL, WARN, Oracle, diff, evaluate
from pt.runner import run

TESTER_DIR = Path(__file__).resolve().parent
USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def badge(level):
    return {"OK": c(" OK ", "1;32"), WARN: c("WARN", "1;33"), FAIL: c("FAIL", "1;31")}[level]


def show_bytes(b: bytes, limit=300) -> str:
    s = repr(b[:limit])[2:-1]
    return s + (f"... (+{len(b) - limit} B)" if len(b) > limit else "")


def parse_args():
    ap = argparse.ArgumentParser(description="Lokalni simulator progtestu - snazi se program rozbit.")
    ap.add_argument("task", help="slozka ulohy (napr. 01_citaty) nebo primo zdrojak")
    ap.add_argument("--src", help="konkretni zdrojak, kdyz jich je ve slozce vic")
    ap.add_argument("--lang", choices=["CZE", "ENG", "all"], default="CZE",
                    help="jazyk vzorovych dat (default CZE)")
    ap.add_argument("--timeout", type=float, default=1.0, help="limit na jeden beh v s (default 1)")
    ap.add_argument("--mem", type=int, default=256, help="limit pameti v MB pro -O2 build (default 256)")
    ap.add_argument("--fuzz", type=int, default=200, help="pocet nahodnych testu (default 200)")
    ap.add_argument("--seed", type=int, default=1, help="seed pro fuzz (default 1)")
    ap.add_argument("--no-asan", action="store_true", help="nespoustet ASan/UBSan build")
    ap.add_argument("--no-big", action="store_true", help="vynechat velke vstupy")
    ap.add_argument("--only-samples", action="store_true", help="jen vzorova data")
    ap.add_argument("--cc", choices=["g++", "gcc"], default="g++",
                    help="kompilator; progtest pouziva g++ i pro C (default g++)")
    ap.add_argument("--strict", action="store_true", help="kompilovat s -Werror")
    ap.add_argument("--ref", help="referencni binarka - vystupy vsech testu se s ni porovnaji presne")
    ap.add_argument("--show", type=int, default=3, help="kolik detailu vypsat na skupinu (default 3)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2)
    return ap.parse_args()


def compile_all(src: Path, workdir: Path, args):
    print(c(f"== Kompilace {src.name}", "1"))
    rel = build.build_release(src, workdir, args.strict, args.cc)
    print("   " + " ".join(rel.cmd[:-3]) + " -o prog -lm")
    if rel.output:
        print(c("   " + rel.output.replace("\n", "\n   "), "33"))
    if not rel.ok:
        print(badge(FAIL) + " Kompilace selhala - program nelze testovat.")
        sys.exit(2)
    forb = build.forbidden_symbols(rel.binary)
    if forb:
        print(badge(FAIL) + f" Program pouziva zakazane funkce: {', '.join(forb)} - progtest ho nespusti!")
        print("   Tip: obal je do #ifndef __PROGTEST__ ... #endif")
        sys.exit(2)
    elif rel.output:
        print(badge(WARN) + " Prelozeno s varovanimi (progtest je ukaze taky).")
    else:
        print(badge("OK") + " Prelozeno bez varovani.")

    san = None
    if not args.no_asan:
        s = build.build_sanitized(src, workdir, args.cc)
        if s.ok:
            san = s.binary
        else:
            print(badge(WARN) + " ASan/UBSan build se nepovedl, pokracuji bez nej:\n   " + s.output[:400])
    return rel.binary, san


def run_case(case, rel_bin, san_bin, ref_bin, oracle, args):
    rel = run(rel_bin, case.data, args.timeout, args.mem)
    san = (run(san_bin, case.data, args.timeout * 5, None, build.asan_env())
           if san_bin else None)
    ref = run(ref_bin, case.data, args.timeout * 5) if ref_bin else None
    return case, rel, evaluate(case, rel, san, ref, oracle, args.timeout)


def save_failure(outdir: Path, idx: int, case, rel, verdict):
    stem = f"{idx:04d}_{verdict.level.lower()}"
    (outdir / f"{stem}_in.txt").write_bytes(case.data)
    (outdir / f"{stem}_out.txt").write_bytes(rel.stdout)
    info = [f"test:    {case.name}", f"skupina: {case.group}", ""]
    info += [f"[{lvl}] {msg}" for lvl, msg in verdict.issues]
    if case.expected is not None:
        (outdir / f"{stem}_ref.txt").write_bytes(case.expected)
    (outdir / f"{stem}_info.txt").write_text("\n".join(info) + "\n")
    return stem


def report_case(case, rel, verdict, stem):
    print(f"   {badge(verdict.level)} {case.name}")
    print(f"        vstup:  {show_bytes(case.data)}")
    print(f"        vystup: {show_bytes(rel.stdout)}")
    for lvl, msg in verdict.issues:
        col = "31" if lvl == FAIL else "33"
        print(c("        - " + msg.replace("\n", "\n          "), col))
    if case.expected is not None and rel.stdout != case.expected and not (rel.timed_out or rel.signal_name):
        print("          " + diff(case.expected, rel.stdout).replace("\n", "\n          "))
    print(c(f"        ulozeno: {stem}_*.txt", "2"))


def main():
    args = parse_args()
    task = Path(args.task).resolve()
    task_dir = task if task.is_dir() else task.parent
    src = build.find_source(task, args.src)

    samples = gen.load_samples(task_dir, args.lang)
    if not samples:
        print(c(f"Varovani: v {task_dir} nejsou zadna vzorova data (sample/**/*_in.txt).", "33"))
    oracle = Oracle.from_outputs([s.expected for s in samples])
    cases = samples if args.only_samples else samples + gen.generate(
        samples, args.fuzz, args.seed, not args.no_big)

    outdir = TESTER_DIR / "vysledky" / task_dir.name
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="progtest_") as wd:
        rel_bin, san_bin = compile_all(src, Path(wd), args)
        ref_bin = Path(args.ref).resolve() if args.ref else None
        print(c(f"\n== Testovani: {len(cases)} vstupu "
                f"({'s ASan/UBSan' if san_bin else 'bez sanitizeru'}, limit {args.timeout:g} s)", "1"))
        with ThreadPoolExecutor(args.jobs) as ex:
            results = list(ex.map(lambda k: run_case(k, rel_bin, san_bin, ref_bin, oracle, args), cases))

    totals = {"OK": 0, WARN: 0, FAIL: 0}
    idx = 0
    for group in gen.GROUPS:
        res = [r for r in results if r[0].group == group]
        if not res:
            continue
        counts = {lv: sum(v.level == lv for _, _, v in res) for lv in totals}
        for lv in totals:
            totals[lv] += counts[lv]
        worst = FAIL if counts[FAIL] else WARN if counts[WARN] else "OK"
        print(f"\n{badge(worst)} {c(group, '1')}: {counts['OK']}/{len(res)} OK"
              + (f", {counts[WARN]} varovani" if counts[WARN] else "")
              + (f", {counts[FAIL]} chyb" if counts[FAIL] else ""))
        shown = 0
        for case, rel, verdict in sorted(res, key=lambda r: r[2].level != FAIL):
            if verdict.level == "OK":
                continue
            idx += 1
            stem = save_failure(outdir, idx, case, rel, verdict)
            if shown < args.show:
                report_case(case, rel, verdict, stem)
                shown += 1
        if shown < counts[FAIL] + counts[WARN]:
            print(c(f"   ... a dalsich {counts[FAIL] + counts[WARN] - shown} (viz --show N nebo slozka vysledky)", "2"))

    print(c("\n== Shrnuti", "1"))
    print(f"   {totals['OK']} OK, {totals[WARN]} varovani, {totals[FAIL]} chyb z {len(results)} testu")
    if idx:
        print(f"   Problemove vstupy ulozeny v {outdir.relative_to(TESTER_DIR.parent)}/")
    sys.exit(1 if totals[FAIL] else 0)


if __name__ == "__main__":
    main()
