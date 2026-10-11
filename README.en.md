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
```

## 📑 Contents

- [Installation](#-installation)
- [What it does](#-what-it-does)
- [What is checked for inputs without a known output](#-what-is-checked-for-inputs-without-a-known-output)
- [Custom tests](#-custom-tests)
- [Results](#-results)
- [Options](#%EF%B8%8F-options)

## 📦 Installation

There is nothing to install. You only need `python3` (≥ 3.10) and `g++`.

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

## 🔍 What it does

1. **Compilation** – `g++ -std=c++20 -Wall -pedantic -Wextra -O2 -D__PROGTEST__`
   - `--strict` adds `-Werror`.
   - Progtest compiles C code as C++ too – e.g. `int *p = malloc(...)` without a cast fails here as well. `--cc gcc` compiles a `.c` file as C (`gcc -std=c11`).
   - Checks for forbidden functions (`system`, `fork`, `exec*`, …) – Progtest refuses to run programs that use them.
   - A second build with `-O0 -fsanitize=address,undefined` hunts for memory errors.
2. **Basic test** – every `*_in.txt` / `*_out.txt` pair from `<task>/sample/**` and `<task>/tests/**`
   (only folders of the language selected by `--lang`, default `CZE`; use `--lang ENG` or `--lang all`).
   Output is compared byte by byte; on a mismatch a diff is printed with visible `\n`, spaces, etc.
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
| ❌ FAIL | empty output, missing trailing `\n`, `\r` in the output, missing prompt (the common first line of the samples) |
| ⚠️ WARN | a line that appears in no sample output (numbers are treated as placeholders) – usually a typo; the closest sample line is suggested |
| ⚠️ WARN | anything on stderr, runtime over half of the time limit |

> [!NOTE]
> The tester **does not decide** which error message belongs to which input – that would amount to solving the task.
> If you have a reference binary (e.g. your own previously accepted solution), use `--ref ./binary`
> and every output will be compared against it exactly.

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
| `--only-samples` | | sample data only |
| `--strict` | | compile with `-Werror` |
| `--cc g++\|gcc` | `g++` | compiler (`gcc` = compile as C) |
| `--ref BIN` | | reference binary – exact comparison of all outputs |
| `--show N` | `3` | how many details to print per group |
| `-j N` | CPU count | number of parallel jobs |
| `--src FILE` | | a specific source file when the folder has several |
