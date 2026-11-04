#!/usr/bin/env python3
"""Lokalni simulator progtestu.

Pouziti:  python3 progtester/progtest.py projekt [volby]
"""

import argparse
import os
import random
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pt import build, complexity, gen, style
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
    ap.add_argument("--suite", action="append",
                    help="jen vybrane sady vzorovych dat (basic, extra, bonus, tests); lze opakovat")
    ap.add_argument("--valgrind", nargs="?", type=int, const=300, default=0, metavar="N",
                    help="spustit pod valgrindem vzorova data + mensi generovane vstupy, celkem "
                         "nejvyse N (default 300); pozna neinicializovane promenne, ktere ASan nevidi")
    ap.add_argument("--complexity", metavar="SOUBOR",
                    help="vlastni generator vstupu pro odhad slozitosti misto automatiky "
                         "(default <uloha>/complexity.py, pokud existuje)")
    ap.add_argument("--complexity-max", type=int, default=6, metavar="N",
                    help="kolik zpusobu zvetseni vstupu, ktere program zpomaluji, zmerit presne (default 6)")
    ap.add_argument("--no-complexity", action="store_true", help="nedelat odhad slozitosti")
    ap.add_argument("--only-complexity", action="store_true", help="jen odhad slozitosti")
    ap.add_argument("--no-style", action="store_true", help="nekontrolovat stabni kulturu kodu")
    ap.add_argument("--only-style", action="store_true", help="jen kompilace a stabni kultura kodu")
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
    if not args.no_asan and not args.only_complexity and not args.only_style:
        s = build.build_sanitized(src, workdir, args.cc)
        if s.ok:
            san = s.binary
        else:
            print(badge(WARN) + " ASan/UBSan build se nepovedl, pokracuji bez nej:\n   " + s.output[:400])

    dbg = None
    if args.valgrind and not args.only_complexity and not args.only_style:
        if not shutil.which("valgrind"):
            print(badge(WARN) + " valgrind neni nainstalovany (apt install valgrind), --valgrind se preskakuje.")
        else:
            d = build.build_debug(src, workdir, args.cc)
            if d.ok:
                dbg = d.binary
            else:
                print(badge(WARN) + " build pro valgrind se nepovedl:\n   " + d.output[:400])
    return rel.binary, san, dbg


def pick_valgrind(cases, limit: int, seed: int) -> set:
    """Vzorova data vzdy, k tomu nahodny vyber mensich generovanych vstupu (valgrind je ~50x pomalejsi)."""
    chosen = [i for i, k in enumerate(cases) if k.suite]
    rest = [i for i, k in enumerate(cases) if not k.suite and len(k.data) <= 4096]
    random.Random(seed).shuffle(rest)
    return set(chosen[:limit] + rest[:max(0, limit - len(chosen))])


def run_valgrind(dbg_bin, data: bytes, timeout: float) -> str:
    with tempfile.TemporaryDirectory(prefix="pt_vg_") as td:
        log = Path(td) / "vg.log"
        run(build.valgrind_cmd(dbg_bin, log), data, max(timeout * 50, 20))
        # pri timeoutu muze byt hlaseni neuplne, ale co v nem je, plati
        return log.read_text(errors="replace") if log.exists() else ""


def run_case(case, rel_bin, san_bin, dbg_bin, ref_bin, oracle, args):
    rel = run(rel_bin, case.data, args.timeout, args.mem)
    san = (run(san_bin, case.data, args.timeout * 5, None, build.asan_env())
           if san_bin else None)
    ref = run(ref_bin, case.data, args.timeout * 5) if ref_bin else None
    ctrl = run(rel_bin, case.control, args.timeout, args.mem) if case.control is not None else None
    vg = run_valgrind(dbg_bin, case.data, args.timeout) if dbg_bin else None
    return case, rel, evaluate(case, rel, san, ref, oracle, args.timeout, ctrl, vg)


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


def print_knob(k, limit):
    pts = k.points
    if len(pts) > 8:  # tabulka jen s nekolika radky, posledni bod vzdy
        step = (len(pts) - 1) / 7
        pts = [pts[round(i * step)] for i in range(8)]
    print(c(f"   {'n':>14}  {'CPU cas':>10}  {'vstup':>9}", "2"))
    for pt in pts:
        print(f"   {complexity.fmt_n(pt.n):>14}  {complexity.fmt_time(pt.time):>10}  "
              f"{pt.in_bytes / 1024:>6.0f} kB")
    if k.warning:
        print(f"   {badge(WARN)} {k.warning}")
    f = k.fit
    if f is not None:
        alts = f" (nebo {', '.join('O(' + a + ')' for a in f.alts)})" if f.alts else ""
        exp = f", lokalni exponent n^{f.exponent:.2f}" if f.exponent is not None else ""
        print(f"   -> {'cas se s n skoro nemeni' if f.flat else f'namereno O({f.cls}){alts}'}{exp}")
    if k.bound is not None:
        print(f"   -> program prijima n az {complexity.fmt_n(k.bound)}"
              + (f", dal vypise chybu" if k.stop == "invalid" else f", pro {complexity.fmt_n(k.stop_n)} spadne"))
    if k.predicted is not None:
        bound = k.n_max if k.kind == "spec" else k.bound
        how = "namereno" if k.points[-1].n >= bound else "odhad"
        col = "32" if k.predicted <= limit else "31"
        print(f"   -> {how} pro n = {complexity.fmt_n(bound)}: "
              + c(complexity.fmt_time(k.predicted), col) + f" (limit {limit:g} s)")
    if k.limit_n is not None:
        print(f"   -> limit {limit:g} s by se prekrocil od n ~ {complexity.fmt_n(k.limit_n)}")
    if k.grade is not None:
        col = "1;32" if k.grade <= 2 else "1;33" if k.grade == 3 else "1;31"
        print("   -> " + c(f"znamka {k.grade}", col) + f": {k.verdict}")


def run_complexity(rel_bin, samples, spec_path: Path | None, args, outdir: Path):
    """Vraci znamky zmerenych zpusobu zvetseni vstupu."""
    if spec_path:
        limit, knobs = complexity.load_spec(spec_path)
        limit = float(limit or args.timeout)
        print(c(f"\n== Odhad casove slozitosti (vlastni generator {spec_path.name}, limit {limit:g} s)", "1"))
        selected, same = knobs, {}
    else:
        limit = args.timeout
        knobs = complexity.discover(samples, rel_bin, args.mem, args.timeout)
        print(c(f"\n== Odhad casove slozitosti (limit {limit:g} s)", "1"))
        if not knobs:
            print(f"   {badge(WARN)} zadny vzorovy vstup bez chybove hlasky - neni z ceho vychazet")
            return []
        print(f"   Zkousim {len(knobs)} zpusobu, jak zvetsit vzorove vstupy (opakovani radku/prvku, "
              f"vetsi cisla)...", flush=True)
        cap = max(limit, 0.5)
        # predbezne mereni: paralelne, hrubsi krok a nizsi strop - jen vybira, co merit presne
        with ThreadPoolExecutor(args.jobs) as ex:
            list(ex.map(lambda k: complexity.ramp(k, rel_bin, cap / 2, args.mem, step=4,
                                                    max_input=complexity.MAX_INPUT_SCREEN), knobs))
        accepted = [k for k in knobs if len(k.points) >= 2]  # prijal aspon jeden zvetseny vstup
        growing = [k for k in accepted if complexity.grows(k)]

        growing.sort(key=complexity.rank, reverse=True)
        # zpusoby se stejnym zaverem (opakovani / hodnota cisla, stejna slozitost) merime jen jednou
        groups = {}
        for k in growing:
            groups.setdefault(complexity.group_key(k), []).append(k)
        selected = [g[0] for g in groups.values()][:args.complexity_max]
        same = {id(g[0]): len(g) - 1 for g in groups.values()}
        print(f"   Zvetseny vstup program prijal u {len(accepted)} z nich, meritelne ho zpomaluje {len(growing)}"
              + (f" - presne merim {len(selected)} nejhorsich" if growing else
                 " - cas na velikosti vstupu skoro nezavisi") + ".")
        if selected:
            print(c("   Presne mereni bezi postupne (bez paralelniho behu), aby casy nezkreslovala zatez.", "2"))

        crashes = [k for k in accepted if k.stop == "crash"]
        for i, k in enumerate(crashes[:2], 1):
            complexity.find_bound(k, rel_bin, cap, args.mem)
            data = k.build(k.stop_n)
            saved = ""
            if len(data) <= 16 * 2 ** 20:
                (outdir / f"slozitost_pad_{i}_in.txt").write_bytes(data)
                saved = f" -> ulozeno slozitost_pad_{i}_in.txt"
            why = ""
            if args.mem and not run(rel_bin, data, cap * 4 + 1).signal_name:
                why = (f" - jen s limitem pameti {args.mem} MB: potrebuje moc pameti, "
                       f"nebo nekontroluje NULL z malloc/realloc")
            print(f"   {badge(WARN)} program spadl ({k.crash}) pro n = {complexity.fmt_n(k.stop_n)}{why}\n"
                  f"        {k.desc}{saved}")
        if len(crashes) > 2:
            print(c(f"        ... a pri {len(crashes) - 2} dalsich zpusobech zvetseni taky", "2"))

    grades = []
    cap = max(limit, 0.5)
    if not spec_path and not selected and accepted:
        print("   -> " + c("znamka 1", "1;32") + ": cas na velikosti vstupu nezavisi")
        grades.append(1)
    for k in selected:
        print(f"\n   {c(k.desc, '1')}" + (f"  (idealne O({k.ideal}))" if k.ideal else ""), flush=True)
        complexity.ramp(k, rel_bin, cap, args.mem, reps=3)
        complexity.find_bound(k, rel_bin, cap, args.mem)
        complexity.evaluate(k, limit)
        print_knob(k, limit)
        if same.get(id(k)):
            print(c(f"   (podobne se chova jeste {same[id(k)]} dalsich zpusobu zvetseni)", "2"))
        if k.grade is not None:
            grades.append(k.grade)
    return grades


def find_complexity(task_dir: Path, args) -> Path | None:
    """Vlastni generator vstupu, pokud je; jinak None = automatika ze vzorovych dat."""
    if args.complexity:
        p = Path(args.complexity).resolve()
        if not p.is_file():
            raise SystemExit(f"Soubor {p} neexistuje.")
        return p
    p = task_dir / "complexity.py"
    return p if p.is_file() else None


def _val(v, limits) -> str:
    """Hodnota v tabulce funkci, obarvena podle limitu (varovani, hodne spatne)."""
    text = str(v)
    if v > limits[1]:
        return c(text, "1;31")
    return c(text, "33") if v > limits[0] else text


def run_style(src: Path, args):
    cxx = args.cc == "g++" or src.suffix.lower() in (".cpp", ".cc", ".cxx")
    rep = style.check(src, cxx)
    tools = f"; navic {', '.join(rep.tools)}" if rep.tools else ""
    print(c(f"\n== Stabni kultura kodu: {src.name} ({rep.code_lines} radku kodu, "
            f"{len(rep.functions)} funkci{tools})", "1"))
    funcs = rep.functions
    flagged = [f for f in funcs if f.lines > style.FUNC_LINES[0] or f.cyclomatic > style.CYCLOMATIC[0]
               or f.nesting > style.NESTING[0] or f.params > style.PARAMS]
    shown = funcs if len(funcs) <= 20 else flagged
    if shown:
        w = max(len("funkce"), *(len(f.name) for f in shown))
        print(c(f"   {'funkce':<{w}}  {'radku':>5}  {'vetveni':>7}  {'zanoreni':>8}  {'param':>5}  komentar", "2"))
        for f in shown:
            # zarovnani rucne - barvy pridavaji neviditelne znaky
            cells = [(_val(f.lines, style.FUNC_LINES), len(str(f.lines)), 5),
                     (_val(f.cyclomatic, style.CYCLOMATIC), len(str(f.cyclomatic)), 7),
                     (_val(f.nesting, style.NESTING), len(str(f.nesting)), 8),
                     (_val(f.params, (style.PARAMS, 99)), len(str(f.params)), 5)]
            row = "  ".join(" " * (width - ln) + txt for txt, ln, width in cells)
            print(f"   {f.name:<{w}}  {row}  {'ano' if f.commented else '-'}")
        if len(shown) < len(funcs):
            print(c(f"   ... a {len(funcs) - len(shown)} dalsich funkci bez nalezu", "2"))
        print(c(f"   (limity: radku {style.FUNC_LINES[0]}, vetveni {style.CYCLOMATIC[0]}, zanoreni "
                f"{style.NESTING[0]}, parametru {style.PARAMS})", "2"))

    def where(fd):
        return f"r. {fd.line}: " if fd.line else ""

    if rep.bugs:
        print(f"\n   {c('Pravdepodobne chyby (staticka analyza):', '1')}")
        for fd in rep.bugs[:10]:
            print(f"   {badge(WARN)} {where(fd)}{fd.msg}")
        if len(rep.bugs) > 10:
            print(c(f"   ... a dalsich {len(rep.bugs) - 10}", "2"))
    if rep.style:
        print(f"\n   {c('Styl:', '1')}")
        for fd in rep.style[:15]:
            mark = c("!!", "1;31") if fd.weight >= style.MAJOR else c(" -", "33")
            print(f"   {mark} {where(fd)}{fd.msg}")
        if len(rep.style) > 15:
            print(c(f"   ... a dalsich {len(rep.style) - 15}", "2"))
    col = "1;32" if rep.grade <= 2 else "1;33" if rep.grade == 3 else "1;31"
    print(f"\n   -> " + c(f"znamka {rep.grade}", col) + f": {style.GRADE_TEXT[rep.grade]} "
          f"({rep.points} trestnych bodu, {rep.density:.1f} na 100 radku kodu)")
    if rep.missing_tools:
        print(c(f"   Tip: sudo apt install {' '.join(rep.missing_tools)} - prida dalsi kontroly", "2"))
    return rep


def main():
    args = parse_args()
    task = Path(args.task).resolve()
    task_dir = task if task.is_dir() else task.parent
    src = build.find_source(task, args.src)
    cx_spec = find_complexity(task_dir, args)

    samples = gen.load_samples(task_dir, args.lang)
    if not samples:
        print(c(f"Varovani: v {task_dir} nejsou zadna vzorova data (sample/**/*_in.txt).", "33"))
    oracle = Oracle.from_outputs([s.expected for s in samples])
    if args.suite:
        samples = [s for s in samples if s.suite in args.suite]
        if not samples:
            raise SystemExit(f"Zadna vzorova data v sadach {', '.join(args.suite)}.")
    cases = [] if args.only_complexity or args.only_style else samples if args.only_samples else samples + gen.generate(
        samples, args.fuzz, args.seed, not args.no_big)

    outdir = TESTER_DIR / "vysledky" / task_dir.name
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)

    grades, style_rep = [], None
    with tempfile.TemporaryDirectory(prefix="progtest_") as wd:
        rel_bin, san_bin, dbg_bin = compile_all(src, Path(wd), args)
        if not args.no_style and not args.only_complexity:
            style_rep = run_style(src, args)
        ref_bin = Path(args.ref).resolve() if args.ref else None
        vg_set = pick_valgrind(cases, args.valgrind, args.seed) if dbg_bin else set()
        if cases:
            tools = ["s ASan/UBSan" if san_bin else "bez sanitizeru"]
            if vg_set:
                tools.append(f"{len(vg_set)} pod valgrindem")
            print(c(f"\n== Testovani: {len(cases)} vstupu ({', '.join(tools)}, limit {args.timeout:g} s)", "1"))
            with ThreadPoolExecutor(args.jobs) as ex:
                results = list(ex.map(
                    lambda ik: run_case(ik[1], rel_bin, san_bin, dbg_bin if ik[0] in vg_set else None,
                                        ref_bin, oracle, args), enumerate(cases)))
        else:
            results = []
        report_groups(results, outdir, args)
        if not args.no_complexity and not args.only_samples and not args.only_style:
            grades = run_complexity(rel_bin, samples, cx_spec, args, outdir)

    totals = {lv: sum(v.level == lv for _, _, v in results) for lv in ("OK", WARN, FAIL)}
    print(c("\n== Shrnuti", "1"))
    suites = list(dict.fromkeys(case.group for case, _, _ in results if case.suite))
    for g in suites:
        res = [v for case, _, v in results if case.group == g]
        ok = sum(v.level != FAIL for v in res)
        print(f"   {badge('OK' if ok == len(res) else FAIL)} {g}: {ok}/{len(res)}")
    if results:
        print(f"   {totals['OK']} OK, {totals[WARN]} varovani, {totals[FAIL]} chyb z {len(results)} testu")
    if style_rep:
        print(f"   Stabni kultura kodu: znamka {style_rep.grade}"
              + (f", {len(style_rep.bugs)} pravdepodobnych chyb ze staticke analyzy" if style_rep.bugs else ""))
    if grades:
        print(f"   Odhad slozitosti: znamka {max(grades)}"
              + (f" (nejhorsi z {len(grades)} zmerenych zpusobu zvetseni vstupu)" if len(grades) > 1 else ""))
    if totals[FAIL] + totals[WARN]:
        print(f"   Problemove vstupy ulozeny v {outdir.relative_to(TESTER_DIR.parent)}/")
    sys.exit(1 if totals[FAIL] else 0)


def report_groups(results, outdir: Path, args):
    groups = list(dict.fromkeys(case.group for case, _, _ in results if case.suite)) + gen.GENERATED
    idx = 0
    for group in groups:
        res = [r for r in results if r[0].group == group]
        if not res:
            continue
        counts = {lv: sum(v.level == lv for _, _, v in res) for lv in ("OK", WARN, FAIL)}
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


if __name__ == "__main__":
    main()
