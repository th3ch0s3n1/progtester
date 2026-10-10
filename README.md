<div align="center">

# 🧪 progtester

**Lokální simulátor Progtestu, který se snaží váš program rozbít.**

![Python](https://img.shields.io/badge/python-%E2%89%A5%203.10-3776AB?logo=python&logoColor=white)
![g++](https://img.shields.io/badge/g%2B%2B-C%2B%2B20-00599C?logo=cplusplus&logoColor=white)
![Závislosti](https://img.shields.io/badge/z%C3%A1vislosti-%C5%BE%C3%A1dn%C3%A9-brightgreen)

🇨🇿 Čeština · [🇬🇧 English](README.en.md)

</div>

---

Přeloží program podobně jako Progtest, pustí na něj vzorová data a pak ho zkusí rozbít.
Tester **nezná řešení žádné úlohy** – u generovaných vstupů kontroluje jen věci, které platí vždy.

```sh
python3 progtester/progtest.py 01_uloha                 # plný test
python3 progtester/progtest.py 01_uloha --only-samples  # jen vzorová data
python3 progtester/progtest.py 01_uloha --fuzz 2000 --seed 42 --show 10
```

## 📑 Obsah

- [Instalace](#-instalace)
- [Co dělá](#-co-dělá)
- [Co se kontroluje u vstupů bez známého výstupu](#-co-se-kontroluje-u-vstupů-bez-známého-výstupu)
- [Vlastní testy](#-vlastní-testy)
- [Výsledky](#-výsledky)
- [Přepínače](#%EF%B8%8F-přepínače)

## 📦 Instalace

Nic se neinstaluje. Stačí `python3` (≥ 3.10) a `g++`.

```sh
git clone https://github.com/th3ch0s3n1/progtester.git
```

Složku `progtester` umístěte vedle složek s úlohami. **Každá úloha musí mít vlastní složku** – v ní leží zdrojový kód řešení a vzorová data:

```
.
├── progtester/
│   └── progtest.py
├── 01_uloha/             ← jedna úloha = jedna složka
│   ├── main.cpp          ← vaše řešení
│   └── sample/           ← vzorová data z Progtestu
│       ├── CZE/
│       └── ENG/
├── 02_dalsi_uloha/
│   ├── main.cpp
│   └── sample/
└── ...
```

### 📥 Vzorová data

Tester vzorová data nezná, musíte je **stáhnout ze stránky úlohy na Progtestu** (tlačítko **Download** u řádku „Vzorová data“):

![Tlačítko Download u vzorových dat na Progtestu](vzorova_data.png)

Stažený archiv rozbalte do složky `sample/` v adresáři příslušné úlohy (viz strom výše).

## 🔍 Co dělá

1. **Kompilace** – `g++ -std=c++20 -Wall -pedantic -Wextra -O2 -D__PROGTEST__`
   - `--strict` přidá `-Werror`.
   - Progtest překládá i C kód jako C++ – např. `int *p = malloc(...)` bez přetypování tu neprojde. `--cc gcc` přeloží soubor `.c` jako C (`gcc -std=c11`).
   - Kontrola zakázaných funkcí (`system`, `fork`, `exec*`, …) – s nimi Progtest program nespustí.
   - Druhý build s `-O0 -fsanitize=address,undefined` hledá paměťové chyby.
2. **Základní test** – všechny `*_in.txt` / `*_out.txt` z `<úloha>/sample/**` a `<úloha>/tests/**`
   (jen složky jazyka `--lang`, výchozí `CZE`; lze `--lang ENG` nebo `--lang all`).
   Porovnává se bajt po bajtu, při chybě se vypíše diff s viditelnými `\n`, mezerami atd.
3. **Rozbíjecí testy** (vstupy odvozené od vzorových dat):

   | Skupina | Co se zkouší |
   |---|---|
   | Bílé znaky | chybějící/přebývající `\n`, mezery na začátku i na konci řádku (jen varování – očekává se stejný výstup jako u vzoru) |
   | Mezní hodnoty | čísla ve vstupu nahrazena `INT_MAX`, `INT_MAX+1`, `-0`, `+N`, `000N`, 40 devítek, … |
   | Nesprávné vstupy | `abc`, `1.23`, `1abc`, `0x1`, prázdný vstup, `\0`, UTF-8, `\r\n`, … |
   | Useknutý vstup | EOF na každé pozici |
   | Velké vstupy | 1 MB mezer/nul/smetí, 100k číslic |
   | Fuzz | náhodné mutace, reprodukovatelné přes `--seed` |

## ✅ Co se kontroluje u vstupů bez známého výstupu

| Úroveň | Kontrola |
|:---:|---|
| ❌ FAIL | pád (SIGSEGV, …), timeout, výstup > 16 MB, limit paměti |
| ❌ FAIL | ASan/UBSan: čtení/zápis mimo pole, přetečení `int`, leak, … |
| ❌ FAIL | `-O2` a `-O0` build vypíšou něco jiného → nedefinované chování |
| ❌ FAIL | prázdný výstup, chybí `\n` na konci, `\r` ve výstupu, chybí výzva (společný první řádek vzoru) |
| ⚠️ WARN | řádek, který se nevyskytuje v žádném vzorovém výstupu (čísla se berou jako zástupná) – typicky překlep; nabídne nejpodobnější vzorový řádek |
| ⚠️ WARN | něco na stderr, běh nad polovinu časového limitu |

> [!NOTE]
> Která chybová hláška patří ke kterému vstupu, tester **nerozhoduje** – to by už bylo řešení.
> Pokud máte referenční binárku (např. vlastní dříve přijaté řešení), použijte `--ref ./binarka`
> a všechny výstupy se s ní porovnají přesně.

## 🧩 Vlastní testy

Přidejte soubory `NNNN_in.txt` + `NNNN_out.txt` do `<úloha>/tests/` – berou se jako další vzorová data
(a jejich výstupy rozšíří sadu „známých“ řádků).

## 📂 Výsledky

Každý neúspěšný vstup se uloží do `progtester/vysledky/<úloha>/`:

| Soubor | Obsah |
|---|---|
| `XXXX_in.txt` | vstup |
| `XXXX_out.txt` | váš výstup |
| `XXXX_ref.txt` | očekávaný výstup (pokud je znám) |
| `XXXX_info.txt` | co bylo špatně |

Reprodukce: `./a.out < progtester/vysledky/01_uloha/0003_fail_in.txt`

**Návratový kód:** `0` = bez chyb (varování nevadí) · `1` = nějaký FAIL · `2` = nejde přeložit / zakázané funkce.

## ⚙️ Přepínače

| Přepínač | Výchozí | Popis |
|---|:---:|---|
| `--lang CZE\|ENG\|all` | `CZE` | které jazykové složky se testují |
| `--timeout S` | `1` | limit na jeden běh v sekundách |
| `--mem MB` | `256` | limit paměti pro `-O2` build |
| `--fuzz N` | `200` | počet náhodných testů |
| `--seed N` | `1` | seed pro fuzz |
| `--no-asan` | | nespouštět ASan/UBSan build |
| `--no-big` | | vynechat velké vstupy |
| `--only-samples` | | jen vzorová data |
| `--strict` | | kompilovat s `-Werror` |
| `--cc g++\|gcc` | `g++` | překladač (`gcc` = překlad jako C) |
| `--ref BIN` | | referenční binárka – přesné porovnání všech výstupů |
| `--show N` | `3` | kolik detailů vypsat na skupinu |
| `-j N` | počet jader | počet paralelních úloh |
| `--src SOUBOR` | | konkrétní zdrojový soubor, když jich je ve složce víc |
