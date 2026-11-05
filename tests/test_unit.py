"""Unit testy casti testeru, ktere nepotrebuji prekladac.

Spusteni:  python3 -m unittest discover -s tests      (z korene repozitare)
"""

import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.dont_write_bytecode = True

from pt import complexity, gen, harness, style  # noqa: E402
from pt.checks import Oracle, _eof_hint  # noqa: E402

TEMPLATE = """\
#ifndef __PROGTEST__
#include <stdio.h>
#include <assert.h>
typedef struct { int x; } TItem;
#endif /* __PROGTEST__ */

int f(TItem *it) { return it->x; }

#ifndef __PROGTEST__
int main(void)
{
    TItem a = {1};
    assert(f(&a) == 1);
    return 0;
}
#endif /* __PROGTEST__ */
"""


class GuardedBlocks(unittest.TestCase):
    def test_template(self):
        blocks = harness.guarded_blocks(TEMPLATE)
        self.assertEqual([(b.start, b.end, b.has_main) for b in blocks], [(1, 5, False), (9, 16, True)])
        self.assertTrue(harness.has_test_main(TEMPLATE))

    def test_header_keeps_line_numbers(self):
        hdr = harness.progtest_header(TEMPLATE, "program.c")
        self.assertIn('#line 2 "program.c"', hdr)
        self.assertIn("typedef struct", hdr)
        self.assertNotIn("main", hdr)

    def test_else_branch_and_if_not_defined(self):
        text = ("#if !defined(__PROGTEST__)\nint main(void) { return 0; }\n#else\nint x;\n#endif\n"
                "#ifndef __PROGTEST__ // komentar\n#define DEBUG 1\n#endif\n")
        blocks = harness.guarded_blocks(text)
        self.assertEqual([(b.start, b.end, b.has_main) for b in blocks], [(1, 5, True), (6, 8, False)])
        self.assertEqual(blocks[0].body.strip(), "int main(void) { return 0; }")

    def test_nested_block_belongs_to_outer(self):
        text = "#ifndef __PROGTEST__\n#ifdef X\n#endif\nint main() {}\n#endif\n"
        self.assertEqual(len(harness.guarded_blocks(text)), 1)

    def test_io_task_with_debug_block_is_not_function_task(self):
        text = "#ifndef __PROGTEST__\n#define LOG 1\n#endif\nint main(void) { return 0; }\n"
        self.assertFalse(harness.has_test_main(text))


class AssertLog(unittest.TestCase):
    def test_parse(self):
        log = harness.parse_log("F\t12\tf(1) == 2\t1 == 2\nF\t13\tg()\t\nS\t5\t2\t14\n")
        self.assertEqual((log.passed, log.failed, log.total, log.last_ok), (5, 2, 7, 14))
        self.assertEqual(log.failures[0], harness.Failure(12, "f(1) == 2", "1 == 2"))

    def test_crash_and_timeout(self):
        log = harness.parse_log("C\t11\t23\t22\n")
        self.assertEqual((log.crash_sig, log.crash_at, log.last_ok, log.passed), (11, 23, 22, None))
        log = harness.parse_log("T\t0\t40\n")
        self.assertEqual((log.timeout_at, log.last_ok), (0, 40))

    def test_glibc_fallback(self):
        err = b"test_release: program.c:19: int main(): Assertion `y = twice(0)' failed.\n"
        log = harness.parse_glibc(err)
        self.assertEqual(log.failures, [harness.Failure(19, "y = twice(0)")])


class Fit(unittest.TestCase):
    @staticmethod
    def points(pairs):
        return [complexity.Point(n, t, 0) for n, t in pairs]

    def test_quadratic_with_startup_noise(self):
        # skutecne mereni: 6 bodu je jen startovni sum, signal je az v poslednich dvou
        pts = self.points([(1, .0023), (4, .0023), (32, .0024), (128, .0034), (1024, .0043),
                           (4096, .0115), (32768, .1077), (131072, 1.66)])
        self.assertEqual(complexity.fit(pts).cls, "n^2")

    def test_linear(self):
        pts = self.points([(1, .0023), (4, .0023), (32, .0024), (128, .0025), (1024, .003),
                           (4096, .005), (32768, .02), (131072, .075), (524288, .3)])
        self.assertEqual(complexity.fit(pts).cls, "n")

    def test_n_log_n(self):
        ns = [4 ** i for i in range(11)]
        pts = self.points([(n, .002 + 2e-8 * n * math.log2(n)) for n in ns])
        self.assertEqual(complexity.fit(pts).cls, "n log n")

    def test_flat(self):
        pts = self.points([(2 ** i, .002 + .0005 * (i % 2)) for i in range(10)])
        self.assertTrue(complexity.fit(pts).flat)


class Checks(unittest.TestCase):
    def test_eof_hint(self):
        exp = b"Zadejte cisla:\nSoucet: 1\n"
        self.assertIn("EOF", _eof_hint(exp, exp + b"Nespravny vstup.\n"))
        self.assertEqual(_eof_hint(exp, b"Zadejte cisla:\nSoucet: 2\n"), "")

    def test_oracle_templates(self):
        o = Oracle.from_outputs([b"Soucet: 6\n", b"Soucet: 13\n"])
        self.assertTrue(o.line_known("Soucet: 12345"))
        self.assertFalse(o.line_known("Soucte: 1"))
        self.assertEqual(o.closest("Soucte: 6"), "Soucet: 6")

    def test_sample_groups(self):
        self.assertEqual(gen.sample_group("basic", ("basic", "CZE"))[0], "basic")
        self.assertEqual(gen.sample_group("extra", ("extra", "CZE"))[1], gen.G_EXTRA)


class Style(unittest.TestCase):
    def check(self, code: str, suffix=".c"):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / f"program{suffix}"
            p.write_text(code)
            return style.check(p, cxx=True, external=False)

    def test_clean_code_gets_good_grade(self):
        code = ("#include <stdio.h>\n\n/* Secte dve cisla. */\nint add(int a, int b)\n{\n"
                "    return a + b;\n}\n\nint main(void)\n{\n    printf(\"%d\\n\", add(1, 2));\n"
                "    return 0;\n}\n")
        rep = self.check(code)
        self.assertEqual([f.name for f in rep.functions], ["add", "main"])
        self.assertLessEqual(rep.grade, 2)

    def test_long_complex_function_is_flagged(self):
        body = "".join(f"    if (x == {i}) {{ y += {i}; }} else {{ y -= 1; }}\n" for i in range(60))
        code = f"int g;\nint f(int x)\n{{\n    int y = 0;\n{body}    goto end;\nend:\n    return y;\n}}\n"
        rep = self.check(code)
        f = rep.functions[0]
        self.assertGreater(f.lines, style.FUNC_LINES[0])
        self.assertGreater(f.cyclomatic, style.CYCLOMATIC[1])
        rules = {fd.rule for fd in rep.findings}
        self.assertTrue({"goto", "globalni", "delka", "vetveni"} <= rules, rules)
        self.assertGreaterEqual(rep.grade, 3)

    def test_progtest_block_is_ignored(self):
        rep = self.check(TEMPLATE)
        self.assertEqual([f.name for f in rep.functions], ["f"])


if __name__ == "__main__":
    unittest.main()
