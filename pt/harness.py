"""Ulohy typu "napis funkci": student odevzdava jen funkce, main() s asserty je v
#ifndef __PROGTEST__ ... #endif a progtest misto nej pouzije svuj vlastni.

Tester takovou ulohu pozna tak, ze s -D__PROGTEST__ program nema main(). Pak:
  - zkontroluje, ze kod jde prelozit tak jako na progtestu (s -D__PROGTEST__ a s hlavickami
    z bloku #ifndef __PROGTEST__, ktere progtest dodava sam) a nechybi v nem zadna funkce,
  - prelozi testovaci main() ze zadani (bez -D__PROGTEST__) s vlastnim assertem
    (pt/include/assert.h), ktery neukonci program a u porovnani vypise hodnoty,
  - spusti ho jako -O2, pod ASan/UBSan a pod valgrindem.
"""

import re
import signal
from dataclasses import dataclass, field

from .checks import FAIL, WARN, Verdict, _san_report, has_sanitizer_error, valgrind_report
from .runner import RunResult

_DIRECTIVE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")
_NOT_PROGTEST = re.compile(r"!\s*defined\s*\(?\s*__PROGTEST__\s*\)?")
_MAIN = re.compile(r"\b(?:int|void|auto)\s+main\s*\(")


@dataclass
class Guarded:
    """Blok #ifndef __PROGTEST__ ... (#else | #endif) - na progtestu se nepreklada."""
    start: int          # radek s #ifndef (od 1)
    end: int            # radek s #endif
    body: str           # obsah vetve, ktera se preklada jen lokalne
    has_main: bool


def _strip_comments(s: str) -> str:
    return re.sub(r"//.*", "", re.sub(r"/\*.*?\*/", " ", s, flags=re.S))


def guarded_blocks(text: str) -> list[Guarded]:
    lines = text.splitlines()
    stack, blocks = [], []   # stack: [je_guard, radek_zacatku, radek_else]
    for i, ln in enumerate(lines, 1):
        m = _DIRECTIVE.match(ln)
        if not m:
            continue
        d, rest = m.group(1), _strip_comments(m.group(2)).strip()
        if d in ("if", "ifdef", "ifndef"):
            g = (d == "ifndef" and rest == "__PROGTEST__") or (d == "if" and bool(_NOT_PROGTEST.fullmatch(rest)))
            stack.append([g, i, None])
        elif d in ("elif", "else"):
            if stack and stack[-1][2] is None:
                stack[-1][2] = i
        elif stack:
            g, start, els = stack.pop()
            if g and not any(s[0] for s in stack):  # vnoreny blok je soucasti vnejsiho
                body = "\n".join(lines[start:(els or i) - 1])
                blocks.append(Guarded(start, i, body, bool(_MAIN.search(_strip_comments(body)))))
    return blocks


def has_test_main(text: str) -> bool:
    return any(b.has_main for b in guarded_blocks(text))


def progtest_header(text: str, src_name: str) -> str:
    """To, co progtest dodava pred kod studenta: obsah bloku #ifndef __PROGTEST__ bez main()
    (typicky #include, nekdy i deklarace typu). #line zachova cisla radku v hlaskach."""
    out = []
    for b in guarded_blocks(text):
        if not b.has_main:
            out.append(f'#line {b.start + 1} "{src_name}"\n{b.body}\n')
    return "\n".join(out)


@dataclass
class Failure:
    line: int
    expr: str
    detail: str = ""


@dataclass
class AssertLog:
    passed: int | None = None        # None = program neskoncil normalne (nebo bez pocitani)
    failed: int = 0
    failures: list = field(default_factory=list)
    last_ok: int = 0                 # radek posledniho splneneho assertu
    crash_sig: int | None = None
    crash_at: int = 0                # assert, ktery se prave vyhodnocoval (0 = mezi asserty)
    timeout_at: int | None = None    # None = bez timeoutu, 0 = mezi asserty

    @property
    def total(self):
        return None if self.passed is None else self.passed + self.failed


def parse_log(text: str) -> AssertLog:
    log = AssertLog()
    for ln in text.splitlines():
        p = ln.split("\t")
        try:
            if p[0] == "F" and len(p) >= 3:
                log.failures.append(Failure(int(p[1]), p[2], p[3] if len(p) > 3 else ""))
                log.failed = max(log.failed, len(log.failures))
            elif p[0] == "S" and len(p) >= 4:
                log.passed, log.failed, log.last_ok = int(p[1]), int(p[2]), int(p[3])
            elif p[0] == "C" and len(p) >= 4:
                log.crash_sig, log.crash_at, log.last_ok = int(p[1]), int(p[2]), int(p[3])
            elif p[0] == "T" and len(p) >= 3:
                log.timeout_at, log.last_ok = int(p[1]), int(p[2])
        except ValueError:
            continue
    return log


_GLIBC = re.compile(r"^.*?:(\d+): .*?: Assertion [`'](.*)' failed\.$", re.M)


def parse_glibc(stderr: bytes) -> AssertLog:
    """Standardni assert (kdyz vlastni nesel prelozit): ukonci program u prvniho selhani."""
    log = AssertLog()
    m = _GLIBC.search(stderr.decode("utf-8", "replace"))
    if m:
        log.failures.append(Failure(int(m.group(1)), m.group(2)))
        log.failed = 1
    return log


def _sig_name(sig: int) -> str:
    try:
        return signal.Signals(sig).name
    except ValueError:
        return f"signal {sig}"


def _where(at: int, last_ok: int) -> str:
    if at:
        return f"pri assertu na r. {at}"
    return f"po assertu na r. {last_ok} (posledni splneny)" if last_ok else "jeste pred prvnim assertem"


def _uncaught(stderr: bytes) -> str:
    m = re.search(rb"terminate called after throwing an instance of '([^']+)'(?:\s+what\(\):\s*(.*))?", stderr)
    if not m:
        return ""
    what = f": {m.group(2).decode('utf-8', 'replace').strip()}" if m.group(2) else ""
    return f" - nezachycena vyjimka {m.group(1).decode('utf-8', 'replace')}{what}"


def assess(label: str, r: RunResult, log: AssertLog, timeout: float, sanitized: bool = False,
           vg_log: str | None = None, count_failures: bool = True) -> Verdict:
    """Prubeh jednoho behu testovaciho main(). Selhane asserty jsou FAIL, podrobnosti
    (vyrazy a hodnoty) vypisuje volajici."""
    v = Verdict()
    where = _where(log.crash_at, log.last_ok)
    if log.timeout_at is not None or r.timed_out:
        at = _where(log.timeout_at, log.last_ok) if log.timeout_at is not None else ""
        v.add(FAIL, f"[{label}] prekrocen casovy limit {timeout:g} s {at} (nekonecna smycka?)".rstrip())
    elif sanitized and has_sanitizer_error(r):
        v.add(FAIL, f"[{label}] pametova chyba / nedefinovane chovani:\n" + _san_report(r.stderr))
    elif log.crash_sig is not None or r.signal_name:
        name = _sig_name(log.crash_sig) if log.crash_sig is not None else r.signal_name
        if name == "SIGABRT" and log.crash_sig is None and log.failures and not log.passed:
            pass  # standardni assert - selhani uz je ve failures
        else:
            v.add(FAIL, f"[{label}] program spadl ({name}) {where}{_uncaught(r.stderr)}")
    elif r.returncode not in (0, None) and log.passed is not None and not vg_log:
        v.add(WARN, f"[{label}] main() skoncil s navratovym kodem {r.returncode}")
    if vg_log:
        v.add(FAIL, f"[{label}] " + valgrind_report(vg_log))
    if log.failed and count_failures:
        v.add(FAIL, f"[{label}] selhalo {log.failed} assertu"
                    + (f" z {log.total}" if log.total else ""))
    return v
