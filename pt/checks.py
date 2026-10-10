"""Vyhodnoceni jednoho behu. Bez znalosti reseni - kontroluji se jen veci,
ktere plati vzdy (pad, timeout, sanitizery, format vystupu, konzistence
se vzorovymi vystupy)."""

import difflib
import re
from dataclasses import dataclass, field

from .runner import RunResult

FAIL, WARN = "FAIL", "WARN"

SAN_MARKERS = (b"ERROR: AddressSanitizer", b"ERROR: LeakSanitizer", b"runtime error:",
               b"AddressSanitizer:DEADLYSIGNAL", b"UndefinedBehaviorSanitizer")
SAN_INFRA = b"LeakSanitizer has encountered a fatal error"
# desitkova, desetinna i hexadecimalni cisla (musi obsahovat aspon jednu cifru)
NUM_PAT = r"[-+]?[0-9A-Fa-f]*\d[0-9A-Fa-f]*(?:\.\d+)?"


@dataclass
class Oracle:
    """Co se da vycist ze vzorovych vystupu, aniz bychom znali reseni."""
    prompt: bytes | None                       # spolecny prvni radek vsech vystupu
    known_lines: set = field(default_factory=set)
    templates: list = field(default_factory=list)  # radky s cisly nahrazenymi regexem

    @classmethod
    def from_outputs(cls, outputs: list[bytes]) -> "Oracle":
        firsts = {o.split(b"\n", 1)[0] for o in outputs if o}
        prompt = firsts.pop() if len(firsts) == 1 and len(outputs) > 1 else None
        lines = {ln for o in outputs for ln in o.decode("utf-8", "replace").split("\n") if ln}
        templates = []
        for ln in lines:
            parts = re.split(f"({NUM_PAT})", ln)
            if len(parts) > 1:
                rx = "".join(NUM_PAT if i % 2 else re.escape(p) for i, p in enumerate(parts))
                templates.append(re.compile(rx + r"\Z"))
        return cls(prompt, lines, templates)

    def line_known(self, line: str) -> bool:
        return line in self.known_lines or any(t.match(line) for t in self.templates)

    def closest(self, line: str):
        m = difflib.get_close_matches(line, list(self.known_lines), n=1, cutoff=0.75)
        return m[0] if m else None


@dataclass
class Verdict:
    issues: list = field(default_factory=list)  # (uroven, zprava)

    def add(self, level, msg):
        self.issues.append((level, msg))

    @property
    def level(self):
        lv = {lvl for lvl, _ in self.issues}
        return FAIL if FAIL in lv else WARN if WARN in lv else "OK"


def _san_report(stderr: bytes) -> str:
    keep = []
    for ln in stderr.decode("utf-8", "replace").splitlines():
        ln = re.sub(r"(/[^\s:]+/)([^/\s:]+\.(c|cpp|h):\d+)", r"\2", ln.strip())  # jen jmeno souboru
        ln = re.sub(r"0x[0-9a-f]{8,}", "0x..", ln)
        if re.search(r"ERROR:|runtime error:|SUMMARY:", ln):
            keep.append(ln)
        elif re.search(r"#\d+ .* in \S+ \S+\.(c|cpp|h):\d+", ln):
            keep.append("  " + ln)  # ramce z kodu studenta (libc vynechavame)
    return "\n".join(keep[:8]) or stderr.decode("utf-8", "replace")[:600]


def has_sanitizer_error(r: RunResult) -> bool:
    return any(m in r.stderr for m in SAN_MARKERS) and SAN_INFRA not in r.stderr


def _crash(r: RunResult, label: str, v: Verdict, timeout: float):
    if r.timed_out:
        v.add(FAIL, f"[{label}] prekrocen casovy limit {timeout:g} s (nekonecna smycka / ceka na vstup?)")
    elif r.signal_name == "SIGXFSZ":
        v.add(FAIL, f"[{label}] vystup prekrocil 16 MB (nekonecny vypis?)")
    elif r.signal_name == "SIGXCPU":
        v.add(FAIL, f"[{label}] prekrocen limit CPU casu")
    elif r.signal_name:
        v.add(FAIL, f"[{label}] program spadl: {r.signal_name}")


def evaluate(case, rel: RunResult, san: RunResult | None, ref: RunResult | None,
             oracle: Oracle, timeout: float) -> Verdict:
    v = Verdict()
    _crash(rel, "-O2", v, timeout)

    if san is not None:
        if has_sanitizer_error(san):
            v.add(FAIL, "[ASan/UBSan] pametova chyba / nedefinovane chovani:\n" + _san_report(san.stderr))
        elif not san.timed_out and san.signal_name and not rel.signal_name:
            v.add(FAIL, f"[ASan/UBSan] program spadl jen v ladicim buildu: {san.signal_name}")
        clean = (not rel.timed_out and not rel.signal_name and not san.timed_out
                 and not san.signal_name and not has_sanitizer_error(san))
        if clean and rel.stdout != san.stdout:
            v.add(FAIL, "vystup -O2 a -O0 buildu se lisi -> nedefinovane chovani "
                        "(neinicializovana promenna, cteni mimo pole, ...)")

    if rel.timed_out or rel.signal_name:
        return v

    out = rel.stdout
    if rel.duration > timeout * 0.5:
        v.add(WARN, f"beh trval {rel.duration:.2f} s (vic nez pulka limitu)")
    if rel.stderr.strip():
        v.add(WARN, "program neco vypsal na stderr (progtest kontroluje jen stdout): "
                    + repr(rel.stderr[:120].decode("utf-8", "replace")))

    if case.expected is not None and out != case.expected:
        lvl = WARN if case.expected_soft else FAIL
        why = (" (stejny obsah jako vzor " + case.origin + ", lisi se jen bile znaky)"
               if case.expected_soft else "")
        v.add(lvl, "vystup neodpovida ocekavanemu" + why)
    if ref is not None and not ref.timed_out and not ref.signal_name and out != ref.stdout:
        v.add(FAIL, "vystup se lisi od referencniho programu (--ref)")

    if not out:
        v.add(FAIL, "prazdny vystup")
        return v
    if not out.endswith(b"\n"):
        v.add(FAIL, "vystup nekonci odradkovanim \\n")
    if b"\r" in out:
        v.add(FAIL, "vystup obsahuje \\r (Windows konce radku)")
    if oracle.prompt is not None and out.split(b"\n", 1)[0] != oracle.prompt:
        v.add(FAIL, f"prvni radek neni vyzva {oracle.prompt.decode('utf-8', 'replace')!r}")

    if case.expected is None:
        for ln in out.decode("utf-8", "replace").split("\n"):
            if ln and not oracle.line_known(ln):
                near = oracle.closest(ln)
                hint = f" - podobny vzorovy radek: {near!r} (preklep?)" if near else ""
                v.add(WARN, f"radek {ln[:100]!r} se nevyskytuje v zadnem vzorovem vystupu{hint}")
    return v


def diff(expected: bytes, got: bytes) -> str:
    def vis(b):
        # repr ukaze \n, \r, \t i mezery na konci radku
        return [repr(ln)[1:-1] for ln in b.decode("utf-8", "replace").splitlines(keepends=True)]
    lines = difflib.unified_diff(vis(expected), vis(got), "ocekavano", "dostal", lineterm="", n=2)
    return "\n".join(lines)
