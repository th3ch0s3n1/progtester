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
python3 progtester/progtest.py 01_uloha --valgrind      # + kontrola pod valgrindem
python3 progtester/progtest.py 01_uloha --only-complexity  # jen odhad složitosti
```

## 📑 Obsah

- [Instalace](#-instalace)
- [Co dělá](#-co-dělá)
- [Co se kontroluje u vstupů bez známého výstupu](#-co-se-kontroluje-u-vstupů-bez-známého-výstupu)
- [Úlohy „napište funkci“](#-úlohy-napište-funkci)
- [Štábní kultura kódu](#-štábní-kultura-kódu)
- [Valgrind](#-valgrind)
- [Odhad složitosti](#-odhad-složitosti)
- [Vlastní testy](#-vlastní-testy)
- [Výsledky](#-výsledky)
- [Přepínače](#%EF%B8%8F-přepínače)
- [Testy testeru](#-testy-testeru)

## 📦 Instalace

Nic se neinstaluje. Stačí `python3` (≥ 3.10) a `g++`. Pro `--valgrind` je potřeba `valgrind` (`apt install valgrind`), kontrolu kódu rozšíří `cppcheck` a `clang-tidy`.

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

Některé úlohy mají vzorová data rozdělená na **sady** – `sample/basic/{CZE,ENG}` (povinné testy)
a `sample/extra/{CZE,ENG}` (nepovinný test, typicky dlouhé vstupy, na kterých neprojde pomalý algoritmus).
Tester je pozná sám a vypíše každou sadu zvlášť:

```
FAIL Zakladni test (vzorova data): 4/8 OK, 4 chyb
FAIL Nepovinny test (vzorova data extra): 0/11 OK, 11 chyb
...
== Shrnuti
   FAIL Zakladni test (vzorova data): 4/8
   FAIL Nepovinny test (vzorova data extra): 0/11
```

Podsložky `bonus*` se hlásí jako bonusové testy, jiné názvy jako „Vzorova data <název>“.
Jen vybrané sady: `--suite basic` (lze opakovat). Soubory `*_out_win.txt` (konce řádků pro Windows) se ignorují.

## 🔍 Co dělá

1. **Kompilace** – `g++ -std=c++20 -Wall -pedantic -Wextra -O2 -D__PROGTEST__`
   - `--strict` přidá `-Werror`.
   - Progtest překládá i C kód jako C++ – např. `int *p = malloc(...)` bez přetypování tu neprojde. `--cc gcc` přeloží soubor `.c` jako C (`gcc -std=c11`).
   - Kontrola zakázaných funkcí (`system`, `fork`, `exec*`, …) – s nimi Progtest program nespustí.
   - Když program s `-D__PROGTEST__` nemá `main()` a ten je jen v `#ifndef __PROGTEST__`, jde o
     [úlohu „napište funkci“](#-úlohy-napište-funkci) – testuje se pak jinak.
   - Druhý build s `-O0 -fsanitize=address,undefined` hledá paměťové chyby.
   - S `--valgrind` třetí build `-O0 -g` pro [valgrind](#-valgrind).
   - [Štábní kultura kódu](#-štábní-kultura-kódu) – délka a složitost funkcí, globální proměnné, cppcheck, clang-tidy, … se známkou.
2. **Základní test** – všechny `*_in.txt` / `*_out.txt` z `<úloha>/sample/**` a `<úloha>/tests/**`
   (jen složky jazyka `--lang`, výchozí `CZE`; lze `--lang ENG` nebo `--lang all`).
   Porovnává se bajt po bajtu, při chybě se vypíše diff s viditelnými `\n`, mezerami atd.
   Vstup dostává program **ze souboru** jako na Progtestu, takže na konci vždy přijde konec vstupu (EOF).
   Při ručním zkoušení v terminálu ho pošlete **Ctrl+D** – jinak program jen čeká a chybu na konci vstupu
   (typicky `Nespravny vstup.` navíc) neuvidíte. Tester na tenhle případ upozorní.
3. **Rozbíjecí testy** (vstupy odvozené od vzorových dat):

   | Skupina | Co se zkouší |
   |---|---|
   | Bílé znaky | chybějící/přebývající `\n`, mezery na začátku i na konci řádku (jen varování – očekává se stejný výstup jako u vzoru) |
   | Mezní hodnoty | čísla ve vstupu nahrazena `INT_MAX`, `INT_MAX+1`, `-0`, `+N`, `000N`, 40 devítek, … (u desetinných úloh i `1e-300`, `4.9e-324`, `1e309`, `inf`, `nan`, …) |
   | Desetinná čísla | jen u úloh s desetinnými čísly: všechna čísla vzoru vynásobená `1e±6` … `1e±300` (`1.44 + 2.55 = 4` → `0.00000000000144 + 0.00000000000255 = 0.000000000004`) – výstup se smí změnit jen tak, že se čísla v něm přeškálují; kontrolní běh s `1e+3` pozná úlohy, kde to neplatí (`*`, `/`). Odhalí absolutní epsilon a `%.2f`. Dále `1.5` → `1.50`, `15e-1`, `0.15e1` (výstup musí zůstat stejný) |
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
| ❌ FAIL | valgrind (s `--valgrind`): neinicializovaná hodnota, neplatné čtení/zápis, leak |
| ❌ FAIL | prázdný výstup, chybí `\n` na konci, `\r` ve výstupu, chybí výzva (společný první řádek vzoru) |
| ⚠️ WARN | řádek, který se nevyskytuje v žádném vzorovém výstupu (čísla se berou jako zástupná) – typicky překlep; nabídne nejpodobnější vzorový řádek |
| ⚠️ WARN | něco na stderr, běh nad polovinu časového limitu |

> [!NOTE]
> Která chybová hláška patří ke kterému vstupu, tester **nerozhoduje** – to by už bylo řešení.
> Pokud máte referenční binárku (např. vlastní dříve přijaté řešení), použijte `--ref ./binarka`
> a všechny výstupy se s ní porovnají přesně.

## 🧷 Úlohy „napište funkci“

U části úloh se neodevzdává celý program, jen funkce. Šablona ze zadání vypadá takhle:

```c
#ifndef __PROGTEST__
#include <stdio.h>
#include <assert.h>
#endif /* __PROGTEST__ */

int dateToIndex(int day, int month, int year, int *idx) { /* vaše řešení */ }

#ifndef __PROGTEST__
int main(void)
{
    int idx;
    assert(dateToIndex(1, 1, 2000, &idx) == 1 && idx == 1);
    ...
}
#endif /* __PROGTEST__ */
```

Tester takovou úlohu pozná sám (s `-D__PROGTEST__` v programu není `main()`) a místo vzorových dat:

1. **Přeloží kód tak jako Progtest** – s `-D__PROGTEST__` a s hlavičkami z bloků `#ifndef __PROGTEST__`
   (ty Progtest dodává sám). Navíc zkontroluje, že kód nepoužívá funkci, která je definovaná jen
   v testovací části – na Progtestu by chyběla:
   ```
   FAIL na progtestu nebudou definovane: square(int) - jsou jen v #ifndef __PROGTEST__ ...
   ```
2. **Spustí testovací `main()` ze zadání** jako `-O2`, pod ASan/UBSan a pod valgrindem (pokud je
   nainstalovaný). Používá k tomu vlastní `assert` ([pt/include/assert.h](pt/include/assert.h)), který:
   - **neukončí program** u prvního selhání – uvidíte všechny selhané asserty najednou,
   - **vypíše hodnoty** obou stran porovnání (u `&&` první nesplněnou část),
   - při pádu nebo zacyklení řekne, **u kterého assertu** se to stalo.

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

Hodnoty se vypisují pro čísla, znaky, řetězce (`char *` i `std::string`), ukazatele (`NULL`)
a všechno, co jde vypsat přes `operator<<`. Funguje to i pro C kód, protože ho `g++` překládá jako C++.
S `--cc gcc` (překlad jako C) se asserty jen počítají, bez hodnot. Když nějaký assert nejde rozložit
(např. přiřazení `assert(x = f())`), použije se standardní `assert`, který skončí u prvního selhání.

Vzorová data, generované vstupy ani odhad složitosti se u těchto úloh nedělají – program nečte vstup.
Štábní kultura kódu se kontroluje stejně (testovací část v `#ifndef __PROGTEST__` se nepočítá).

## 🧹 Štábní kultura kódu

Hned po kompilaci tester zkontroluje kód samotný a oznámkuje ho. Pro C/C++ neexistuje jeden závazný styl
jako PEP 8 u Pythonu – kontroluje se proto to, na čem se shodnou běžné styly (Linux kernel, Google, CERT)
i cvičící:

| Co | Limit / pravidlo |
|---|---|
| délka funkce | nejvýš 50 řádků kódu (nad 100 vážný prohřešek) |
| větvení (cyklomatická složitost: `if`/`for`/`while`/`case`/`&&`/`\|\|`/`?`) | nejvýš 10 (nad 20 vážný) |
| zanoření bloků | nejvýš 3 (nad 5 vážný) |
| parametry funkce | nejvýš 5 |
| celý program v `main` | těžký prohřešek |
| komentář nad delšími funkcemi (kromě `main`) | aspoň u poloviny |
| globální proměnné, `goto` | nepoužívat (konstanty `const`/`#define` jsou v pořádku) |
| magická čísla | víc než 5 různých čísel (mimo 0, 1, 2, 10, 100) → pojmenovat |
| duplicitní kód | 5+ stejných řádků na dvou místech → vytáhnout do funkce |
| pojmenování | nemíchat `snake_case` a `camelCase` |
| odsazení, délka řádku | nemíchat tabulátory a mezery, řádky do 120 znaků |

Kód v `#ifndef __PROGTEST__ … #endif` (testovací `main` ze zadání) se nekontroluje.

Když je nainstalovaný **cppcheck** nebo **clang-tidy** (`sudo apt install cppcheck clang-tidy`), přiberou se i
jejich nálezy. Analýza běží ve stejném jazyce, v jakém kód překládá Progtest (`.c` jako C++), u souborů `.c`
se ale vynechají rady platné jen pro C++ (const reference, `std::` algoritmy, …).
Závažnosti `error`/`warning` z cppcheck a `bugprone-*` z clang-tidy jsou **pravděpodobné chyby**
(neinicializovaná proměnná, únik paměti při `realloc`, přetečení při násobení, …) – vypíšou se zvlášť a do
známky za styl se nepočítají.

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

**Známka:** každý nález má trestné body (drobnost 1, vážný 2, všechno v `main` 6; stejný druh se započítá
nejvýš 3×). Body se přepočtou na 100 řádků kódu (kratší program se počítá jako 100 řádků):
≤ 1 → **1**, ≤ 2,5 → **2**, ≤ 4,5 → **3**, ≤ 7 → **4**, jinak **5**.

## 🔬 Valgrind

ASan/UBSan **nepozná čtení neinicializované paměti** (proměnná bez počáteční hodnoty, paměť z `malloc`/`realloc`).
Typický příznak je, že se výstup `-O2` a `-O0` buildu liší, nebo že program na Progtestu dělá něco jiného než doma.
Valgrind ukáže přesné místo i to, kde paměť vznikla:

```
FAIL sample/basic/CZE/0000_in.txt
     - [valgrind] Conditional jump or move depends on uninitialised value(s)
         at operation_calculate_hotel_price(array, time, time) (program.c:341)
         by main (program.c:64)
       Uninitialised value was created by a heap allocation
         at realloc (vg_replace_malloc.c:1804)
         by insert_array(array*, operation) (program.c:464)
```

Valgrind je asi 50× pomalejší, proto se pouští jen na vzorová data a náhodný výběr menších generovaných
vstupů: `--valgrind` = nejvýše 300 vstupů, `--valgrind 50` = nejvýše 50.

## 📈 Odhad složitosti

Po ostatních testech tester odhadne časovou složitost programu – **bez znalosti úlohy**, jen ze vzorových dat.
Vzorové vstupy zkouší obecnými způsoby zvětšovat a sleduje, jak roste CPU čas:

| Způsob zvětšení | Příklad (`+ 2026-01-01 12:00, 80`) | Ideál |
|---|---|:---:|
| řádek n-krát | stejný řádek n-krát za sebou | O(n log n) |
| řádek n-krát, číslo +1 | `+ 2026-…`, `+ 2027-…`, `+ 2028-…` (rostoucí čas, id, …) | O(n log n) |
| prvek n-krát | číslo i s oddělovačem za ním n-krát (posloupnost na jednom řádku) | O(n log n) |
| celý vstup n-krát | celý vzorový vstup n-krát za sebou | O(n log n) |
| číslo + n | `+ 2026-01-01 12:00, [80 + n]` – velikost hodnoty (délka intervalu, rozpočet, …) | O(log n) |

- **Platnost:** zvětšený vstup platí, jen dokud ho program přijímá – nesmí spadnout ani vypsat chybovou hlášku
  dřív než u původního vzoru a odpovědí musí s n přibývat stejným tempem. Kde ho program přestane přijímat,
  tam končí platný rozsah (dohledá se půlením) a na něj se extrapoluje čas. Program tedy sám „řekne“,
  jak velké vstupy dává smysl zkoušet (např. rok jen do 2999).
- **Výběr:** všechny způsoby se nejdřív hrubě změří paralelně, pak se ty, které program měřitelně zpomalují,
  seřadí podle toho, o kolik jsou horší než ideál, a nejhorší (`--complexity-max`, default 6) se změří přesně
  a postupně. Způsoby se stejným závěrem se měří jen jednou.
- **Model:** naměřené časy se proloží modely `t = c + a·f(n)` pro `f` = 1, log n, n, n log n, n², n³;
  z modelů, které sedí skoro stejně dobře, se vybere ten nejjednodušší.
- **Pády** při zvětšování se hlásí zvlášť (a zopakují se bez limitu paměti – pozná se tak, jestli program
  jen potřebuje moc paměti / nekontroluje `NULL` z `malloc`). Vstup se uloží do `vysledky/`.
- **Náhlý skok** (čas se nemění a pak prudce vzroste) typicky znamená přetečení proměnné nebo nekonečnou smyčku.

```
   cislo '# 2000-12-08 23:27, [1163189]' zvetsene o n  (sample/extra/CZE/0000_in.txt:11)  (idealne O(log n))
                n     CPU cas      vstup
                1     23.1 ms       0 kB
              ...
          6.9e10      1.10 s       0 kB
   -> namereno O(n) (nebo O(n log n)), lokalni exponent n^0.96
   -> znamka 4: cas roste s hodnotou cisla jako O(n) a program takovy vstup prijima - pri vetsim n nestihne limit (idealne O(log n))
```

| Známka | Význam |
|:---:|---|
| 1 | složitost odpovídá ideálu (a stihne limit) |
| 2 | horší než ideál, ale v rozsahu, který program přijímá, limit stihne – jde to lépe |
| 3 | horší než ideál o jednu třídu / dobrá složitost s moc velkou konstantou |
| 4 | horší a nestihne limit / podezřelý skok |
| 5 | řádově pomalé |

> [!NOTE]
> Je to odhad, ne důkaz. Měří se jen to, co jde odvodit ze vzorových dat – pokud se nějaký parametr ve
> vzorech neobjevuje (např. vzory mají jen pár změn ceníku), tester ho zvětšit nemusí umět. O(n) a O(n log n)
> se měřením odlišují špatně, tester pak vypíše obě možnosti.

### Vlastní generátor (nepovinné)

Když chcete měřit něco konkrétního, dejte do složky úlohy `complexity.py` (nebo `--complexity SOUBOR`)
a tester použije ten místo automatiky:

```python
TIME_LIMIT = 1.0   # [s] nepovinné, jinak --timeout

def gen(n):        # vrací SPRÁVNÝ vstup velikosti n (str nebo bytes)
    return f"{n}\n" + " ".join(map(str, range(n))) + "\n"

SERIES = [dict(name="počet prvků", gen=gen, n_min=16, n_max=1_000_000, target="n log n")]
```

`n_min` = první velikost (dál se zdvojuje), `n_max` = největší `n` na Progtestu (na něj se extrapoluje),
`target` = složitost dobrého řešení (`1`, `log n`, `n`, `n log n`, `n^2`, `n^3`).

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
| `--only-samples` | | jen vzorová data (bez odhadu složitosti) |
| `--suite SADA` | | jen vybrané sady vzorových dat (`basic`, `extra`, `bonus…`, `tests`); lze opakovat |
| `--valgrind [N]` | | pustit vzorová data + menší vstupy pod valgrindem, nejvýše N (default 300) |
| `--complexity SOUBOR` | | vlastní generátor vstupů místo automatiky (default `<úloha>/complexity.py`, pokud existuje) |
| `--complexity-max N` | `6` | kolik nejhorších způsobů zvětšení vstupu změřit přesně |
| `--no-complexity` | | nedělat odhad složitosti |
| `--only-complexity` | | jen odhad složitosti |
| `--no-style` | | nekontrolovat štábní kulturu kódu |
| `--only-style` | | jen kompilace a štábní kultura kódu |
| `--strict` | | kompilovat s `-Werror` |
| `--cc g++\|gcc` | `g++` | překladač (`gcc` = překlad jako C) |
| `--ref BIN` | | referenční binárka – přesné porovnání všech výstupů |
| `--show N` | `3` | kolik detailů vypsat na skupinu |
| `--out SLOŽKA` | `vysledky/<úloha>` | kam uložit problémové vstupy (složka se na začátku vyprázdní; existující neprázdnou složku, kterou nevytvořil tester, odmítne) |
| `-j N` | počet jader | počet paralelních úloh |
| `--src SOUBOR` | | konkrétní zdrojový soubor, když jich je ve složce víc |

## 🛠️ Testy testeru

Tester má vlastní testy ve složce [tests/](tests/): unit testy (rozpoznání bloků `#ifndef __PROGTEST__`,
fit složitosti, štábní kultura, …) a end-to-end testy, které pouští celý tester na malé programy se
známou chybou ([tests/fixtures/](tests/fixtures/) – chyba na konci vstupu, zápis mimo pole,
neinicializovaná proměnná, O(n²), pád v assertu, únik paměti, …).

```sh
python3 -m unittest discover -s tests            # vše (~1 min)
PT_FAST=1 python3 -m unittest discover -s tests  # bez odhadu složitosti (~25 s)
```

Před úpravou heuristik (odhad složitosti, štábní kultura, generátor vstupů) je dobré je pustit –
tyhle části se snadno rozbijí tiše.
