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
from dataclasses import dataclass, field
from pathlib import Path

from pt import build, complexity, gen, harness, report, style
from pt.checks import FAIL, WARN, Oracle, evaluate
from pt.report import badge, c
from pt.runner import run

TESTER_DIR = Path(__file__).resolve().parent


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
    ap.add_argument("--out", metavar="SLOZKA",
                    help="kam ulozit problemove vstupy (default vysledky/<uloha>)")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2)
    return ap.parse_args()


@dataclass
class Compiled:
    rel: Path | None = None          # -O2 binarka (uloha se vstupem/vystupem)
    san: Path | None = None
    dbg: Path | None = None
    function_task: bool = False      # uloha "napis funkci" - testuje se main() ze zadani
    problems: list = field(default_factory=list)  # chyby, kvuli kterym progtest program neprelozi


def compile_all(src: Path, workdir: Path, args) -> Compiled:
    print(c(f"== Kompilace {src.name}", "1"))
    res = Compiled()
    obj = build.compile_object(src, workdir, args.strict, args.cc)
    text = src.read_text(errors="replace")
    if not (obj.ok and build.defines_main(obj.binary)) and harness.has_test_main(text):
        # main() je jen v #ifndef __PROGTEST__ -> uloha "napis funkci"; progtest pred kod
        # vlozi hlavicky ze zadani (obsah ostatnich bloku #ifndef __PROGTEST__)
        hdr = workdir / "progtest_header.h"
        hdr.write_text(harness.progtest_header(text, src.name))
        obj = build.compile_object(src, workdir, args.strict, args.cc, include=hdr)
        res.function_task = not (obj.ok and build.defines_main(obj.binary))
    print("   " + build.display_cmd(obj))
    if res.function_task:
        print(c("   Uloha \"napis funkci\": main() je jen v #ifndef __PROGTEST__ - prekladam jako progtest "
                "(s -D__PROGTEST__, hlavicky ze zadani), testy z main() zvlast.", "2"))
    if obj.output:
        print(c("   " + obj.output.replace("\n", "\n   "), "33"))
    if not obj.ok:
        print(badge(FAIL) + " Kompilace selhala - program nelze testovat.")
        sys.exit(2)

    if res.function_task:
        target = obj.binary
    else:
        rel = build.link(obj, src, args.cc)
        if not rel.ok:
            why = ("program nema funkci main()" if "undefined reference to `main'" in rel.output
                   else rel.output[-600:])
            print(badge(FAIL) + f" Linkovani selhalo: {why}")
            sys.exit(2)
        target = res.rel = rel.binary
    forb = build.forbidden_symbols(target)
    if forb:
        print(badge(FAIL) + f" Program pouziva zakazane funkce: {', '.join(forb)} - progtest ho nespusti!")
        print("   Tip: obal je do #ifndef __PROGTEST__ ... #endif")
        sys.exit(2)
    if res.function_task:
        missing = build.missing_functions(obj.binary, src, args.cc)
        if missing:
            msg = (f"na progtestu nebudou definovane: {', '.join(missing)} - jsou jen v #ifndef "
                   f"__PROGTEST__ (nebo nikde); presun je pred #ifndef __PROGTEST__")
            print(badge(FAIL) + " " + msg)
            res.problems.append(msg)
    if not res.problems:
        print(badge(WARN) + " Prelozeno s varovanimi (progtest je ukaze taky)." if obj.output
              else badge("OK") + " Prelozeno bez varovani.")
    if res.function_task:
        return res

    if not args.no_asan and not args.only_complexity and not args.only_style:
        s = build.build_sanitized(src, workdir, args.cc)
        if s.ok:
            res.san = s.binary
        else:
            print(badge(WARN) + " ASan/UBSan build se nepovedl, pokracuji bez nej:\n   " + s.output[:400])

    if args.valgrind and not args.only_complexity and not args.only_style:
        if not shutil.which("valgrind"):
            print(badge(WARN) + " valgrind neni nainstalovany (apt install valgrind), --valgrind se preskakuje.")
        else:
            d = build.build_debug(src, workdir, args.cc)
            if d.ok:
                res.dbg = d.binary
            else:
                print(badge(WARN) + " build pro valgrind se nepovedl:\n   " + d.output[:400])
    return res


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
        report.print_knob(k, limit)
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


def _assert_run(label, b: build.Build, smart: bool, timeout: float, mem, env_extra: dict, wd: Path,
                vg: bool = False):
    """Spusti testovaci main() a vrati (vysledek behu, AssertLog, log valgrindu)."""
    log = wd / f"asserts_{b.binary.name}.log"
    log.unlink(missing_ok=True)
    env = dict(env_extra)
    env["PT_ASSERT_LOG"] = str(log)
    # vlastni casovac v programu (rekne, u ktereho assertu) vyprsi o chlup driv nez runner
    env["PT_ASSERT_TIMEOUT_MS"] = str(int(timeout * 1000))
    cmd, vg_log = [b.binary], None
    if vg:
        vg_file = wd / "asserts_vg.log"
        cmd = build.valgrind_cmd(b.binary, vg_file)
    r = run(cmd, b"", timeout + 0.5, mem, env)
    if vg and vg_file.exists():
        vg_log = vg_file.read_text(errors="replace")
    text = log.read_text(errors="replace") if log.exists() else ""
    return r, harness.parse_log(text) if smart else harness.parse_glibc(r.stderr), vg_log


@dataclass
class FuncResult:
    passed: int | None = None     # None = main() nedobehl (pad, timeout) nebo se nepocitalo
    total: int | None = None
    failed: int = 0
    broken: list = field(default_factory=list)  # buildy s padem / pametovou chybou / timeoutem
    level: str = "OK"


def _run_args(r, smart, wd):
    label, b, env, timeout, mem, vg = r
    return label, b, smart, timeout, mem, env, wd, vg


def run_function_tests(src: Path, wd: Path, args) -> FuncResult:
    """Uloha "napis funkci": spusti main() s asserty ze zadani (-O2, ASan/UBSan, valgrind)."""
    print(c("\n== Testy z main() v #ifndef __PROGTEST__ (asserty ze zadani)", "1"))
    smart = True
    rel = build.build_test(src, wd, "release", args.cc)
    if not rel.ok:
        plain = build.build_test(src, wd, "release", args.cc, smart=False)
        if not plain.ok:
            print(badge(FAIL) + " testovaci main() nejde prelozit:\n   " + plain.output[:800].replace("\n", "\n   "))
            return FuncResult(broken=["preklad testu"], level=FAIL)
        smart, rel = False, plain
        print(c("   (vyrazy v assertech nejdou rozlozit na hodnoty - pouzivam standardni assert, "
                "ktery skonci u prvniho selhani)", "2"))
    runs = [("-O2", rel, dict(os.environ), args.timeout, args.mem, False)]
    if not args.no_asan:
        san = build.build_test(src, wd, "asan", args.cc, smart)
        if san.ok:
            runs.append(("ASan/UBSan", san, build.asan_env(), args.timeout * 5, None, False))
        else:
            print(badge(WARN) + " ASan/UBSan build se nepovedl:\n   " + san.output[:400])
    if shutil.which("valgrind"):
        dbg = build.build_test(src, wd, "debug", args.cc, smart)
        if dbg.ok:
            runs.append(("valgrind", dbg, dict(os.environ), max(args.timeout * 50, 20), None, True))
    else:
        print(c("   Tip: sudo apt install valgrind - najde i neinicializovane promenne", "2"))

    # -O2 nejdriv: kdyz se zacykli, valgrind (~50x pomalejsi) nema smysl nechat bezet desitky sekund
    first = _assert_run(*_run_args(runs[0], smart, wd))
    if first[0].timed_out or first[1].timeout_at is not None:
        runs = [r if r[0] != "valgrind" else (*r[:3], args.timeout * 5, *r[4:]) for r in runs]
    with ThreadPoolExecutor(max(1, len(runs) - 1)) as ex:
        results = [first] + list(ex.map(lambda r: _assert_run(*_run_args(r, smart, wd)), runs[1:]))

    res, base_fails = FuncResult(), None
    for (label, _, _, timeout, _, _), (r, log, vg_log) in zip(runs, results):
        fails = [(f.line, f.expr) for f in log.failures]
        first = base_fails is None
        v = harness.assess(label, r, log, timeout, sanitized=label.startswith("ASan"), vg_log=vg_log,
                           count_failures=first)
        if first:
            base_fails, res.passed, res.total, res.failed = fails, log.passed, log.total, log.failed
        elif fails != base_fails and log.total is not None and res.total is not None:
            v.add(FAIL, f"[{label}] asserty dopadly jinak nez v -O2 buildu -> nedefinovane chovani "
                        "(neinicializovana promenna, cteni mimo pole, ...)")
        if label == "-O2" and log.total == 0 and not v.issues:
            v.add(WARN, "testovaci main() neobsahuje zadny assert - nic se neoveruje")
        if v.level == "OK":
            stat = ("bez chyb, asserty dopadly stejne jako v -O2" if not first and res.failed
                    else f"vsech {log.total} assertu proslo" if log.total else "bez chyb")
            cpu = f" ({r.cpu:.2f} s CPU)" if label == "-O2" else ""
            print(f"   {badge('OK')} {label}: {stat}{cpu}")
        else:
            for lvl, msg in v.issues:
                print(f"   {badge(lvl)} " + c(msg.replace("\n", "\n        "), "31" if lvl == FAIL else "33"))
        if label == "-O2" and log.failures:
            for f in log.failures[:max(args.show, 10)]:
                print(f"        r. {f.line}: assert({f.expr})")
                if f.detail:
                    print(c(f"               hodnoty: {f.detail}", "33"))
            if log.failed > max(args.show, 10):
                print(c(f"        ... a dalsich {log.failed - max(args.show, 10)}", "2"))
        if any(lv == FAIL and not m.startswith(f"[{label}] selhalo") for lv, m in v.issues):
            res.broken.append(label)
        if v.level == FAIL or (v.level == WARN and res.level == "OK"):
            res.level = v.level
    return res


OUT_MARKER = ".progtester_vysledky"  # slozku s timhle souborem vytvoril tester a smi ji smazat


def prepare_outdir(outdir: Path, own: bool):
    """Vycisti slozku na vysledky. Slozku z --out smaze jen, kdyz je prazdna nebo ji vytvoril
    tester - preklep jako `--out 01_uloha` nesmi smazat reseni."""
    if outdir.exists():
        if not outdir.is_dir():
            raise SystemExit(f"--out {outdir}: neni slozka.")
        if not (own or (outdir / OUT_MARKER).exists() or not any(outdir.iterdir())):
            raise SystemExit(f"Slozka {outdir} uz existuje a nevytvoril ji tester - nemazu ji. "
                             f"Zvol pro --out novou nebo prazdnou slozku.")
        shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / OUT_MARKER).touch()


def main():
    args = parse_args()
    task = Path(args.task).resolve()
    task_dir = task if task.is_dir() else task.parent
    src = build.find_source(task, args.src)
    cx_spec = find_complexity(task_dir, args)

    outdir = Path(args.out).resolve() if args.out else TESTER_DIR / "vysledky" / task_dir.name
    prepare_outdir(outdir, own=not args.out)

    with tempfile.TemporaryDirectory(prefix="progtest_") as wd:
        comp = compile_all(src, Path(wd), args)
        style_rep = None
        if not args.no_style and not args.only_complexity:
            cxx = args.cc == "g++" or src.suffix.lower() in (".cpp", ".cc", ".cxx")
            style_rep = style.check(src, cxx)
            report.print_style(src, style_rep)
        if comp.function_task:
            code = test_function_task(src, Path(wd), comp, style_rep, args)
        else:
            code = test_io_task(src, Path(wd), comp, style_rep, task_dir, cx_spec, outdir, args)
    sys.exit(code)


def test_function_task(src: Path, wd: Path, comp: Compiled, style_rep, args) -> int:
    fr = None
    if not args.only_style and not args.only_complexity:
        fr = run_function_tests(src, wd, args)
        print(c("   (vzorova data, generovane vstupy a odhad slozitosti se u ulohy s funkci nedelaji - "
                "program necte standardni vstup)", "2"))
    elif args.only_complexity:
        print(c("\n   Odhad slozitosti umi jen ulohy, ktere ctou standardni vstup.", "2"))

    report.function_summary(comp.problems, fr, style_rep)
    return 1 if comp.problems or (fr and fr.level == FAIL) else 0


def test_io_task(src: Path, wd: Path, comp: Compiled, style_rep, task_dir: Path, cx_spec, outdir: Path,
                 args) -> int:
    samples = gen.load_samples(task_dir, args.lang)
    if not samples:
        print(c(f"\nVarovani: v {task_dir} nejsou zadna vzorova data (sample/**/*_in.txt).", "33"))
    oracle = Oracle.from_outputs([s.expected for s in samples])
    if args.suite:
        samples = [s for s in samples if s.suite in args.suite]
        if not samples:
            raise SystemExit(f"Zadna vzorova data v sadach {', '.join(args.suite)}.")
    cases = [] if args.only_complexity or args.only_style else samples if args.only_samples else samples + gen.generate(
        samples, args.fuzz, args.seed, not args.no_big)

    grades = []
    rel_bin, san_bin, dbg_bin = comp.rel, comp.san, comp.dbg
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
    report.report_groups(results, outdir, args)
    if not args.no_complexity and not args.only_samples and not args.only_style:
        grades = run_complexity(rel_bin, samples, cx_spec, args, outdir)

    report.io_summary(results, style_rep, grades, outdir, TESTER_DIR.parent)
    return 1 if any(v.level == FAIL for _, _, v in results) else 0


if __name__ == "__main__":
    main()
