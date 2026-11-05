<div align="center">

# 🧪 progtester

**A local Progtest simulator that tries to break your program.**

![Python](https://img.shields.io/badge/python-%E2%89%A5%203.10-3776AB?logo=python&logoColor=white)
![g++](https://img.shields.io/badge/g%2B%2B-C%2B%2B20-00599C?logo=cplusplus&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

[🇨🇿 Čeština](README.md) · 🇬🇧 English

</div>

---

Compiles your program the way Progtest does, runs the sample data through it, and then tries to break it.
The tester **does not know the solution to any task** – for generated inputs it only checks things that always hold.

```sh
python3 progtester/progtest.py 01_task                 # full test
python3 progtester/progtest.py 01_task --only-samples  # samples only
python3 progtester/progtest.py 01_task --fuzz 2000 --seed 42 --show 10
python3 progtester/progtest.py 01_task --valgrind         # + checks under valgrind
python3 progtester/progtest.py 01_task --only-complexity  # complexity estimate only
```

## 📑 Contents

- [Installation](#-installation)
- [What it does](#-what-it-does)
- [What is checked for inputs without a known output](#-what-is-checked-for-inputs-without-a-known-output)
- ["Write a function" tasks](#-write-a-function-tasks)
- [Code style](#-code-style)
- [Valgrind](#-valgrind)
- [Complexity estimate](#-complexity-estimate)
- [Custom tests](#-custom-tests)
- [Results](#-results)
- [Options](#%EF%B8%8F-options)
- [Tester's own tests](#%EF%B8%8F-testers-own-tests)

## 📦 Installation

There is nothing to install. You only need `python3` (≥ 3.10) and `g++`. `--valgrind` needs `valgrind` (`apt install valgrind`); `cppcheck` and `clang-tidy` extend the code check.

```sh
git clone https://github.com/th3ch0s3n1/progtester.git
```

Place the `progtester` folder next to your task folders. **Every task must have its own folder** – it holds the source code of your solution and the sample data:

```
.
├── progtester/
│   └── progtest.py
├── 01_task/              ← one task = one folder
│   ├── main.cpp          ← your solution
│   └── sample/           ← sample data from Progtest
│       ├── CZE/
│       └── ENG/
├── 02_another_task/
│   ├── main.cpp
│   └── sample/
└── ...
```

### 📥 Sample data

The tester does not know the sample data – you have to **download it from the task page on Progtest** (the **Download** button on the "Vzorová data" / sample data row):

![The Download button for sample data on Progtest](vzorova_data.png)

Extract the downloaded archive into the `sample/` folder inside that task's directory (see the tree above).

Some tasks split their sample data into **suites** – `sample/basic/{CZE,ENG}` (mandatory tests)
and `sample/extra/{CZE,ENG}` (the optional test, usually long inputs that a slow algorithm will not finish).
The tester detects them and reports each suite separately:

```
FAIL Zakladni test (vzorova data): 4/8 OK, 4 chyb
FAIL Nepovinny test (vzorova data extra): 0/11 OK, 11 chyb
...
== Shrnuti
   FAIL Zakladni test (vzorova data): 4/8
   FAIL Nepovinny test (vzorova data extra): 0/11
```

`bonus*` subfolders are reported as bonus tests, any other name as "Vzorova data <name>".
Selected suites only: `--suite basic` (repeatable). `*_out_win.txt` files (Windows line endings) are ignored.

## 🔍 What it does

1. **Compilation** – `g++ -std=c++20 -Wall -pedantic -Wextra -O2 -D__PROGTEST__`
   - `--strict` adds `-Werror`.
   - Progtest compiles C code as C++ too – e.g. `int *p = malloc(...)` without a cast fails here as well. `--cc gcc` compiles a `.c` file as C (`gcc -std=c11`).
   - Checks for forbidden functions (`system`, `fork`, `exec*`, …) – Progtest refuses to run programs that use them.
   - If the program has no `main()` with `-D__PROGTEST__` and there is one inside `#ifndef __PROGTEST__`,
     it is a ["write a function" task](#-write-a-function-tasks) and is tested differently.
   - A second build with `-O0 -fsanitize=address,undefined` hunts for memory errors.
   - With `--valgrind`, a third `-O0 -g` build for [valgrind](#-valgrind).
   - [Code style](#-code-style) – function length and complexity, global variables, cppcheck, clang-tidy, … with a grade.
2. **Basic test** – every `*_in.txt` / `*_out.txt` pair from `<task>/sample/**` and `<task>/tests/**`
   (only folders of the language selected by `--lang`, default `CZE`; use `--lang ENG` or `--lang all`).
   Output is compared byte by byte; on a mismatch a diff is printed with visible `\n`, spaces, etc.
   The program reads its input **from a file** as on Progtest, so the input always ends with end-of-file (EOF).
   When testing by hand in a terminal, send it with **Ctrl+D** – otherwise the program just waits and you will not
   see an error at the end of input (typically an extra `Nespravny vstup.`). The tester points this case out.
3. **Breaking tests** (inputs derived from the sample data):

   | Group | What is tried |
   |---|---|
   | Whitespace | missing/extra `\n`, spaces at the start and end of lines (warning only – the output is expected to match the sample) |
   | Boundary values | numbers in the input replaced with `INT_MAX`, `INT_MAX+1`, `-0`, `+N`, `000N`, forty 9s, … (for decimal tasks also `1e-300`, `4.9e-324`, `1e309`, `inf`, `nan`, …) |
   | Decimal numbers | decimal tasks only: every number of a sample multiplied by `1e±6` … `1e±300` (`1.44 + 2.55 = 4` → `0.00000000000144 + 0.00000000000255 = 0.000000000004`) – the output may only change by its numbers being rescaled; a control run at `1e+3` detects tasks where this does not hold (`*`, `/`). Catches absolute epsilons and `%.2f`. Also `1.5` → `1.50`, `15e-1`, `0.15e1` (output must stay the same) |
   | Invalid input | `abc`, `1.23`, `1abc`, `0x1`, empty input, `\0`, UTF-8, `\r\n`, … |
   | Truncated input | EOF at every position |
   | Large input | 1 MB of spaces/zeros/garbage, 100k digits |
   | Fuzz | random mutations, reproducible via `--seed` |

## ✅ What is checked for inputs without a known output

| Level | Check |
|:---:|---|
| ❌ FAIL | crash (SIGSEGV, …), timeout, output > 16 MB, memory limit |
| ❌ FAIL | ASan/UBSan: out-of-bounds read/write, `int` overflow, leak, … |
| ❌ FAIL | `-O2` and `-O0` builds print different output → undefined behaviour |
| ❌ FAIL | valgrind (with `--valgrind`): uninitialised value, invalid read/write, leak |
| ❌ FAIL | empty output, missing trailing `\n`, `\r` in the output, missing prompt (the common first line of the samples) |
| ⚠️ WARN | a line that appears in no sample output (numbers are treated as placeholders) – usually a typo; the closest sample line is suggested |
| ⚠️ WARN | anything on stderr, runtime over half of the time limit |

> [!NOTE]
> The tester **does not decide** which error message belongs to which input – that would amount to solving the task.
> If you have a reference binary (e.g. your own previously accepted solution), use `--ref ./binary`
> and every output will be compared against it exactly.

## 🧷 "Write a function" tasks

In some tasks you submit only functions, not a whole program. The template from the assignment looks like this:

```c
#ifndef __PROGTEST__
#include <stdio.h>
#include <assert.h>
#endif /* __PROGTEST__ */

int dateToIndex(int day, int month, int year, int *idx) { /* your solution */ }

#ifndef __PROGTEST__
int main(void)
{
    int idx;
    assert(dateToIndex(1, 1, 2000, &idx) == 1 && idx == 1);
    ...
}
#endif /* __PROGTEST__ */
```

The tester detects such a task on its own (there is no `main()` with `-D__PROGTEST__`) and instead of sample data:

1. **Compiles the code the way Progtest does** – with `-D__PROGTEST__` and with the headers from the
   `#ifndef __PROGTEST__` blocks (Progtest supplies those itself). It also checks that the code does not
   use a function defined only in the test part – it would be missing on Progtest:
   ```
   FAIL na progtestu nebudou definovane: square(int) - jsou jen v #ifndef __PROGTEST__ ...
   ```
2. **Runs the test `main()` from the assignment** as `-O2`, under ASan/UBSan and under valgrind (if
   installed). It uses its own `assert` ([pt/include/assert.h](pt/include/assert.h)) that:
   - **does not stop the program** at the first failure – you see all failed asserts at once,
   - **prints the values** of both sides of a comparison (for `&&`, the first false part),
   - on a crash or an infinite loop tells you **which assert** it happened in.

```
== Testy z main() v #ifndef __PROGTEST__ (asserty ze zadani)
   FAIL [-O2] selhalo 3 assertu z 10
        r. 31: assert(absVal(-5) == 5)
               hodnoty: -5 == 5
        r. 37: assert(third() == 0.3)
               hodnoty: 0.30000000000000004 == 0.3
   FAIL [-O2] program spadl (SIGSEGV) pri assertu na r. 23
   FAIL [ASan/UBSan] pametova chyba / nedefinovane chovani:
        crash.c:12:17: runtime error: load of null pointer of type 'const int'
          #0 0x.. in getItem(int const*, int) crash.c:12
          #1 0x.. in main crash.c:23
```

Values are shown for numbers, characters, strings (`char *` and `std::string`), pointers (`NULL`) and
anything printable with `operator<<`. It works for C code too, because `g++` compiles it as C++.
With `--cc gcc` (compiled as C) asserts are only counted, without values. When an assert cannot be
decomposed (e.g. an assignment `assert(x = f())`), the standard `assert` is used, which stops at the first failure.

Sample data, generated inputs and the complexity estimate are skipped for these tasks – the program reads no input.
Code style is checked the same way (the test part in `#ifndef __PROGTEST__` is not counted).

## 🧹 Code style

Right after compilation the tester checks the code itself and grades it. C/C++ has no single binding style like
PEP 8 for Python – so it checks what common styles (Linux kernel, Google, CERT) and teachers agree on:

| What | Limit / rule |
|---|---|
| function length | at most 50 lines of code (over 100 is serious) |
| branching (cyclomatic complexity: `if`/`for`/`while`/`case`/`&&`/`\|\|`/`?`) | at most 10 (over 20 is serious) |
| block nesting | at most 3 (over 5 is serious) |
| function parameters | at most 5 |
| the whole program in `main` | severe |
| comment above longer functions (except `main`) | for at least half of them |
| global variables, `goto` | do not use (`const`/`#define` constants are fine) |
| magic numbers | more than 5 distinct numbers (other than 0, 1, 2, 10, 100) → name them |
| duplicated code | 5+ identical lines in two places → extract a function |
| naming | do not mix `snake_case` and `camelCase` |
| indentation, line length | do not mix tabs and spaces, lines up to 120 characters |

Code inside `#ifndef __PROGTEST__ … #endif` (the test `main` from the assignment) is not checked.

If **cppcheck** or **clang-tidy** is installed (`sudo apt install cppcheck clang-tidy`), their findings are added.
The analysis uses the same language Progtest compiles the code as (`.c` as C++), but for `.c` files advice that
only applies to C++ (const references, `std::` algorithms, …) is skipped. cppcheck `error`/`warning` and
clang-tidy `bugprone-*` findings are **probable bugs** (uninitialised variable, leak on `realloc`, overflow in a
multiplication, …) – they are listed separately and do not count toward the style grade.

```
   funkce                           radku  vetveni  zanoreni  param  komentar
   operations_handler                  49       18         2      2  ano
   ...
   Pravdepodobne chyby (staticka analyza):
   WARN r. 110: [cppcheck error] Uninitialized variable: start_time.total_minutes
   WARN r. 464: [clang-tidy] 'a->array' may be set to null if 'realloc' fails, ... (bugprone-suspicious-realloc-usage)

   Styl:
    - odsazeni micha tabulatory a mezery
    - r. 83: funkce operations_handler ma 18 cest kodem (...; doporuceno nejvys 10) - vyclen casti do pomocnych funkci

   -> znamka 3: dobre - stoji za to uklidit (12 trestnych bodu, 3.6 na 100 radku kodu)
```

**Grade:** every finding has penalty points (minor 1, serious 2, everything in `main` 6; the same kind counts at
most 3×). Points are scaled to 100 lines of code (shorter programs count as 100 lines):
≤ 1 → **1**, ≤ 2.5 → **2**, ≤ 4.5 → **3**, ≤ 7 → **4**, otherwise **5**.

## 🔬 Valgrind

ASan/UBSan **do not detect reads of uninitialised memory** (a variable without an initial value, memory from `malloc`/`realloc`).
The typical symptom is that the `-O2` and `-O0` builds print different output, or that the program behaves differently on Progtest than at home.
Valgrind shows the exact spot and where the memory came from:

```
FAIL sample/basic/CZE/0000_in.txt
     - [valgrind] Conditional jump or move depends on uninitialised value(s)
         at operation_calculate_hotel_price(array, time, time) (program.c:341)
         by main (program.c:64)
       Uninitialised value was created by a heap allocation
         at realloc (vg_replace_malloc.c:1804)
         by insert_array(array*, operation) (program.c:464)
```

Valgrind is roughly 50× slower, so it only runs on the sample data plus a random selection of smaller generated
inputs: `--valgrind` = at most 300 inputs, `--valgrind 50` = at most 50.

## 📈 Complexity estimate

After the other tests the tester estimates the program's time complexity – **without knowing the task**, from the
sample data alone. It grows the sample inputs in generic ways and watches how the CPU time grows:

| Growth | Example (`+ 2026-01-01 12:00, 80`) | Ideal |
|---|---|:---:|
| line × n | the same line n times | O(n log n) |
| line × n, number +1 | `+ 2026-…`, `+ 2027-…`, `+ 2028-…` (increasing time, id, …) | O(n log n) |
| element × n | a number plus the separator after it, n times (a sequence on one line) | O(n log n) |
| whole input × n | the whole sample input n times | O(n log n) |
| number + n | `+ 2026-01-01 12:00, [80 + n]` – size of a value (interval length, budget, …) | O(log n) |

- **Validity:** a grown input counts only while the program accepts it – it must not crash or print an error
  message earlier than for the original sample, and its answers must keep growing at the same pace. Where the
  program stops accepting it, the valid range ends (found by bisection) and the time is extrapolated to it. The
  program itself thus "tells" how big the inputs can sensibly get (e.g. years only up to 2999).
- **Selection:** all growths are first measured roughly in parallel; those that measurably slow the program down
  are ranked by how much worse than the ideal they are, and the worst (`--complexity-max`, default 6) are measured
  precisely, one at a time. Growths with the same conclusion are measured once.
- **Model:** the times are fitted with `t = c + a·f(n)` for `f` = 1, log n, n, n log n, n², n³; among the models that
  fit almost equally well, the simplest wins.
- **Crashes** while growing are reported separately (and re-run without the memory limit – this tells whether the
  program just needs too much memory / does not check `NULL` from `malloc`). The input is saved to `vysledky/`.
- **A sudden jump** (flat time, then a steep rise) usually means a variable overflow or an infinite loop.

```
   cislo '# 2000-12-08 23:27, [1163189]' zvetsene o n  (sample/extra/CZE/0000_in.txt:11)  (idealne O(log n))
                n     CPU cas      vstup
                1     23.1 ms       0 kB
              ...
          6.9e10      1.10 s       0 kB
   -> namereno O(n) (nebo O(n log n)), lokalni exponent n^0.96
   -> znamka 4: cas roste s hodnotou cisla jako O(n) a program takovy vstup prijima - pri vetsim n nestihne limit (idealne O(log n))
```

| Grade | Meaning |
|:---:|---|
| 1 | complexity matches the ideal (and fits the limit) |
| 2 | worse than the ideal, but fits the limit within the range the program accepts – can be improved |
| 3 | one class worse than the ideal / good complexity with too large a constant |
| 4 | worse and misses the limit / suspicious jump |
| 5 | orders of magnitude too slow |

> [!NOTE]
> This is an estimate, not a proof. Only what can be derived from the sample data is measured – if a parameter
> never varies in the samples (e.g. they only have a few price changes), the tester may not be able to grow it.
> O(n) and O(n log n) are hard to tell apart by measurement; the tester then prints both.

### Custom generator (optional)

To measure something specific, put `complexity.py` in the task folder (or pass `--complexity FILE`) and the
tester uses it instead of the automatic mode:

```python
TIME_LIMIT = 1.0   # [s] optional, defaults to --timeout

def gen(n):        # returns a VALID input of size n (str or bytes)
    return f"{n}\n" + " ".join(map(str, range(n))) + "\n"

SERIES = [dict(name="number of elements", gen=gen, n_min=16, n_max=1_000_000, target="n log n")]
```

`n_min` = first size (then doubled), `n_max` = the largest `n` on Progtest (the time is extrapolated to it),
`target` = complexity of a good solution (`1`, `log n`, `n`, `n log n`, `n^2`, `n^3`).

## 🧩 Custom tests

Add `NNNN_in.txt` + `NNNN_out.txt` files to `<task>/tests/` – they are treated as additional sample data
(and their outputs extend the set of "known" lines).

## 📂 Results

Every failing input is saved to `progtester/vysledky/<task>/`:

| File | Contents |
|---|---|
| `XXXX_in.txt` | the input |
| `XXXX_out.txt` | your output |
| `XXXX_ref.txt` | the expected output (if known) |
| `XXXX_info.txt` | what went wrong |

Reproduce with: `./a.out < progtester/vysledky/01_task/0003_fail_in.txt`

**Exit code:** `0` = no errors (warnings are fine) · `1` = at least one FAIL · `2` = does not compile / forbidden functions.

## ⚙️ Options

| Option | Default | Description |
|---|:---:|---|
| `--lang CZE\|ENG\|all` | `CZE` | which language folders to test |
| `--timeout S` | `1` | time limit per run in seconds |
| `--mem MB` | `256` | memory limit for the `-O2` build |
| `--fuzz N` | `200` | number of random tests |
| `--seed N` | `1` | fuzz seed |
| `--no-asan` | | skip the ASan/UBSan build |
| `--no-big` | | skip large inputs |
| `--only-samples` | | sample data only (no complexity estimate) |
| `--suite SUITE` | | only the selected sample suites (`basic`, `extra`, `bonus…`, `tests`); repeatable |
| `--valgrind [N]` | | run the samples + smaller inputs under valgrind, at most N (default 300) |
| `--complexity FILE` | | custom input generator instead of the automatic mode (default `<task>/complexity.py` if it exists) |
| `--complexity-max N` | `6` | how many of the worst growths to measure precisely |
| `--no-complexity` | | skip the complexity estimate |
| `--only-complexity` | | complexity estimate only |
| `--no-style` | | skip the code style check |
| `--only-style` | | compilation and code style only |
| `--strict` | | compile with `-Werror` |
| `--cc g++\|gcc` | `g++` | compiler (`gcc` = compile as C) |
| `--ref BIN` | | reference binary – exact comparison of all outputs |
| `--show N` | `3` | how many details to print per group |
| `--out DIR` | `vysledky/<task>` | where to save problematic inputs |
| `-j N` | CPU count | number of parallel jobs |
| `--src FILE` | | a specific source file when the folder has several |

## 🛠️ Tester's own tests

The tester has its own tests in [tests/](tests/): unit tests (detecting `#ifndef __PROGTEST__` blocks,
complexity fitting, code style, …) and end-to-end tests that run the whole tester on small programs with
a known bug ([tests/fixtures/](tests/fixtures/) – error at end of input, out-of-bounds write,
uninitialized variable, O(n²), crash inside an assert, memory leak, …).

```sh
python3 -m unittest discover -s tests            # everything (~1 min)
PT_FAST=1 python3 -m unittest discover -s tests  # without the complexity estimate (~25 s)
```

Run them before changing the heuristics (complexity estimate, code style, input generator) –
those parts break silently easily.
