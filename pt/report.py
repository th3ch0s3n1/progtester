"""Vypis vysledku na terminal a ukladani problemovych vstupu do slozky vysledky."""

import os
import sys
from pathlib import Path

from . import complexity, gen, style
from .checks import FAIL, WARN, diff

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def badge(level):
    return {"OK": c(" OK ", "1;32"), WARN: c("WARN", "1;33"), FAIL: c("FAIL", "1;31")}[level]


def show_bytes(b: bytes, limit=300) -> str:
    s = repr(b[:limit])[2:-1]
    return s + (f"... (+{len(b) - limit} B)" if len(b) > limit else "")


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


def _val(v, limits) -> str:
    """Hodnota v tabulce funkci, obarvena podle limitu (varovani, hodne spatne)."""
    text = str(v)
    if v > limits[1]:
        return c(text, "1;31")
    return c(text, "33") if v > limits[0] else text


def print_style(src: Path, rep: style.StyleReport):
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


def _style_line(rep):
    if rep:
        print(f"   Stabni kultura kodu: znamka {rep.grade}"
              + (f", {len(rep.bugs)} pravdepodobnych chyb ze staticke analyzy" if rep.bugs else ""))


def function_summary(problems: list, fr, style_rep):
    """Shrnuti ulohy "napis funkci"; `fr` je FuncResult nebo None (testy se nespoustely)."""
    print(c("\n== Shrnuti", "1"))
    for msg in problems:
        print(f"   {badge(FAIL)} {msg}")
    if fr is not None:
        stat = (f"{fr.passed}/{fr.total} proslo" if fr.total is not None
                else f"main() nedobehl, {fr.failed} selhalo" if fr.failed else "main() nedobehl")
        print(f"   {badge(fr.level)} Asserty ze zadani: {stat}"
              + (f"; chyba v: {', '.join(fr.broken)}" if fr.broken else ""))
    _style_line(style_rep)


def io_summary(results, style_rep, grades: list, outdir: Path, base: Path):
    """Shrnuti ulohy se vstupem/vystupem; cesta k vysledkum se vypise relativne k `base`."""
    totals = {lv: sum(v.level == lv for _, _, v in results) for lv in ("OK", WARN, FAIL)}
    print(c("\n== Shrnuti", "1"))
    suites = list(dict.fromkeys(case.group for case, _, _ in results if case.suite))
    for g in suites:
        res = [v for case, _, v in results if case.group == g]
        ok = sum(v.level != FAIL for v in res)
        print(f"   {badge('OK' if ok == len(res) else FAIL)} {g}: {ok}/{len(res)}")
    if results:
        print(f"   {totals['OK']} OK, {totals[WARN]} varovani, {totals[FAIL]} chyb z {len(results)} testu")
    _style_line(style_rep)
    if grades:
        print(f"   Odhad slozitosti: znamka {max(grades)}"
              + (f" (nejhorsi z {len(grades)} zmerenych zpusobu zvetseni vstupu)" if len(grades) > 1 else ""))
    if totals[FAIL] + totals[WARN]:
        try:
            shown = outdir.relative_to(base)
        except ValueError:
            shown = outdir
        print(f"   Problemove vstupy ulozeny v {shown}/")


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
