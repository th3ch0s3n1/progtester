"""Spousteni programu v omezenem prostredi (cas, pamet, velikost vystupu)."""

import os
import resource
import signal
import subprocess
import tempfile
import threading
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
    duration: float       # realny cas [s]
    cpu: float = 0.0      # user + sys CPU cas [s]

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


def run(cmd, data: bytes, timeout: float, mem_mb: int | None = None, env=None) -> RunResult:
    """`cmd` je cesta k binarce nebo cely prikaz (seznam), napr. [valgrind, ..., binarka]."""
    argv = [str(x) for x in cmd] if isinstance(cmd, (list, tuple)) else [str(cmd)]
    # stdin/stdout pres soubory: zadny deadlock na velkych vstupech a nekonecny
    # vypis skonci na RLIMIT_FSIZE misto zaplneni pameti testeru
    with tempfile.TemporaryDirectory(prefix="pt_") as td:
        fin, fout, ferr = (Path(td) / n for n in ("in", "out", "err"))
        fin.write_bytes(data)
        with open(fin, "rb") as i, open(fout, "wb") as o, open(ferr, "wb") as e:
            start = time.monotonic()
            p = subprocess.Popen(argv, stdin=i, stdout=o, stderr=e, env=env,
                                 preexec_fn=_limits(mem_mb, int(timeout) + 1),
                                 start_new_session=True)
            # wait4 misto p.wait(): vrati i CPU cas prave tohoto procesu (ru_maxrss nepouzivame -
            # po fork() v nem zustava pamet testeru)
            lock, state = threading.Lock(), {"done": False, "killed": False}

            def kill():
                with lock:
                    if not state["done"]:
                        state["killed"] = True
                        try:
                            os.killpg(p.pid, signal.SIGKILL)  # i s potomky (valgrind)
                        except ProcessLookupError:
                            pass

            timer = threading.Timer(timeout, kill)
            timer.start()
            _, status, ru = os.wait4(p.pid, 0)
            with lock:
                state["done"] = True
            timer.cancel()
            dur = time.monotonic() - start
            p.returncode = os.waitstatus_to_exitcode(status)
        return RunResult(fout.read_bytes(), ferr.read_bytes()[:64 * 1024], p.returncode,
                         state["killed"], dur, ru.ru_utime + ru.ru_stime)
