"""Stabni kultura zdrojoveho kodu (C i C++) - bez zavislosti.

Pro C/C++ neexistuje jeden zavazny styl jako PEP 8 u Pythonu. Kontroluji se proto
veci, na kterych se shodnou bezne styly (Linux kernel, Google, CERT) i cvicici:

  funkce      delka, vetveni (cyklomaticka slozitost), hloubka zanoreni, pocet parametru,
              komentar nad funkci, "vsechno v main"
  soubor      globalni promenne, goto, magicka cisla, duplicitni kod, michani
              snake_case/camelCase, michani tabulatoru a mezer, dlouhe radky

Kod v #ifndef __PROGTEST__ ... #endif se nekontroluje (byva v nem testovaci main ze zadani).
Kdyz je nainstalovany cppcheck nebo clang-tidy, jejich nalezy se pridaji.

Kazdy nalez ma vahu (trestne body), stejny druh nalezu se zapocita nejvys MAX_SAME-krat;
soucet bodu urcuje znamku 1-5.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# limity: (varovani, hodne spatne)
FUNC_LINES = (50, 100)
CYCLOMATIC = (10, 20)
NESTING = (3, 5)
PARAMS = 5
LINE_LEN = 120
MAGIC_MIN = 5          # tolik ruznych magickych cisel uz stoji za zminku
DUP_WINDOW = 5         # tolik stejnych netrivialnich radku za sebou = duplicitni kod
ALLOWED_NUMBERS = {"0", "1", "2", "10", "100", "0.0", "1.0", "0.5", "2.0"}
MAX_SAME = 3
# trestne body na 100 radku kodu (u kratsich programu se deli jako by mely 100 radku) -> znamka, jinak 5
GRADE_DENSITY = [(1.0, 1), (2.5, 2), (4.5, 3), (7.0, 4)]

MINOR, MAJOR, SEVERE = 1, 2, 6

KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "sizeof", "do", "else", "case",
            "alignof", "decltype", "static_assert", "defined"}


@dataclass
class Function:
    name: str
    line: int          # radek hlavicky
    end_line: int
    lines: int         # radky s kodem
    params: int
    cyclomatic: int
    nesting: int
    commented: bool


@dataclass
class Finding:
    weight: int
    rule: str
    line: int | None
    msg: str
    bug: bool = False  # pravdepodobna chyba (staticka analyza), ne styl - do znamky se nepocita


@dataclass
class StyleReport:
    src: Path
    functions: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    code_lines: int = 0
    tools: list = field(default_factory=list)   # pouzite externi nastroje
    missing_tools: list = field(default_factory=list)
    points: int = 0
    density: float = 0.0   # trestne body na 100 radku kodu
    grade: int = 1

    def add(self, weight, rule, line, msg, bug=False):
        self.findings.append(Finding(weight, rule, line, msg, bug))

    @property
    def style(self):
        return [f for f in self.findings if not f.bug]

    @property
    def bugs(self):
        return [f for f in self.findings if f.bug]


# ---------------------------------------------------------------- priprava zdrojaku

def clean(src: str) -> tuple[str, set[int], int]:
    """Nahradi komentare, retezce, znakove literaly a direktivy preprocesoru mezerami
    (zachova delku i konce radku, aby sedela cisla radku a pozice).

    Vraci (vycisteny kod, cisla radku s komentarem, pocet radku v #ifndef __PROGTEST__).
    Bloky #ifndef __PROGTEST__ ... #else/#endif se vymazou cele.
    """
    out = list(src)
    comment_lines = set()
    i, n, line = 0, len(src), 1

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    at_line_start = True
    skip_depth = None   # hloubka #if, na ktere zacal vynechany blok __PROGTEST__
    if_depth = 0
    skipped = 0
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            at_line_start = True
            i += 1
            continue
        if at_line_start and ch in " \t":
            i += 1
            continue
        if at_line_start and ch == "#":
            # direktiva (i s pokracovanim na dalsim radku)
            j = i
            while True:
                e = src.find("\n", j)
                e = n if e < 0 else e
                if e > 0 and src[e - 1] == "\\" and e < n:
                    j = e + 1
                    continue
                break
            d = src[i:e]
            word = re.match(r"#\s*(\w*)", d).group(1)
            if word in ("if", "ifdef", "ifndef"):
                if_depth += 1
                if skip_depth is None and re.match(r"#\s*ifndef\s+__PROGTEST__\b", d):
                    skip_depth = if_depth
            elif word in ("else", "elif") and skip_depth == if_depth:
                skip_depth = None
            elif word == "endif":
                if skip_depth == if_depth:
                    skip_depth = None
                if_depth -= 1
            blank(i, e)
            line += src.count("\n", i, e)
            i = e
            at_line_start = False
            continue
        at_line_start = False
        if skip_depth is not None:
            e = src.find("\n", i)
            e = n if e < 0 else e
            if src[i:e].strip():
                skipped += 1
            blank(i, e)
            i = e
            continue
        if src.startswith("//", i):
            e = src.find("\n", i)
            e = n if e < 0 else e
            comment_lines.add(line)
            blank(i, e)
            i = e
        elif src.startswith("/*", i):
            e = src.find("*/", i + 2)
            e = n if e < 0 else e + 2
            for ln in range(line, line + src.count("\n", i, e) + 1):
                comment_lines.add(ln)
            line += src.count("\n", i, e)
            blank(i, e)
            i = e
        elif ch in "\"'":
            # retezec / znak (R"(...)" raw retezce v PA1 nepotkame)
            j = i + 1
            while j < n and src[j] != ch and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            blank(i + 1, min(j, n))
            i = j + 1
        else:
            i += 1
    return "".join(out), comment_lines, skipped


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _match_paren(text: str, i: int) -> int:
    depth = 0
    for k in range(i, len(text)):
        if text[k] == "(":
            depth += 1
        elif text[k] == ")":
            depth -= 1
            if depth == 0:
                return k
    return -1


# ---------------------------------------------------------------- funkce

_NAME_RE = re.compile(r"(operator\s*[^\s(]+|~?[A-Za-z_]\w*(?:\s*::\s*~?[A-Za-z_]\w*)*)\s*\(")


def _function_header(header: str):
    """(jmeno, parametry) pokud je text pred { hlavicka definice funkce, jinak None."""
    h = header.strip()
    if not h or "=" in h.split("(")[0]:
        return None
    m = _NAME_RE.search(h)
    if not m:
        return None
    name = re.sub(r"\s+", "", m.group(1))
    if name.split("::")[-1] in KEYWORDS:
        return None
    pre = h[:m.start()].strip()
    if pre and not re.fullmatch(r"[\w\s\*&:<>,~\[\]]*", pre):
        return None
    close = _match_paren(h, m.end() - 1)
    if close < 0:
        return None
    params = h[m.end():close].strip()
    rest = h[close + 1:].strip()
    # za ) smi byt jen const/noexcept/override/-> typ/inicializace konstruktoru
    if rest and not re.match(r"(const|noexcept|override|final|->|:|throw|&|mutable)", rest):
        return None
    if params in ("", "void"):
        nparams = 0
    else:
        depth, nparams = 0, 1
        for ch in params:
            depth += ch in "(<["
            depth -= ch in ")>]"
            nparams += ch == "," and depth == 0
    return name, nparams


def _container(header: str) -> bool:
    h = header.strip()
    return "=" not in h and "(" not in h and (
        re.search(r"\b(namespace|class|struct|union)\b", h) is not None or h == "extern")


def find_functions(code: str, comment_lines: set[int]) -> tuple[list[Function], list[tuple[int, str]]]:
    """Definice funkci a globalni promenne [(radek, text)]."""
    functions, globals_ = [], []
    stack = []            # druhy otevrenych bloku: container | function | other
    boundary = [0]        # zacatek aktualniho prikazu na kazde urovni
    last_header = [""]    # hlavicka posledniho uzavreneho bloku na kazde urovni (typedef struct ...)
    i, n = 0, len(code)
    lines = code.split("\n")
    while i < n:
        ch = code[i]
        in_container = all(k == "container" for k in stack)
        if ch == "{":
            header = code[boundary[-1]:i]
            kind = "other"
            if in_container:
                fh = _function_header(header)
                if fh:
                    kind = "function"
                    end = _block_end(code, i)
                    name, nparams = fh
                    hstart = boundary[-1] + len(header) - len(header.lstrip())
                    hline, eline = _line_of(code, hstart), _line_of(code, end)
                    body = code[i:end + 1]
                    functions.append(Function(
                        name, hline, eline,
                        sum(1 for ln in lines[hline - 1:eline] if ln.strip() not in ("", "{", "}")),
                        nparams, _cyclomatic(body), _nesting(body),
                        _has_comment(lines, comment_lines, hline, eline)))
                    i = end + 1
                    boundary[-1] = i
                    last_header[-1] = header
                    continue
                if _container(header):
                    kind = "container"
            stack.append(kind)
            boundary.append(i + 1)
            last_header.append(header)
        elif ch == "}":
            if stack:
                stack.pop()
                boundary.pop()
                hdr = last_header.pop()
                boundary[-1] = i + 1
                last_header[-1] = hdr
        elif ch == ";":
            if not stack:  # globalni promenne jen na nejvyssi urovni (ne clenske promenne trid)
                stmt = code[boundary[-1]:i]
                g = _global_var(stmt, last_header[-1])
                if g:
                    globals_.append((_line_of(code, boundary[-1] + len(stmt) - len(stmt.lstrip())), g))
                last_header[-1] = ""
            boundary[-1] = i + 1
        i += 1
    return functions, globals_


def _block_end(code: str, i: int) -> int:
    depth = 0
    for k in range(i, len(code)):
        if code[k] == "{":
            depth += 1
        elif code[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return len(code) - 1


def _cyclomatic(body: str) -> int:
    return (1 + len(re.findall(r"\b(if|for|while|case|catch)\b", body))
            + body.count("&&") + body.count("||") + body.count("?"))


def _nesting(body: str) -> int:
    """Nejvetsi pocet do sebe vnorenych bloku uvnitr tela funkce (telo samo = 0)."""
    depth = best = 0
    for ch in body:
        if ch == "{":
            depth += 1
            best = max(best, depth)
        elif ch == "}":
            depth -= 1
    return max(0, best - 1)


def _has_comment(lines, comment_lines, hline, eline) -> bool:
    """Komentar tesne nad hlavickou (prazdne radky se preskoci) nebo na prvnich radcich tela."""
    k = hline - 1
    while k >= 1 and not lines[k - 1].strip() and k not in comment_lines:
        k -= 1
    if k >= 1 and k in comment_lines:
        return True
    return any(ln in comment_lines for ln in range(hline, min(eline, hline + 2) + 1))


def _global_var(stmt: str, prev_header: str) -> str | None:
    s = " ".join(stmt.split())
    if not s:
        return None
    if prev_header.strip().startswith("typedef") or re.match(r"(typedef|using|template|extern|static_assert|"
                                                              r"friend|namespace)\b", s):
        return None
    if re.search(r"\b(const|constexpr)\b", s.split("=")[0]) and "*" not in s.split("=")[0]:
        return None
    before_eq = s.split("=")[0]
    if "(" in before_eq and not re.search(r"\(\s*\*", before_eq):
        return None  # prototyp funkce
    if prev_header and re.fullmatch(r"[\w\s,\*\[\]]*", s) is None:
        return None
    if prev_header and not re.search(r"\b(struct|union|class)\b", prev_header):
        return None
    if not re.search(r"[A-Za-z_]\w*\s*(\[[^\]]*\]\s*)*$", before_eq.strip()):
        return None
    if not prev_header and not re.match(r"[\w:<>]+[\s\*&]+", s):
        return None  # samotny identifikator / neco divneho
    return s[:80]


# ---------------------------------------------------------------- dalsi kontroly

def _magic_numbers(code: str, functions) -> dict[str, int]:
    """Cislo -> prvni radek, kde se v tele funkce objevi (mimo povolene male hodnoty)."""
    found = {}
    lines = code.split("\n")
    for f in functions:
        for ln in range(f.line, f.end_line + 1):
            text = lines[ln - 1]
            for m in re.finditer(r"(?<![\w.])(\d+\.?\d*(?:[eE][-+]?\d+)?)[uUlLfF]*(?![\w.])", text):
                num = m.group(1)
                if num not in ALLOWED_NUMBERS:
                    found.setdefault(num, ln)
    return found


_TRIVIAL = re.compile(r"[{}();\s]*|(break|continue|else|return\s*\w*|default\s*:)\s*;?\s*[{}]*")


def _duplicates(code: str, functions) -> list[tuple[int, int, int]]:
    """Dvojice stejnych bloku kodu [(radek1, radek2, delka)] - kandidati na vlastni funkci."""
    lines = code.split("\n")
    items = []  # (cislo radku, normalizovany text) jen netrivialnich radku v telech funkci
    for f in functions:
        for ln in range(f.line + 1, f.end_line + 1):
            t = " ".join(lines[ln - 1].split())
            if t and not _TRIVIAL.fullmatch(t):
                items.append((ln, t))
    seen, dups, covered = {}, [], set()
    for k in range(len(items) - DUP_WINDOW + 1):
        key = tuple(t for _, t in items[k:k + DUP_WINDOW])
        if key in seen:
            a = seen[key]
            if items[k][0] in covered or k - a < DUP_WINDOW:
                continue
            length = DUP_WINDOW
            while (k + length < len(items) and a + length < k
                   and items[a + length][1] == items[k + length][1]):
                length += 1
            dups.append((items[a][0], items[k][0], length))
            covered.update(ln for ln, _ in items[k:k + length])
        else:
            seen[key] = k
    return dups


def _naming(functions) -> dict[str, list[str]]:
    styles = {}
    for f in functions:
        name = f.name.split("::")[-1]
        if name == "main" or name.startswith("~") or name.startswith("operator"):
            continue
        if "_" in name.strip("_") and name.lower() == name:
            styles.setdefault("snake_case", []).append(name)
        elif re.match(r"[a-z]+[A-Z]", name) and "_" not in name:
            styles.setdefault("camelCase", []).append(name)
        elif re.match(r"[A-Z][a-z]+[A-Z]?", name) and "_" not in name:
            styles.setdefault("PascalCase", []).append(name)
        elif "_" in name and re.search(r"[A-Z]", name) and re.search(r"[a-z]", name):
            styles.setdefault("smisene", []).append(name)
    return styles


# ---------------------------------------------------------------- externi nastroje

# rady, ktere davaji smysl jen pro C++ idiomy - u souboru .c (C prekladane jako C++) je vynechame
CPP_ONLY_CPPCHECK = {"passedByValue", "cstyleCast", "useStlAlgorithm", "useInitializationList",
                     "noExplicitConstructor", "postfixOperator", "passedByValueCallback"}


def _is_c(src: Path) -> bool:
    return src.suffix.lower() == ".c"


def _cppcheck(src: Path, cxx: bool, rep: StyleReport):
    exe = shutil.which("cppcheck")
    if not exe:
        rep.missing_tools.append("cppcheck")
        return
    cmd = [exe, "--enable=warning,style,performance,portability", "--quiet", "--inline-suppr",
           "--suppress=missingIncludeSystem", "-D__PROGTEST__",
           "--template={line}|{severity}|{id}|{message}", f"--language={'c++' if cxx else 'c'}", src.name]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=src.parent, timeout=60)
    except subprocess.TimeoutExpired:
        return
    rep.tools.append("cppcheck")
    for ln in p.stderr.splitlines():
        parts = ln.split("|", 3)
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        line, sev, ident, msg = parts
        if ident in ("missingInclude", "checkersReport", "unmatchedSuppression"):
            continue
        if _is_c(src) and ident in CPP_ONLY_CPPCHECK:
            continue
        bug = sev in ("error", "warning")
        rep.add(MAJOR if bug else MINOR, f"cppcheck:{ident}", int(line), f"[cppcheck {sev}] {msg}", bug)


TIDY_CHECKS = ",".join([
    "-*", "bugprone-*", "-bugprone-easily-swappable-parameters", "-bugprone-narrowing-conversions",
    "readability-else-after-return", "readability-inconsistent-declaration-parameter-name",
    "readability-misleading-indentation", "readability-redundant-*", "readability-duplicate-include",
    "readability-function-cognitive-complexity", "misc-unused-*", "performance-*",
])


def _clang_tidy(src: Path, cxx: bool, rep: StyleReport):
    exe = shutil.which("clang-tidy")
    if not exe:
        rep.missing_tools.append("clang-tidy")
        return
    std = ["-x", "c++", "-std=c++20"] if cxx else ["-x", "c", "-std=c11"]
    checks = TIDY_CHECKS + (",-performance-unnecessary-value-param,-performance-enum-size" if _is_c(src) else "")
    cmd = [exe, f"-checks={checks}", "-config={CheckOptions: "
           "{readability-function-cognitive-complexity.Threshold: 25}}", src.name, "--", *std, "-D__PROGTEST__"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=src.parent, timeout=120)
    except subprocess.TimeoutExpired:
        return
    rep.tools.append("clang-tidy")
    for m in re.finditer(r"^(?:.*[/\\])?" + re.escape(src.name) + r":(\d+):\d+: (warning|error): (.*?) \[([\w.,-]+)\]$",
                         p.stdout, re.MULTILINE):
        line, sev, msg, check = m.groups()
        if check.startswith("clang-diagnostic"):
            continue  # chyby/varovani prekladace hlasi uz kompilace
        bug = sev == "error" or check.startswith(("bugprone", "cert"))
        rep.add(MAJOR if bug else MINOR, f"clang-tidy:{check}", int(line), f"[clang-tidy] {msg} ({check})", bug)


# ---------------------------------------------------------------- hlavni kontrola

def check(src: Path, cxx: bool = True, external: bool = True) -> StyleReport:
    """cxx = preklada se jako C++ (progtest preklada g++ i soubory .c)."""
    text = src.read_text(errors="replace").replace("\r\n", "\n")
    code, comment_lines, skipped = clean(text)
    rep = StyleReport(src)
    rep.code_lines = sum(1 for ln in code.split("\n") if ln.strip())
    functions, globals_ = find_functions(code, comment_lines)
    rep.functions = functions

    # funkce
    for f in functions:
        if f.lines > FUNC_LINES[0]:
            bad = f.lines > FUNC_LINES[1]
            rep.add(MAJOR if bad else MINOR, "delka", f.line,
                    f"funkce {f.name} ma {f.lines} radku (doporuceno nejvys {FUNC_LINES[0]}) - rozdel ji na mensi")
        if f.cyclomatic > CYCLOMATIC[0]:
            bad = f.cyclomatic > CYCLOMATIC[1]
            rep.add(MAJOR if bad else MINOR, "vetveni", f.line,
                    f"funkce {f.name} ma {f.cyclomatic} cest kodem (if/for/while/case/&&/||; doporuceno nejvys "
                    f"{CYCLOMATIC[0]}) - vyclen casti do pomocnych funkci")
        if f.nesting > NESTING[0]:
            bad = f.nesting > NESTING[1]
            rep.add(MAJOR if bad else MINOR, "zanoreni", f.line,
                    f"funkce {f.name} ma bloky zanorene {f.nesting} hluboko (doporuceno nejvys {NESTING[0]}) - "
                    f"pomuze vycleneni funkce nebo predcasny return/continue")
        if f.params > PARAMS:
            rep.add(MINOR, "parametry", f.line,
                    f"funkce {f.name} ma {f.params} parametru (doporuceno nejvys {PARAMS}) - zvaz strukturu")
    real = [f for f in functions if f.name != "main"]
    main = next((f for f in functions if f.name == "main"), None)
    if main and not real and main.lines > 40:
        rep.add(SEVERE, "jen-main", main.line,
                f"cely program je v jedne funkci main ({main.lines} radku) - rozdel ho na funkce")
    long_ones = [f for f in functions if f.lines >= 10 and f.name != "main"]  # main se vysvetluje sam
    undocumented = [f for f in long_ones if not f.commented]
    if long_ones and len(undocumented) * 2 > len(long_ones):
        rep.add(MINOR, "komentare", undocumented[0].line,
                f"{len(undocumented)} z {len(long_ones)} delsich funkci nema komentar, co dela: "
                + ", ".join(f.name for f in undocumented[:5]))

    # soubor
    for line, g in globals_[:MAX_SAME]:
        rep.add(MAJOR, "globalni", line, f"globalni promenna: {g!r} - predavej data parametry "
                                         f"(konstanty oznac const nebo #define)")
    for m in re.finditer(r"\bgoto\b", code):
        rep.add(MAJOR, "goto", _line_of(code, m.start()), "goto - pouzij cyklus, break/continue nebo funkci")
    magic = _magic_numbers(code, functions)
    if len(magic) >= MAGIC_MIN:
        ex = ", ".join(f"{k} (r. {v})" for k, v in list(magic.items())[:8])
        rep.add(MINOR, "magicka-cisla", next(iter(magic.values())),
                f"{len(magic)} ruznych magickych cisel v kodu: {ex}{', ...' if len(magic) > 8 else ''} - "
                f"pojmenuj je (#define / const)")
    for a, b, length in _duplicates(code, functions)[:MAX_SAME]:
        rep.add(MINOR, "duplicita", b, f"radky {b}-{b + length - 1} jsou skoro stejne jako {a}-{a + length - 1} "
                                       f"- vytahni je do funkce")
    styles = _naming(functions)
    if len(styles) > 1:
        rep.add(MINOR, "pojmenovani", None, "jmena funkci michaji styly: " + "; ".join(
            f"{k}: {', '.join(v[:3])}" for k, v in styles.items()) + " - drz se jednoho")
    raw_lines = text.split("\n")
    indents = {("tab" if ln.startswith("\t") else "mezery") for ln in raw_lines
               if ln[:1] in (" ", "\t") and ln.strip() and not ln.lstrip().startswith("*")}
    if len(indents) > 1:
        rep.add(MINOR, "odsazeni", None, "odsazeni micha tabulatory a mezery")
    long_lines = [k for k, ln in enumerate(raw_lines, 1) if len(ln.expandtabs(4)) > LINE_LEN]
    if long_lines:
        rep.add(MINOR, "dlouhe-radky", long_lines[0],
                f"{len(long_lines)} radku delsich nez {LINE_LEN} znaku (napr. r. {', '.join(map(str, long_lines[:3]))})")

    if external:
        _cppcheck(src, cxx, rep)
        _clang_tidy(src, cxx, rep)

    # stejny problem na stejnem radku hlasi nastroje nekdy vickrat (uninitvar + uninitStructMember)
    uniq, keys = [], set()
    for fd in rep.findings:
        tool = fd.rule.split(":")[0]
        key = (fd.line, tool, fd.msg.split("]")[-1].split()[:1] if ":" in fd.rule else fd.rule)
        key = (key[0], key[1], str(key[2]))
        if key not in keys:
            keys.add(key)
            uniq.append(fd)
    rep.findings = uniq

    # body a znamka - stejny druh nalezu se zapocita nejvys MAX_SAME-krat
    counted = {}
    for fd in sorted(rep.style, key=lambda x: -x.weight):
        if counted.get(fd.rule, 0) < MAX_SAME:
            counted[fd.rule] = counted.get(fd.rule, 0) + 1
            rep.points += fd.weight
    rep.density = rep.points / max(1.0, rep.code_lines / 100)
    rep.grade = next((g for limit, g in GRADE_DENSITY if rep.density <= limit), 5)
    rep.findings.sort(key=lambda x: (-x.weight, x.line or 0))
    return rep


GRADE_TEXT = {1: "vyborne", 2: "chvalitebne - par drobnosti", 3: "dobre - stoji za to uklidit",
              4: "dostatecne - cvicici bude mit vyhrady", 5: "nedostatecne - kod je potreba prepsat"}
