"""End-to-end testy: cely tester na malych programech se znamou chybou (tests/fixtures/).

Spusteni:  python3 -m unittest discover -s tests      (z korene repozitare)
           PT_FAST=1 python3 -m unittest discover -s tests   bez odhadu slozitosti (~40 s mene)

Fixtures:
  io_sum/   uloha se vstupem: cte cisla do konce vstupu a vypisuje prubezny soucet
            (ok.c spravne, ostatni se znamou chybou - viz komentar na zacatku souboru)
  func/     uloha "napis funkci": main() s asserty v #ifndef __PROGTEST__
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
IO, FUNC = FIX / "io_sum", FIX / "func"
FAST = bool(os.environ.get("PT_FAST"))
HAS_VALGRIND = shutil.which("valgrind") is not None


def tester(task: Path, src: str, *args, timeout=300) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="pt_e2e_") as out:
        env = dict(os.environ, NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, str(ROOT / "progtest.py"), str(task), "--src", str(task / src),
                            "--out", out, *args], capture_output=True, text=True, timeout=timeout, env=env)
    return p.returncode, p.stdout + p.stderr


class IoTask(unittest.TestCase):
    QUICK = ("--no-style", "--no-complexity", "--fuzz", "30", "--show", "1")

    def test_correct_program_passes(self):
        code, out = tester(IO, "ok.c", *self.QUICK)
        self.assertEqual(code, 0, out)
        self.assertIn("Zakladni test (vzorova data): 4/4", out)
        self.assertRegex(out, r" 0 chyb z \d+ testu")

    def test_eof_as_error_is_explained(self):
        code, out = tester(IO, "eof_bug.c", *self.QUICK)
        self.assertEqual(code, 1, out)
        self.assertIn("program bere konec vstupu (EOF) jako chybu", out)

    def test_heap_overflow_found_by_asan(self):
        code, out = tester(IO, "overflow.c", *self.QUICK)
        self.assertEqual(code, 1, out)
        self.assertIn("heap-buffer-overflow", out)
        self.assertIn("overflow.c:12", out)

    @unittest.skipUnless(HAS_VALGRIND, "neni valgrind")
    def test_uninitialized_found_by_valgrind(self):
        code, out = tester(IO, "uninit.c", "--no-style", "--no-complexity", "--only-samples", "--valgrind")
        self.assertEqual(code, 1, out)
        self.assertIn("[valgrind]", out)
        self.assertIn("uninitialised", out)
        self.assertIn("uninit.c:7", out)  # misto alokace

    def test_missing_main(self):
        code, out = tester(IO, "nomain.c")
        self.assertEqual(code, 2, out)
        self.assertIn("program nema funkci main()", out)

    def test_style_grade(self):
        code, out = tester(IO, "ok.c", "--only-style")
        self.assertEqual(code, 0, out)
        m = re.search(r"Stabni kultura kodu: znamka (\d)", out)
        self.assertIsNotNone(m, out)
        self.assertLessEqual(int(m.group(1)), 2, out)


@unittest.skipIf(FAST, "PT_FAST")
class Complexity(unittest.TestCase):
    def grade(self, src):
        code, out = tester(IO, src, "--no-style", "--only-complexity")
        m = re.search(r"Odhad slozitosti: znamka (\d)", out)
        self.assertIsNotNone(m, out)
        return int(m.group(1)), out

    def test_quadratic_is_detected(self):
        grade, out = self.grade("quadratic.c")
        self.assertIn("namereno O(n^2)", out)
        self.assertGreaterEqual(grade, 3, out)

    def test_linear_is_fine(self):
        grade, out = self.grade("ok.c")
        self.assertNotIn("O(n^2)", out)
        self.assertEqual(grade, 1, out)


class FunctionTask(unittest.TestCase):
    def run_func(self, src, *args):
        return tester(FUNC, src, "--no-style", *args)

    def test_all_asserts_pass(self):
        code, out = self.run_func("ok.c")
        self.assertEqual(code, 0, out)
        self.assertIn('Uloha "napis funkci"', out)
        self.assertIn("Asserty ze zadani: 5/5 proslo", out)

    def test_failed_asserts_show_values_and_continue(self):
        code, out = self.run_func("fail.c")
        self.assertEqual(code, 1, out)
        self.assertIn("Asserty ze zadani: 7/10 proslo", out)
        self.assertIn("r. 31: assert(absVal(-5) == 5)", out)
        self.assertIn("hodnoty: -5 == 5", out)
        self.assertIn("hodnoty: -7 == 7", out)            # prvni nesplnena cast &&
        self.assertIn("hodnoty: 0.30000000000000004 == 0.3", out)
        self.assertNotIn("nejdou rozlozit", out)           # vsechny tvary vyrazu se prelozily

    def test_c_mode_counts_without_values(self):
        code, out = self.run_func("fail.c", "--cc", "gcc")
        self.assertEqual(code, 1, out)
        self.assertIn("Asserty ze zadani: 7/10 proslo", out)
        self.assertNotIn("hodnoty:", out)

    def test_crash_reports_assert_line(self):
        code, out = self.run_func("crash.c")
        self.assertEqual(code, 1, out)
        self.assertIn("program spadl (SIGSEGV) pri assertu na r. 23", out)
        self.assertIn("load of null pointer", out)         # UBSan
        self.assertIn("getItem(int const*, int) crash.c:12", out)

    def test_leak(self):
        code, out = self.run_func("leak.c")
        self.assertEqual(code, 1, out)
        self.assertIn("LeakSanitizer", out)

    def test_helper_only_in_test_block(self):
        code, out = self.run_func("guard_helper.c")
        self.assertEqual(code, 1, out)
        self.assertIn("na progtestu nebudou definovane: square(int)", out)

    def test_timeout_reports_assert_line(self):
        code, out = self.run_func("timeout.c", "--timeout", "0.5")
        self.assertEqual(code, 1, out)
        self.assertIn("prekrocen casovy limit 0.5 s pri assertu na r. 23", out)

    def test_cpp_strings_and_uncaught_exception(self):
        code, out = self.run_func("cpp.cpp")
        self.assertEqual(code, 1, out)
        self.assertIn('hodnoty: "b" == "a"', out)
        self.assertIn("nezachycena vyjimka std::logic_error: empty stack", out)
        self.assertIn("pri assertu na r. 36", out)

    def test_fallback_to_standard_assert(self):
        code, out = self.run_func("fallback.c")
        self.assertEqual(code, 1, out)
        self.assertIn("nejdou rozlozit", out)
        self.assertIn("r. 19: assert(y = twice(0))", out)


if __name__ == "__main__":
    unittest.main()


class OutDir(unittest.TestCase):
    def run_with_out(self, out: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ, NO_COLOR="1", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, str(ROOT / "progtest.py"), str(IO), "--src", str(IO / "ok.c"),
                               "--out", str(out), "--only-style"], capture_output=True, text=True,
                              timeout=120, env=env)

    def test_foreign_dir_is_not_deleted(self):
        with tempfile.TemporaryDirectory(prefix="pt_e2e_") as d:
            keep = Path(d) / "reseni.c"
            keep.write_text("int main(void) { return 0; }\n")
            p = self.run_with_out(Path(d))
            self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("nevytvoril ji tester", p.stderr)
            self.assertTrue(keep.exists())

    def test_own_dir_is_reused(self):
        with tempfile.TemporaryDirectory(prefix="pt_e2e_") as d:
            out = Path(d) / "vysledky"
            for _ in range(2):  # podruhe uz slozka existuje, ale ma znacku testeru
                p = self.run_with_out(out)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertTrue((out / ".progtester_vysledky").exists())
