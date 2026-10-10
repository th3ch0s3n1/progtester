"""Nacteni vzorovych dat a generovani vstupu, ktere se snazi program rozbit.

Generator nezna reseni ulohy. Vychazi jen ze vzorovych vstupu (cisla v nich
nahrazuje meznimi hodnotami, usekava je, mutuje) a z obecne zakernych vstupu.
"""

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

G_SAMPLE = "Zakladni test (vzorova data)"
G_WS = "Test bilych znaku a konce radku"
G_BOUND = "Test meznich hodnot"
G_INVALID = "Test osetreni nespravnych vstupu"
G_EOF = "Test useknuteho vstupu (EOF)"
G_BIG = "Test velkych vstupu"
G_FUZZ = "Nahodny test (fuzz)"
GROUPS = [G_SAMPLE, G_WS, G_BOUND, G_INVALID, G_EOF, G_BIG, G_FUZZ]

NUM_RE = re.compile(rb"[-+]?\d+(?:\.\d+)?")


@dataclass
class Case:
    name: str
    group: str
    data: bytes
    expected: bytes | None = None   # presny ocekavany vystup (jen vzorova data)
    expected_soft: bool = False     # neshoda = varovani, ne chyba
    note: str = ""
    origin: str = field(default="", repr=False)


LANGS = ("CZE", "ENG")


def load_samples(task: Path, lang: str = "CZE") -> list[Case]:
    """Vsechny *_in.txt + *_out.txt z <uloha>/sample/** a <uloha>/tests/** (bez duplicit).

    Soubory ve slozce jineho jazyka (CZE/ENG) se preskoci; lang="all" bere vse.
    """
    cases, seen = [], set()
    for sub in ("sample", "tests"):
        root = task / sub
        if not root.is_dir():
            continue
        for fin in sorted(root.rglob("*_in.txt")):
            parts = fin.relative_to(root).parts
            if lang != "all" and any(p in LANGS and p != lang for p in parts):
                continue
            fout = fin.with_name(fin.name.replace("_in.txt", "_out.txt"))
            if not fout.exists():
                continue
            data, out = fin.read_bytes(), fout.read_bytes()
            if (data, out) in seen:
                continue
            seen.add((data, out))
            cases.append(Case(str(fin.relative_to(task)), G_SAMPLE, data, out))
    return cases


def _boundary_values(tok: bytes) -> list[bytes]:
    vals = [b"0", b"-0", b"+0", b"1", b"-1",
            b"2147483647", b"-2147483648", b"2147483648", b"-2147483649",
            b"4294967295", b"4294967296",
            b"9223372036854775807", b"-9223372036854775808", b"9223372036854775808",
            b"18446744073709551616", b"9" * 40, b"-" + b"9" * 40]
    try:
        n = int(tok)
    except ValueError:
        n = None
    if n is not None:
        vals += [str(n - 1).encode(), str(n + 1).encode(), b"+" + tok.lstrip(b"+"),
                 b"0" * 30 + tok.lstrip(b"+-"), tok + b".0", tok + b".5",
                 tok + b"e0", b"0x" + tok.lstrip(b"+-")]
    return vals


GENERIC_INVALID = [
    b"", b" ", b"\n", b"\n\n\n", b"\t \n", b"abc\n", b"a\n", b"x1\n", b"1x\n",
    b"1abc\n", b"1.23\n", b"1,5\n", b".5\n", b"5.\n", b"-\n", b"+\n", b"--1\n",
    b"+-1\n", b"- 1\n", b"1e3\n", b"0x1\n", b"1 2\n", b"1\r\n", b"\r\n",
    b"\x00\n", b"1\x00\n", b"\xff\xfe\n", b"\xef\xbc\x91\n",  # fullwidth 1
    b"\xc3\xa1\n", b"%d%s%n\n", b"'\"\\\n", b"\x1b[31m1\n", b"\x04", b"\x1a\n",
]


def _whitespace_variants(data: bytes) -> list[tuple[str, bytes]]:
    out = []
    stripped = data.rstrip(b"\n")
    if data.endswith(b"\n"):
        out.append(("bez \\n na konci", stripped))
    out.append(("vic \\n na konci", stripped + b"\n\n\n"))
    out.append(("bile znaky na zacatku", b" \t\n  " + data))
    out.append(("mezery na konci radku", stripped + b"   \n"))
    out.append(("tabulator na konci radku", stripped + b"\t\n"))
    out.append(("mezery na konci bez \\n", stripped + b"  "))
    if b" " in stripped:
        out.append(("vic mezer mezi tokeny", re.sub(rb" +", b" \t \n ", stripped) + b"\n"))
    return out


def _mutate(rng: random.Random, data: bytes) -> bytes:
    alphabet = b"0123456789 \n\t-+.,aZ\x00\xff\r"
    b = bytearray(data)
    for _ in range(rng.randint(1, 4)):
        op = rng.randrange(6)
        pos = rng.randint(0, len(b))
        if op == 0:
            b[pos:pos] = bytes([rng.choice(alphabet)])
        elif op == 1 and b:
            del b[min(pos, len(b) - 1)]
        elif op == 2 and b:
            b[min(pos, len(b) - 1)] = rng.choice(alphabet)
        elif op == 3 and b:
            a = rng.randrange(len(b))
            b[pos:pos] = b[a:a + rng.randint(1, 8)]
        elif op == 4:
            b[pos:pos] = str(rng.choice([0, -1, 2**31, -2**31 - 1, 10**18, rng.randint(-999, 999)])).encode()
        else:
            del b[pos:]
    return bytes(b)


def generate(samples: list[Case], fuzz: int, seed: int, big: bool) -> list[Case]:
    rng = random.Random(seed)
    cases: list[Case] = []
    seen = {c.data for c in samples}

    def add(group, name, data, **kw):
        if data in seen:
            return
        seen.add(data)
        cases.append(Case(name, group, data, **kw))

    # 1) bile znaky - vystup by se nemel zmenit (jen varovani, neni to vzdy pravidlo)
    for s in samples:
        for desc, d in _whitespace_variants(s.data):
            add(G_WS, f"{s.name}: {desc}", d, expected=s.expected, expected_soft=True, origin=s.name)

    # 2) mezni hodnoty - kazde cislo ve vzorovem vstupu postupne nahradime
    for s in samples:
        matches = list(NUM_RE.finditer(s.data))[:8]
        for m in matches:
            for v in _boundary_values(m.group()):
                d = s.data[:m.start()] + v + s.data[m.end():]
                add(G_BOUND, f"{s.name}: {m.group().decode()} -> {v[:24].decode()}", d, origin=s.name)

    # 3) nespravne vstupy
    for d in GENERIC_INVALID:
        add(G_INVALID, f"obecny: {d!r}", d)
    for s in samples:
        for m in list(NUM_RE.finditer(s.data))[:4]:
            t = m.group()
            for v in (t + b"abc", b"abc" + t, t + b".5", t + b",", t + b"#", t + b"\x00", t + b"-" + t):
                add(G_INVALID, f"{s.name}: {t.decode()} -> {v!r}", s.data[:m.start()] + v + s.data[m.end():],
                    origin=s.name)

    # 4) useknuty vstup - EOF kdekoliv uprostred
    for s in samples:
        n = len(s.data)
        cuts = range(n) if n <= 64 else sorted(rng.sample(range(n), 40))
        for c in cuts:
            add(G_EOF, f"{s.name}: prvnich {c} B", s.data[:c], origin=s.name)

    # 5) velke vstupy
    if big:
        first = samples[0].data if samples else b"1\n"
        add(G_BIG, "1M mezer + vzor", b" " * 10**6 + first)
        add(G_BIG, "1M nul + vzor", b"0" * 10**6 + first)
        add(G_BIG, "100k devitek", b"9" * 10**5 + b"\n")
        add(G_BIG, "1M znaku 'a'", b"a" * 10**6 + b"\n")
        add(G_BIG, "vzor 50000x za sebou", first * 50000)
        add(G_BIG, "1M nahodnych bajtu", rng.randbytes(10**6))
        add(G_BIG, "radek 1M dlouhy bez \\n", b"1" + b"x" * 10**6)

    # 6) fuzz
    if samples:
        for i in range(fuzz * 4):
            if sum(c.group == G_FUZZ for c in cases) >= fuzz:
                break
            s = rng.choice(samples)
            add(G_FUZZ, f"#{i} z {s.name}", _mutate(rng, s.data), origin=s.name)

    return cases
