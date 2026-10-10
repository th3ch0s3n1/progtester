"""Spousteni programu v omezenem prostredi (cas, pamet, velikost vystupu)."""

import resource
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

MB = 1024 * 1024
MAX_OUTPUT = 16 * MB


@dataclass
class RunResult:
    stdout: bytes
    stderr: bytes
    returncode: int
    timed_out: bool
    duration: float

    @property
    def signal_name(self):
        if self.returncode < 0:
            try:
                return signal.Signals(-self.returncode).name
            except ValueError:
                return f"signal {-self.returncode}"
        return None


def _limits(mem_mb, cpu_s):
    def apply():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
        if mem_mb:
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * MB, mem_mb * MB))
    return apply


def run(binary: Path, data: bytes, timeout: float, mem_mb: int | None = None, env=None) -> RunResult:
    # stdin/stdout pres soubory: zadny deadlock na velkych vstupech a nekonecny
    # vypis skonci na RLIMIT_FSIZE misto zaplneni pameti testeru
    with tempfile.TemporaryDirectory(prefix="pt_") as td:
        fin, fout, ferr = (Path(td) / n for n in ("in", "out", "err"))
        fin.write_bytes(data)
        with open(fin, "rb") as i, open(fout, "wb") as o, open(ferr, "wb") as e:
            start = time.monotonic()
            p = subprocess.Popen([str(binary)], stdin=i, stdout=o, stderr=e, env=env,
                                 preexec_fn=_limits(mem_mb, int(timeout) + 1),
                                 start_new_session=True)
            timed_out = False
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                p.kill()
                p.wait()
            dur = time.monotonic() - start
        return RunResult(fout.read_bytes(), ferr.read_bytes()[:64 * 1024], p.returncode, timed_out, dur)
