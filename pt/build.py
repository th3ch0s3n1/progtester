"""Kompilace testovaneho programu (release jako progtest + sanitizer build)."""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Funkce, kvuli kterym progtest program vubec nespusti
FORBIDDEN = {
    "system", "popen", "fork", "vfork", "clone", "execl", "execlp", "execle",
    "execv", "execvp", "execvpe", "execve", "fexecve", "posix_spawn",
    "posix_spawnp", "socket", "connect", "bind", "listen", "accept",
    "kill", "ptrace", "dlopen", "chroot", "setuid", "setgid",
}

C_STD = "-std=c11"
CXX_STD = "-std=c++20"
COMMON = ["-Wall", "-pedantic", "-D__PROGTEST__"]
SANITIZE = [
    "-O0", "-g", "-fno-omit-frame-pointer",
    "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
]


@dataclass
class Build:
    ok: bool
    binary: Path
    cmd: list
    output: str  # warningy / chyby kompilatoru


def _compiler(src: Path, cc: str):
    # progtest preklada i C kod pomoci g++ (soubor .c bere g++ jako C++)
    if cc == "g++" or src.suffix in (".cpp", ".cc", ".cxx"):
        return "g++", CXX_STD
    return "gcc", C_STD


def compile_src(src: Path, out: Path, extra: list, cc: str) -> Build:
    cc, std = _compiler(src, cc)
    # spousti se ze slozky zdrojaku, at jsou hlasky kompilatoru kratke
    cmd = [cc, std, *COMMON, *extra, src.name, "-o", str(out), "-lm"]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=src.parent)
    return Build(p.returncode == 0 and out.exists(), out, cmd, p.stderr.strip())


def build_release(src: Path, outdir: Path, strict: bool, cc: str) -> Build:
    extra = ["-O2", "-Wextra"] + (["-Werror"] if strict else [])
    return compile_src(src, outdir / "prog_release", extra, cc)


def build_sanitized(src: Path, outdir: Path, cc: str) -> Build:
    return compile_src(src, outdir / "prog_asan", SANITIZE, cc)


def forbidden_symbols(binary: Path) -> list:
    if not shutil.which("nm"):
        return []
    p = subprocess.run(["nm", "-u", "-D", str(binary)], capture_output=True, text=True)
    if p.returncode != 0:
        p = subprocess.run(["nm", "-u", str(binary)], capture_output=True, text=True)
    found = set()
    for line in p.stdout.splitlines():
        name = line.split()[-1].split("@")[0]
        if name in FORBIDDEN:
            found.add(name)
    return sorted(found)


def find_source(task: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    if task.is_file():
        return task.resolve()
    cands = sorted(p for ext in ("*.c", "*.cpp") for p in task.glob(ext))
    for pref in ("program.c", "main.c", "program.cpp", "main.cpp"):
        for c in cands:
            if c.name == pref:
                return c
    if len(cands) == 1:
        return cands[0]
    if not cands:
        raise SystemExit(f"V {task} neni zadny .c/.cpp soubor (pouzij --src).")
    raise SystemExit(f"V {task} je vic zdrojaku ({', '.join(c.name for c in cands)}), vyber --src.")


def asan_env() -> dict:
    env = dict(os.environ)
    env["ASAN_OPTIONS"] = "detect_leaks=1:abort_on_error=0:exitcode=86:allocator_may_return_null=1"
    env["UBSAN_OPTIONS"] = "print_stacktrace=1:halt_on_error=1:exitcode=87"
    return env
