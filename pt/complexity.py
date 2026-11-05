"""Empiricky odhad casove slozitosti - bez znalosti ulohy.

Tester nevi, co je ve vstupu "velikost". Zkousi proto vzorove vstupy zvetsovat
obecnymi zpusoby a sleduje, jak roste cas:

  radek xn         jeden radek vzoru zopakovany n-krat
  radek xn, +1     totez, ale vybrane cislo je v kazde kopii o 1 vetsi (rostouci cas, id, ...)
  prvek xn         cislo i s oddelovacem za nim zopakovane n-krat (posloupnost na jednom radku)
  vstup xn         cely vzorovy vstup n-krat za sebou
  cislo +n         jedno cislo zvetsene o n (velikost hodnoty - napr. delka intervalu)

Zpusob zvetseni plati, jen dokud ho program prijima: nesmi spadnout ani vypsat
chybovou hlasku driv nez u puvodniho vzoru. Kde ho program prestane prijimat,
tam konci platny rozsah n (dohleda se pulenim) - na nej se extrapoluje cas.

Meri se CPU cas programu (user + sys): nezkresli ho paralelni beh ani rezie
spousteni z testeru. Namerene casy se prolozi modely t = c + a*f(n) pro f = 1, log n, n, n log n,
n^2, n^3 a porovnaji s idealem: u opakovani O(n log n) celkem (zpracovani
jednoho prvku nesmi zaviset na tom, kolik jich uz bylo), u hodnoty cisla
O(log n) (cas nema rust s velikosti cisla).

Volitelne lze misto automatiky dodat vlastni generator (soubor s SERIES, viz README).
"""

import importlib.util
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .gen import ERROR_RE, NUM_RE
from .runner import run

CLASSES = ["1", "log n", "n", "n log n", "n^2", "n^3"]
_F = {
    "1": lambda n: 0.0,
    "log n": lambda n: math.log2(n),
    "n": lambda n: float(n),
    "n log n": lambda n: n * math.log2(n),
    "n^2": lambda n: float(n) ** 2,
    "n^3": lambda n: float(n) ** 3,
}
_ALIASES = {"1": "1", "logn": "log n", "n": "n", "nlogn": "n log n", "n^2": "n^2", "n2": "n^2",
            "n^3": "n^3", "n3": "n^3"}

IDEAL_REPEAT = "n log n"   # n prvku: kazdy nejvys O(log n)
IDEAL_VALUE = "log n"      # cislo velikosti n: cas nema rust s hodnotou

FLAT_ABS = 0.004           # rozdil casu pod 4 ms je sum
GROWS_ABS = 0.010          # zpusob zvetseni je zajimavy, kdyz cas naroste aspon o 10 ms
MAX_INPUT = 16 * 1024 * 1024        # presne mereni
MAX_INPUT_SCREEN = 4 * 1024 * 1024  # predbezne mereni (jen vybira, co merit presne)
N_LIMIT = 2 ** 40
MAX_TOKENS = 12            # kolik cisel na radku zkouset
PER_SHAPE = 3              # v kolika vzorech zkouset radek stejneho tvaru
JUMP = 10                  # cas skoci aspon 10x -> podezrely skok (preteceni, nekonecna smycka)
TAIL_TOL = 0.4             # o kolik smi model minout cas u dvou nejvetsich n (relativne)


def norm_class(s: str | None) -> str | None:
    if s is None:
        return None
    k = (str(s).lower().replace("o(", "").replace(" ", "").replace("*", "").replace("(", "")
         .replace(")", "").replace("²", "^2").replace("³", "^3").replace("log2", "log"))
    if k not in _ALIASES:
        raise SystemExit(f"neznama slozitost {s!r} (pouzij {', '.join(CLASSES)})")
    return _ALIASES[k]


@dataclass
class Point:
    n: int
    time: float      # nejlepsi CPU cas [s]
    in_bytes: int


@dataclass
class Fit:
    cls: str                 # nejlepsi model
    alts: list               # dalsi modely, ktere sedi skoro stejne dobre
    c: float = 0.0
    a: float = 0.0
    flat: bool = False       # cas se s n prakticky nemeni
    exponent: float | None = None

    def predict(self, n: int) -> float:
        return self.c + self.a * _F[self.cls](n)

    @property
    def best_cls(self) -> str:
        """Nejlepsi trida v ramci presnosti mereni."""
        return min([self.cls, *self.alts], key=CLASSES.index)


@dataclass
class Knob:
    """Jeden zpusob, jak vstup zvetsit na velikost n."""
    kind: str                       # line, inc, seg, input, value, spec
    desc: str
    build: Callable[[int], bytes]
    ideal: str | None
    n_min: int = 1
    n_max: int | None = None        # znamy rozsah (jen u vlastniho generatoru)
    base_out: bytes | None = None   # vystup programu na puvodnim vzoru
    # vysledky mereni
    points: list = field(default_factory=list)
    stop: str = ""                  # time | invalid | crash | input | max
    stop_n: int | None = None
    crash: str = ""
    bound: int | None = None        # nejvetsi n, ktere program jeste prijme
    fit: Fit | None = None
    predicted: float | None = None  # cas pro n = bound
    limit_n: int | None = None      # od jakeho n se prekroci limit
    grade: int | None = None
    verdict: str = ""
    warning: str = ""
    progress: list = field(default_factory=list)  # [(n, radku vystupu pred chybou)] prvnich dvou velikosti


# ---------------------------------------------------------------- hledani zpusobu zvetseni

def _show(b: bytes, width=48) -> str:
    s = b.decode("utf-8", "replace")
    return repr(s if len(s) <= width else s[:width] + "...")


def _join(lines):
    return b"\n".join(lines)


def _make_line(lines, i):
    return lambda n: _join(lines[:i] + [lines[i]] * n + lines[i + 1:])


def _bump(tok: bytes, d: int) -> bytes:
    return str(int(tok) + d).zfill(len(tok)).encode()  # zachova uvodni nuly (01 -> 02)


def _make_inc(lines, i, m):
    ln = lines[i]
    pre, tok, post = ln[:m.start()], m.group(), ln[m.end():]
    return lambda n: _join(lines[:i] + [pre + _bump(tok, k) + post for k in range(n)] + lines[i + 1:])


def _make_value(lines, i, m):
    ln = lines[i]
    pre, tok, post = ln[:m.start()], m.group(), ln[m.end():]
    return lambda n: _join(lines[:i] + [pre + _bump(tok, n) + post] + lines[i + 1:])


def _make_seg(lines, i, a, b):
    ln = lines[i]
    return lambda n: _join(lines[:i] + [ln[:a] + ln[a:b] * n + ln[b:]] + lines[i + 1:])


def discover(samples, binary: Path, mem_mb, timeout: float) -> list[Knob]:
    """Zpusoby zvetseni vzorovych vstupu.

    Radky stejneho tvaru (lisi se jen cisla) se zkousi nejvys v PER_SHAPE ruznych vzorech, v kazdem
    posledni vyskyt: o kousek driv ve vstupu muze stejny prikaz delat neco jineho (napr. dotaz pred
    prvnim zadanim dat jen vypise N/A a na velikosti cisla pak nezalezi).
    """
    usable = sorted((s for s in samples if s.expected is not None and not ERROR_RE.search(s.expected)),
                    key=lambda s: len(s.data))
    knobs, seen = [], {}
    for s in usable:
        base = run(binary, s.data, timeout * 5, mem_mb)
        if base.timed_out or base.signal_name:
            continue
        out = base.stdout
        in_sample = set()

        def add(key, kind, desc, build, ideal):
            if key in in_sample or seen.get(key, 0) >= PER_SHAPE:
                return
            in_sample.add(key)
            seen[key] = seen.get(key, 0) + 1
            knobs.append(Knob(kind, desc, build, ideal, base_out=out))

        add(("input",), "input", f"cely vstup {s.name} n-krat za sebou", lambda n, d=s.data: d * n, IDEAL_REPEAT)
        lines = s.data.split(b"\n")
        for i in reversed(range(len(lines))):
            ln = lines[i]
            if not ln.strip():
                continue
            tpl = NUM_RE.sub(b"#", ln)
            where = f"{s.name}:{i + 1}"
            add(("line", tpl), "line", f"radek {_show(ln)} n-krat  ({where})", _make_line(lines, i), IDEAL_REPEAT)
            nums = list(NUM_RE.finditer(ln))[:MAX_TOKENS]
            for j, m in enumerate(nums):
                tok = m.group()
                mark = ln[:m.start()] + b"[" + tok + b"]" + ln[m.end():]
                if tok.isdigit():
                    add(("value", tpl, j), "value", f"cislo {_show(mark)} zvetsene o n  ({where})",
                        _make_value(lines, i, m), IDEAL_VALUE)
                    add(("inc", tpl, j), "inc", f"radek {_show(mark)} n-krat, cislo v kazde kopii o 1 vetsi  "
                                                f"({where})", _make_inc(lines, i, m), IDEAL_REPEAT)
                if j + 1 < len(nums):
                    a, b = m.start(), nums[j + 1].start()
                    add(("seg", tpl, j), "seg", f"prvek {_show(ln[a:b])} n-krat na radku {_show(ln)}  ({where})",
                        _make_seg(lines, i, a, b), IDEAL_REPEAT)
    return knobs


def load_spec(path: Path) -> tuple[float | None, list[Knob]]:
    """Vlastni generator: SERIES = [dict(name=..., gen=n -> vstup, n_min, n_max, target), ...]."""
    spec = importlib.util.spec_from_file_location("pt_user_complexity", path)
    mod = importlib.util.module_from_spec(spec)
    dont_write, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # zadny __pycache__ ve slozce ulohy
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = dont_write
    series = getattr(mod, "SERIES", None)
    if not series:
        raise SystemExit(f"{path}: chybi SERIES = [dict(name=..., gen=..., ...), ...]")
    knobs = []
    for sp in series:
        def build(n, g=sp["gen"]):
            d = g(n)
            return d.encode() if isinstance(d, str) else bytes(d)
        n_max = sp.get("n_max")
        knobs.append(Knob("spec", sp.get("name", "?"), build, norm_class(sp.get("target")),
                          int(sp.get("n_min", 16)), int(n_max) if n_max else None))
    return getattr(mod, "TIME_LIMIT", None), knobs


# ---------------------------------------------------------------- mereni

def _err_lines(out: bytes) -> int | None:
    m = ERROR_RE.search(out)
    return None if m is None else out[:m.start()].count(b"\n")


def _accepted(k: Knob, out: bytes, data: bytes, n: int) -> bool:
    """Prijal program zvetseny vstup?

    1. Chybova hlaska nesmi prijit driv nez u puvodniho vzoru.
    2. Vystupu (radku pred pripadnou chybou) musi s n pribyvat stejnym tempem jako mezi prvnimi
       dvema velikostmi - jinak program cast vstupu odmitl (chyba prisla az po mnoha odpovedich).
    """
    e = _err_lines(out)
    lines = out.count(b"\n") if e is None else e
    if len(k.progress) < 2:
        if not k.progress or k.progress[-1][0] != n:
            k.progress.append((n, lines))
    else:
        (n1, p1), (n2, p2) = k.progress
        if n > n2 and lines < p1 + (p2 - p1) / (n2 - n1) * (n - n1) - 1:
            return False
    if e is None:
        return True
    if k.base_out is not None:
        b = _err_lines(k.base_out)
        return b is not None and e >= b
    # vlastni generator: hlaska az na konci vystupu = nejspis spatne zpracovany EOF
    if e >= 0.1 * data.count(b"\n"):
        k.warning = k.warning or (f"chybova hlaska az po {e} radcich vystupu - nejspis spatne zpracovavas "
                                  f"konec vstupu (EOF); mereni pokracuje")
        return True
    return False


def _sizes(n_min: int, n_max: int | None, step: int):
    n, top = max(1, n_min), n_max or N_LIMIT
    while n <= top:
        yield n
        if n_max and n < n_max < step * n:
            yield n_max
        n *= step


def ramp(k: Knob, binary: Path, cap: float, mem_mb, reps: int = 1, step: int = 2,
         max_input: int = MAX_INPUT):
    """Zvetsuje n (n_min, n_min*step, ...), dokud program vstup prijima a stiha."""
    k.points, k.stop, k.stop_n, k.crash, k.progress = [], "max", None, "", []
    for n in _sizes(k.n_min, k.n_max, step):
        data = k.build(n)
        if len(data) > max_input:
            k.stop, k.stop_n = "input", n
            return
        best = None
        for _ in range(reps):
            r = run(binary, data, cap * 2 + 1, mem_mb)
            if r.timed_out:
                k.stop, k.stop_n = "time", n
                return
            if r.signal_name:
                k.stop, k.stop_n, k.crash = "crash", n, r.signal_name
                return
            if not _accepted(k, r.stdout, data, n):
                k.stop, k.stop_n = "invalid", n
                return
            if best is None or r.cpu < best.time:
                best = Point(n, r.cpu, len(data))
            if r.cpu > 0.2:
                break  # dlouhe behy neopakujeme, sum je relativne maly
        k.points.append(best)
        if best.time > cap:
            k.stop = "time"
            return


def _ok_at(k: Knob, binary, n, cap, mem_mb) -> bool:
    data = k.build(n)
    if len(data) > MAX_INPUT:
        return False
    r = run(binary, data, cap * 2 + 1, mem_mb)
    return r.timed_out or (not r.signal_name and _accepted(k, r.stdout, data, n))  # timeout = prijal, jen pomaly


def find_bound(k: Knob, binary, cap, mem_mb):
    """Pulenim najde nejvetsi n, ktere program jeste prijme (kdyz zvetsovani skoncilo chybou/padem)."""
    if k.stop not in ("invalid", "crash") or not k.points or k.stop_n is None:
        return
    lo, hi = k.points[-1].n, k.stop_n
    while hi - lo > max(1, lo // 64):
        mid = (lo + hi) // 2
        if _ok_at(k, binary, mid, cap, mem_mb):
            lo = mid
        else:
            hi = mid
    if k.stop == "crash":
        k.stop_n = hi
    k.bound = lo


# ---------------------------------------------------------------- prolozeni a hodnoceni

def _fit_model(ns, ts, cls):
    """Vazene nejmensi ctverce pro t = c + a*f(n) (relativni chyba), c, a >= 0."""
    w = [1 / t ** 2 for t in ts]
    fs = [_F[cls](n) for n in ns]
    if cls == "1":
        c = sum(wi * t for wi, t in zip(w, ts)) / sum(w)
        a = 0.0
    else:
        sw = sum(w)
        sf = sum(wi * f for wi, f in zip(w, fs))
        sff = sum(wi * f * f for wi, f in zip(w, fs))
        st = sum(wi * t for wi, t in zip(w, ts))
        sft = sum(wi * f * t for wi, f, t in zip(w, fs, ts))
        det = sw * sff - sf * sf
        c, a = ((sff * st - sf * sft) / det, (sw * sft - sf * st) / det) if det else (0.0, 0.0)
        if c < 0:  # bez konstanty
            c, a = 0.0, sft / sff
        if a <= 0:
            return None
    err = math.sqrt(sum(((c + a * f - t) / t) ** 2 for f, t in zip(fs, ts)) / len(ts))
    return err, c, a


def _exponent(points):
    """Lokalni exponent k (t ~ n^k) z poslednich bodu, kde uz cas neni jen sum."""
    pts = [p for p in points if p.time >= 0.01]
    ks = [math.log(q.time / p.time) / math.log(q.n / p.n) for p, q in zip(pts, pts[1:]) if q.n > p.n]
    if not ks:
        return None
    ks = ks[-3:]
    return sorted(ks)[len(ks) // 2]


def _head_tail(points) -> tuple[float, float]:
    """Cas na zacatku a na konci rady, odolny vuci jednomu odlehlemu mereni."""
    ts = [p.time for p in points]
    return min(ts[:3]), min(ts[-2:])


def fit(points: list[Point]) -> Fit | None:
    if len(points) < 4:
        return None
    ns, ts = [p.n for p in points], [max(p.time, 1e-4) for p in points]
    head, tail = _head_tail(points)
    if tail <= 1.3 * head + FLAT_ABS:
        return Fit("1", ["log n"], c=sum(ts) / len(ts), flat=True)
    res = {}
    for cls in CLASSES:
        r = _fit_model(ns, ts, cls)
        if r:
            res[cls] = r
    # model musi sedet i na nejvetsich n - tam je signal; jinak by jednodussi model "vyhral" na
    # bodech, kde je cas jen startovni sum (napr. O(n) na datech, kde 4x vetsi n trva 15x dyl)
    def tail_ok(cls):
        _, c, a = res[cls]
        return all(abs(c + a * _F[cls](n) - t) <= TAIL_TOL * t for n, t in zip(ns[-2:], ts[-2:]))

    good = {k: r for k, r in res.items() if tail_ok(k)} or res
    err = min(r[0] for r in good.values())
    ok = [k for k in CLASSES if k in good and good[k][0] <= err * 1.3 + 0.02]
    best = ok[0]  # z modelu, ktere sedi skoro stejne dobre, ten nejjednodussi
    alts = [k for k in ok if CLASSES.index(k) == CLASSES.index(best) + 1]
    return Fit(best, alts, c=res[best][1], a=res[best][2], exponent=_exponent(points))


def growth(k: Knob) -> float:
    """Kolikrat se cas zvetsil (inf = uz nestiha)."""
    if k.stop == "time":
        return math.inf
    if len(k.points) < 4:
        return 1.0
    head, tail = _head_tail(k.points)
    return tail / max(head, 1e-4)


def rank(k: Knob) -> tuple:
    """Poradi pro presne mereni: nejdriv o kolik je slozitost horsi nez ideal, pak narust casu."""
    f = fit(k.points)
    d = CLASSES.index(f.best_cls) - CLASSES.index(k.ideal) if f and k.ideal else 0
    if f and f.flat and k.stop == "time":
        d = 9  # podezrely skok
    return d, growth(k)


def group_key(k: Knob) -> tuple:
    """Zpusoby zvetseni se stejnym zaverem: druh (opakovani / hodnota) a hruba slozitost."""
    f = fit(k.points)
    return k.ideal, (f.best_cls if f else None), (f.flat if f else None), k.stop == "time" and (f is None or f.flat)


def grows(k: Knob) -> bool:
    """Zpomaluje tento zpusob zvetseni program meritelne?"""
    if k.stop == "time":
        return True
    if len(k.points) < 4:
        return False
    head, tail = _head_tail(k.points)
    return tail >= 1.5 * head + GROWS_ABS


def _limit_n(f: Fit, limit: float, start: int) -> int | None:
    """Nejmensi n, pro ktere model prekroci limit (None = nikdy do 2^62)."""
    if f.flat or f.cls == "1":
        return None
    lo, hi = start, start
    while f.predict(hi) <= limit:
        lo, hi = hi, hi * 2
        if hi > 2 ** 62:
            return None
    while hi - lo > max(1, lo // 100):
        mid = (lo + hi) // 2
        lo, hi = (mid, hi) if f.predict(mid) <= limit else (lo, mid)
    return hi


def evaluate(k: Knob, limit: float):
    k.fit = f = fit(k.points)
    if f is None:
        if k.stop == "time" and k.points:
            k.grade, k.verdict = 5, f"moc pomale uz pro n = {fmt_n(k.points[-1].n * 2)}"
        return
    bound = k.n_max if k.kind == "spec" else k.bound
    last = k.points[-1]
    if bound:
        k.predicted = last.time if last.n >= bound else f.predict(bound)
    if not (bound and last.n >= bound):
        k.limit_n = _limit_n(f, limit, last.n)
        if bound and k.limit_n and k.limit_n > bound:
            k.limit_n = None  # mimo rozsah, ktery program prijima

    fits = k.predicted is None or k.predicted <= limit
    if k.ideal is None:  # vlastni generator bez cile - jen podle casu
        if k.predicted is None:
            return
        ratio = k.predicted / limit
        k.grade = 1 if ratio <= 0.25 else 2 if ratio <= 0.5 else 3 if ratio <= 1 else 4 if ratio <= 4 else 5
        k.verdict = ("s rezervou stihne limit" if k.grade <= 2 else "stihne limit tesne" if k.grade == 3
                     else "nestihne casovy limit")
        return

    head = _head_tail(k.points)[0]
    if f.flat and k.stop == "time" or f.flat and last.time > JUMP * head + GROWS_ABS:
        k.grade = 4
        k.verdict = (f"cas se s n nemeni, ale pro n = {fmt_n(k.stop_n or last.n)} najednou prudce vzroste - "
                     f"preteceni promenne, nekonecna smycka?")
        return

    d = CLASSES.index(f.best_cls) - CLASSES.index(k.ideal)
    what = "s hodnotou cisla" if k.kind == "value" else "s poctem prvku"
    if d <= 0:
        k.grade, k.verdict = ((1, "vyborne - lepe to nejde") if fits else
                              (3, "slozitost je dobra, ale konstanta je moc velka - zrychli implementaci"))
    elif k.predicted is not None:  # znamy rozsah
        if k.predicted <= limit:
            k.grade, k.verdict = 2, (f"v platnem rozsahu (n <= {fmt_n(bound)}) limit stihne, ale cas roste "
                                     f"{what} zbytecne rychle - jde to lepe (idealne O({k.ideal}))")
        elif k.predicted <= 10 * limit:
            k.grade, k.verdict = 4, f"pro n = {fmt_n(bound)} nestihne casovy limit - potrebujes lepsi algoritmus"
        else:
            k.grade, k.verdict = 5, f"pro n = {fmt_n(bound)} je radove pomaly - potrebujes lepsi algoritmus"
    elif k.stop == "time":  # program takovy vstup prijima a uz pri merenem n nestiha
        k.grade = 4 if d == 1 else 5
        k.verdict = (f"cas roste {what} jako O({f.best_cls}) a program takovy vstup prijima - "
                     f"pri vetsim n nestihne limit (idealne O({k.ideal}))")
    else:
        k.grade = 3 if d == 1 else 4 if d == 2 else 5
        k.verdict = f"cas roste {what} jako O({f.best_cls}) - da se vylepsit (idealne O({k.ideal}))"


# ---------------------------------------------------------------- formatovani

def fmt_n(n) -> str:
    if n is None:
        return "?"
    return f"{n:,}".replace(",", " ") if n < 10 ** 7 else f"{n:.2g}".replace("+0", "").replace("+", "")


def fmt_time(t: float) -> str:
    if t < 1:
        return f"{t * 1000:.1f} ms"
    if t < 600:
        return f"{t:.2f} s"
    if t < 3 * 86400:
        return f"{t / 3600:.1f} h"
    return f"{t / 86400:.0f} dni" if t < 365 * 86400 else f"{t / (365 * 86400):.1g} let"
