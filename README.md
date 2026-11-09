<div align="center">

# 🧪 progtester

**Lokální simulátor Progtestu, který se snaží váš program rozbít.**

![Python](https://img.shields.io/badge/python-%E2%89%A5%203.10-3776AB?logo=python&logoColor=white)
![g++](https://img.shields.io/badge/g%2B%2B-C%2B%2B20-00599C?logo=cplusplus&logoColor=white)
![Závislosti](https://img.shields.io/badge/z%C3%A1vislosti-%C5%BE%C3%A1dn%C3%A9-brightgreen)

🇨🇿 Čeština · [🇬🇧 English](README.en.md)

</div>

---

progtester přeloží vaše řešení stejně jako Progtest, pustí na něj vzorová data ze zadání a potom ho
zkouší rozbít tisíci odvozených vstupů: mezními hodnotami, nesprávným vstupem, useknutým vstupem,
obřími vstupy a náhodnými mutacemi. Hledá pády, paměťové chyby, nedefinované chování a příliš pomalý
algoritmus a oznámkuje i čitelnost kódu.

Tester **nezná řešení žádné úlohy**. U vstupů, ke kterým nemá očekávaný výstup, kontroluje jen to, co
musí platit vždy (program nespadne, nepíše mimo pole, výstup má správný tvar, …).

## Obsah

- [Rychlý start](#rychlý-start)
- [Co tester dělá](#co-tester-dělá)
- [Jak číst výsledky](#jak-číst-výsledky)
- [Překlad](#překlad)
- [Vzorová data](#vzorová-data)
- [Rozbíjecí testy](#rozbíjecí-testy)
- [Paměťové chyby: ASan, UBSan a valgrind](#paměťové-chyby-asan-ubsan-a-valgrind)
- [Úlohy „napište funkci“](#úlohy-napište-funkci)
- [Štábní kultura kódu](#štábní-kultura-kódu)
- [Odhad časové složitosti](#odhad-časové-složitosti)
- [Vlastní testy a generátory](#vlastní-testy-a-generátory)
- [Přepínače](#přepínače)
- [Vývoj testeru](#vývoj-testeru)

## Rychlý start

Potřebujete Linux (na Windows WSL), `python3` ≥ 3.10 a `g++`. Nic dalšího se neinstaluje.
Nepovinně: `valgrind` pro `--valgrind`, `cppcheck` a `clang-tidy` pro podrobnější kontrolu kódu
(`sudo apt install valgrind cppcheck clang-tidy`).

```sh
git clone https://github.com/th3ch0s3n1/progtester.git
```

Složku `progtester` dejte vedle složek s úlohami. Každá úloha má vlastní složku se zdrojovým kódem
a vzorovými daty:

```
.
├── progtester/
├── 01_uloha/
│   ├── main.c            ← vaše řešení
│   └── sample/           ← vzorová data z Progtestu
│       ├── CZE/
│       └── ENG/
└── 02_dalsi_uloha/
    └── ...
```

Vzorová data stáhněte na stránce úlohy na Progtestu tlačítkem **Download** u řádku „Vzorová data“
a rozbalte je do `sample/`:

![Tlačítko Download u vzorových dat na Progtestu](vzorova_data.png)

Potom stačí tester spustit:

```sh
python3 progtester/progtest.py 01_uloha                    # všechno
python3 progtester/progtest.py 01_uloha --only-samples     # jen vzorová data, rychle
python3 progtester/progtest.py 01_uloha --valgrind         # navíc kontrola pod valgrindem
python3 progtester/progtest.py 01_uloha --only-complexity  # jen odhad složitosti
```

Pokud je ve složce víc zdrojových souborů, tester vezme `program.c`, `main.c`, `program.cpp` nebo
`main.cpp`; jinak ho určete přes `--src`. Místo složky můžete předat rovnou cestu ke zdrojovému souboru.

## Co tester dělá

Jeden běh projde tyto kroky:

1. **[Překlad](#překlad)** stejnými přepínači jako Progtest a kontrola zakázaných funkcí.
2. **[Štábní kultura kódu](#štábní-kultura-kódu)**: délka a složitost funkcí, globální proměnné,
   magická čísla, … a známka 1–5.
3. **[Vzorová data](#vzorová-data)**: výstup se porovná se vzorem bajt po bajtu.
4. **[Rozbíjecí testy](#rozbíjecí-testy)**: vstupy odvozené od vzorů. Každý vstup běží v několika
   buildech (`-O2`, ASan/UBSan, případně valgrind), aby se ukázaly i
   [paměťové chyby](#paměťové-chyby-asan-ubsan-a-valgrind).
5. **[Odhad časové složitosti](#odhad-časové-složitosti)**: tester vzorové vstupy zvětšuje, měří čas
   a odhadne, jestli program stihne limit i na velkých datech.

U [úloh „napište funkci“](#úlohy-napište-funkci), kde se odevzdává jen funkce, se místo kroků 3–5
spustí testovací `main()` ze zadání.

## Jak číst výsledky

Každý test skončí jako **OK**, **WARN** nebo **FAIL**:

- **FAIL** je chyba, kvůli které by Progtest test nejspíš neuznal: špatný výstup, pád, timeout,
  paměťová chyba, nedefinované chování.
- **WARN** je podezřelé, ale nemusí to být chyba: neznámý řádek ve výstupu, výpis na stderr, běh
  nad polovinu časového limitu.

Na konci je shrnutí za každou sadu vzorových dat, známka za styl a za složitost. U každé skupiny testů
se vypíšou první tři problémy (`--show N` jich ukáže víc) i s rozdílem proti očekávanému výstupu:

```
FAIL Zakladni test (vzorova data): 1/4 OK, 3 chyb
   FAIL sample/CZE/0000_in.txt
        vstup:  1 2 3\n
        vystup: Zadejte cisla:\nSoucet: 1\nSoucet: 3\nSoucet: 6\nNespravny vstup.\n
        - vystup neodpovida ocekavanemu
          vse spravne, jen na konci navic chybova hlaska -> program bere konec vstupu (EOF) jako chybu. ...
          --- ocekavano
          +++ dostal
          @@ -3,2 +3,3 @@
           Soucet: 3\n
           Soucet: 6\n
          +Nespravny vstup.\n
        ulozeno: 0001_fail_*.txt
```

Všechny problémové vstupy se ukládají do `progtester/vysledky/<úloha>/` (jinam přes `--out`):

| Soubor | Obsah |
|---|---|
| `0001_fail_in.txt` | vstup |
| `0001_fail_out.txt` | výstup vašeho programu |
| `0001_fail_ref.txt` | očekávaný výstup, pokud je znám |
| `0001_fail_info.txt` | co bylo špatně |

Chybu si pak zopakujete vlastním programem: `./a.out < progtester/vysledky/01_uloha/0001_fail_in.txt`.

Návratový kód testeru je `0`, když nic neselhalo (varování nevadí), `1` při jakémkoli FAIL
a `2`, když program nejde přeložit nebo používá zakázané funkce.

## Překlad

Program se přeloží jako na Progtestu:

```
g++ -std=c++20 -Wall -pedantic -D__PROGTEST__ -O2 -Wextra main.c -o prog -lm
```

- Progtest překládá i soubory `.c` překladačem `g++`, tedy jako C++. Kód, který je platné C, ale ne
  C++ (např. `int *p = malloc(...)` bez přetypování), proto neprojde ani tady. `--cc gcc` přeloží
  `.c` jako C (`gcc -std=c11`).
- `--strict` přidá `-Werror`.
- Program nesmí volat `system`, `fork`, `exec*`, `popen`, sokety apod., jinak ho Progtest nespustí.
  Pokud je potřebujete při ladění, dejte je do `#ifndef __PROGTEST__ … #endif`.

Kromě tohoto buildu se program přeloží ještě s `-O0 -fsanitize=address,undefined` a s `--valgrind`
také s `-O0 -g`; viz [paměťové chyby](#paměťové-chyby-asan-ubsan-a-valgrind).

## Vzorová data

Testují se všechny dvojice `*_in.txt` / `*_out.txt` ze složky `sample/` (včetně podsložek)
a z [`tests/`](#vlastní-testy-a-generátory). Ze složek `CZE` a `ENG` se bere jen `CZE`; jiný jazyk
vyberete přes `--lang ENG` nebo `--lang all`. Soubory `*_out_win.txt` se ignorují.

Výstup se porovná přesně, bajt po bajtu. Program dostane vstup ze souboru, takže na konci vždy narazí
na konec vstupu (EOF). Když program EOF považuje za nesprávný vstup a na konec vypíše chybovou hlášku
navíc, tester na to upozorní zvlášť. Při ručním zkoušení v terminálu se EOF posílá klávesami **Ctrl+D**.

Některé úlohy mají vzorová data rozdělená na sady, např. `sample/basic/` (povinné testy)
a `sample/extra/` (nepovinný test s velkými vstupy). Tester každou sadu vyhodnotí zvlášť:

```
== Shrnuti
   FAIL Zakladni test (vzorova data): 4/8
   FAIL Nepovinny test (vzorova data extra): 0/11
```

Podsložky `bonus*` se hlásí jako bonusové testy. `--suite basic` otestuje jen vybranou sadu
(přepínač jde opakovat).

## Rozbíjecí testy

Z každého vzorového vstupu tester odvodí další:

| Skupina | Co se zkouší |
|---|---|
| Bílé znaky | chybějící nebo přebývající `\n`, mezery na začátku a konci řádků |
| Mezní hodnoty | čísla ve vstupu nahrazená `0`, `-0`, `INT_MAX`, `INT_MAX+1`, `000N`, `+N`, 40 devítek, … |
| Desetinná čísla | jen u úloh s desetinnými čísly, viz níže |
| Nesprávné vstupy | `abc`, `1abc`, `1.23`, `0x1`, prázdný vstup, `\0`, UTF-8, `\r\n`, … |
| Useknutý vstup | vstup ukončený uprostřed, na každé pozici |
| Velké vstupy | 1 MB mezer, nul nebo náhodných bajtů, 100 000 číslic, vzor 50 000× za sebou |
| Fuzz | náhodné mutace vzorů (`--fuzz N`, reprodukovatelné přes `--seed`) |

**Desetinná čísla.** Když vzorový vstup obsahuje desetinná čísla, tester je všechna vynásobí
`1e±6` až `1e±300`. Výstup se pak smí změnit jen tak, že se stejně přeškálují čísla v něm. Tím se
odhalí porovnávání s pevným epsilonem nebo výpis přes `%.2f`. Úlohy, kde to neplatí (násobení,
dělení), tester pozná kontrolním během a test vynechá. Navíc zkouší jiný zápis stejného čísla
(`1.5` → `1.50`, `15e-1`, `0.15e1`), při kterém se výstup nesmí změnit vůbec.

Většina těchto vstupů nemá známý výstup. Tester u nich kontroluje:

| Úroveň | Kontrola |
|:---:|---|
| FAIL | pád (SIGSEGV, …), timeout, překročený limit paměti, výstup nad 16 MB |
| FAIL | ASan/UBSan: přístup mimo pole, přetečení `int`, únik paměti, … |
| FAIL | build `-O2` a `-O0` vypíšou něco jiného (nedefinované chování) |
| FAIL | prázdný výstup, chybí `\n` na konci, `\r` ve výstupu, chybí úvodní výzva (první řádek, který mají všechny vzory společný) |
| WARN | řádek, který se v žádném vzorovém výstupu nevyskytuje, ani když se čísla berou jako libovolná; tester nabídne nejpodobnější vzorový řádek (typicky překlep) |
| WARN | výpis na stderr, běh nad polovinu časového limitu |
| WARN | u bílých znaků a jiného zápisu čísla: výstup se liší od vzoru |

> [!NOTE]
> Tester nerozhoduje, jestli má program na daný vstup vypsat chybovou hlášku, nebo výsledek. To by
> vyžadovalo znát řešení. Máte-li referenční program (třeba vlastní dřív přijaté řešení), předejte ho
> přes `--ref ./binarka` a všechny výstupy se s ním porovnají přesně.

## Paměťové chyby: ASan, UBSan a valgrind

Každý vstup běží i v buildu s **AddressSanitizerem a UndefinedBehaviorSanitizerem**. Ty najdou
přístup mimo pole, použití uvolněné paměti, únik paměti nebo přetečení celého čísla a ukážou řádek
v kódu.

Čtení **neinicializované paměti** sanitizery nepoznají. Typickým příznakem je, že se výstupy `-O2`
a `-O0` liší, nebo že program na Progtestu dělá něco jiného než doma. Najde ho valgrind:
`--valgrind` pustí pod valgrindem vzorová data a náhodný výběr menších generovaných vstupů, celkem
nejvýš 300 (`--valgrind 50` nejvýš 50). Valgrind je zhruba 50× pomalejší, proto se nepouští na všechno.

```
   FAIL sample/CZE/0000_in.txt
        - [valgrind] Use of uninitialised value of size 8
            at _itoa_word (_fitoa_word.c:38)
            ...
            by printf (printf.c:33)
            by main (uninit.c:13)
          Uninitialised value was created by a heap allocation
            at malloc (vg_replace_malloc.c:447)
            by main (uninit.c:7)
```

## Úlohy „napište funkci“

U některých úloh se odevzdává jen funkce a zadání obsahuje testovací `main()` s asserty:

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

Tester takovou úlohu pozná podle toho, že s `-D__PROGTEST__` v kódu žádný `main()` nezbude. Pak:

1. Přeloží kód jako Progtest, tedy s `-D__PROGTEST__` a s hlavičkami z bloků `#ifndef __PROGTEST__`,
   které Progtest dodává sám. Ohlásí funkce, které vaše řešení volá, ale jsou definované jen
   v testovací části, takže na Progtestu by chyběly.
2. Spustí testovací `main()` v buildu `-O2`, pod ASan/UBSan a pod valgrindem (je-li nainstalovaný).
   Používá přitom vlastní [`assert`](pt/include/assert.h), který po selhání pokračuje dál, vypíše
   hodnoty obou stran porovnání a při pádu nebo zacyklení řekne, u kterého assertu se to stalo.

```
== Testy z main() v #ifndef __PROGTEST__ (asserty ze zadani)
   FAIL [-O2] selhalo 3 assertu z 10
        r. 31: assert(absVal(-5) == 5)
               hodnoty: -5 == 5
        r. 32: assert(absVal(-7) == 7 && idx == 3)
               hodnoty: -7 == 7
        r. 37: assert(third() == 0.3)
               hodnoty: 0.30000000000000004 == 0.3
    OK  ASan/UBSan: bez chyb, asserty dopadly stejne jako v -O2
    OK  valgrind: bez chyb, asserty dopadly stejne jako v -O2
```

Hodnoty se vypíšou u čísel, znaků, řetězců (`char *` i `std::string`), ukazatelů a všeho, co jde
vypsat přes `operator<<`; u `&&` jen první nesplněná část. S `--cc gcc` se asserty jen počítají,
bez hodnot. Assert, který nejde rozložit (např. `assert(x = f())`), se vyhodnotí standardním
`assert` a program u prvního selhání skončí.

## Štábní kultura kódu

Tester kód projde a oznámkuje podle pravidel v tabulce. Známka je orientační: pravidla odpovídají
běžným doporučením pro čitelný C/C++ kód, nejsou to oficiální kritéria Progtestu ani cvičících.

| Co | Pravidlo |
|---|---|
| délka funkce | nejvýš 50 řádků kódu (nad 100 vážný prohřešek) |
| větvení (`if`, `for`, `while`, `case`, `&&`, `\|\|`, `?`) | nejvýš 10 cest kódem (nad 20 vážný prohřešek) |
| zanoření bloků | nejvýš 3 úrovně (nad 5 vážný prohřešek) |
| parametry funkce | nejvýš 5 |
| celý program v `main` | těžký prohřešek |
| komentáře | aspoň polovina delších funkcí (kromě `main`) má komentář |
| globální proměnné, `goto` | nepoužívat (konstanty přes `const` nebo `#define` jsou v pořádku) |
| magická čísla | víc než 5 různých čísel kromě 0, 1, 2, 10 a 100 → pojmenovat je |
| duplicitní kód | 5 a více stejných řádků na dvou místech → vytáhnout do funkce |
| pojmenování | nemíchat `snake_case` a `camelCase` |
| formátování | nemíchat tabulátory a mezery, řádky nejvýš 120 znaků |

Testovací část v `#ifndef __PROGTEST__ … #endif` se nekontroluje.

Pokud jsou nainstalované **cppcheck** nebo **clang-tidy**, přidají se jejich nálezy. Nálezy, které
ukazují spíš na chybu než na styl (`error`/`warning` z cppcheck, `bugprone-*` z clang-tidy, např.
neinicializovaná proměnná nebo únik paměti při `realloc`), se vypíšou zvlášť a do známky se nepočítají.

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

**Jak vzniká známka:** drobný nález má 1 trestný bod, vážný 2 a celý program v `main` 6. Stejný druh
nálezu se započítá nejvýš třikrát. Body se přepočtou na 100 řádků kódu (kratší program se počítá jako
100 řádků): do 1 bodu známka **1**, do 2,5 **2**, do 4,5 **3**, do 7 **4**, víc **5**.

## Odhad časové složitosti

Na závěr tester odhadne, jak rychle roste doba běhu s velikostí vstupu. Úlohu nezná, takže vychází
ze vzorových vstupů a zkouší je zvětšovat obecnými způsoby. Na příkladu vzorového řádku `1 2 3`:

| Způsob zvětšení | Příklad | Ideál |
|---|---|:---:|
| řádek n-krát | `1 2 3` n-krát pod sebou | O(n log n) |
| řádek n-krát, číslo o 1 větší | `1 2 3`, `1 2 4`, `1 2 5`, … | O(n log n) |
| prvek n-krát | `1 1 1 … 1 2 3` | O(n log n) |
| celý vstup n-krát | celý vzorový vstup n-krát za sebou | O(n log n) |
| číslo + n | `1 2 [3 + n]` | O(log n) |

Zvětšený vstup se počítá, jen dokud ho program přijímá: nesmí spadnout ani vypsat chybovou hlášku
a počet odpovědí musí růst s n. Tím program sám vymezí, jak velké vstupy dávají smysl. Všechny způsoby
se nejdřív zběžně změří, a ty, které program zpomalují nejvíc, se pak změří přesně (`--complexity-max`,
výchozí 6). Naměřené časy se proloží modely O(1), O(log n), O(n), O(n log n), O(n²) a O(n³):

```
   radek '1 2 3' n-krat  (sample/CZE/0000_in.txt:1)  (idealne O(n log n))
                n     CPU cas      vstup
                1      2.4 ms       0 kB
               64      5.3 ms       0 kB
            2 048      9.9 ms      12 kB
            8 192     68.0 ms      48 kB
           32 768    946.4 ms     192 kB
   -> namereno O(n^2), lokalni exponent n^1.89
   -> limit 1 s by se prekrocil od n ~ 32 768
   -> znamka 4: cas roste s poctem prvku jako O(n^2) a program takovy vstup prijima - pri vetsim n nestihne limit (idealne O(n log n))
```

| Známka | Význam |
|:---:|---|
| 1 | složitost odpovídá ideálu a stihne limit |
| 2 | horší než ideál, ale na vstupech, které program přijímá, limit stihne |
| 3 | o jednu třídu horší než ideál, nebo dobrá složitost s příliš velkou konstantou |
| 4 | horší než ideál a nestihne limit, nebo podezřelý skok v čase |
| 5 | řádově pomalé |

Pokud program při zvětšování spadne, tester to ohlásí a vstup uloží do `vysledky/`. Zkusí ho i bez
limitu paměti, aby bylo vidět, jestli program jen potřebuje moc paměti nebo nekontroluje `NULL`
z `malloc`. Náhlý skok v čase (dlouho stejný, pak prudký nárůst) obvykle znamená přetečení
proměnné nebo nekonečnou smyčku.

> [!NOTE]
> Je to odhad, ne důkaz. Tester umí zvětšit jen to, co ve vzorových datech vidí. O(n) a O(n log n)
> se měřením rozlišují špatně, proto tester v takovém případě vypíše obě možnosti.

## Vlastní testy a generátory

**Vlastní testy:** soubory `NNNN_in.txt` a `NNNN_out.txt` ve složce `<úloha>/tests/` se testují stejně
jako vzorová data. Jejich výstupy navíc rozšíří sadu řádků, které tester považuje za známé.

**Vlastní generátor pro odhad složitosti:** když chcete měřit konkrétní parametr, dejte do složky
úlohy soubor `complexity.py` (nebo ho předejte přes `--complexity SOUBOR`). Tester ho pak použije
místo automatického zvětšování:

```python
TIME_LIMIT = 1.0   # [s] nepovinné, jinak --timeout

def gen(n):        # vrací SPRÁVNÝ vstup velikosti n (str nebo bytes)
    return f"{n}\n" + " ".join(map(str, range(n))) + "\n"

SERIES = [dict(name="počet prvků", gen=gen, n_min=16, n_max=1_000_000, target="n log n")]
```

`n_min` je první měřená velikost (dál se zdvojuje), `n_max` největší `n`, které může přijít na
Progtestu (na tu se čas extrapoluje), a `target` složitost dobrého řešení: `1`, `log n`, `n`,
`n log n`, `n^2` nebo `n^3`.

## Přepínače

| Přepínač | Výchozí | Popis |
|---|:---:|---|
| **Co testovat** | | |
| `--only-samples` | | jen vzorová data |
| `--only-style` | | jen překlad a štábní kultura |
| `--only-complexity` | | jen odhad složitosti |
| `--no-style` | | bez kontroly štábní kultury |
| `--no-complexity` | | bez odhadu složitosti |
| `--no-asan` | | bez buildu s ASan/UBSan |
| `--no-big` | | bez velkých vstupů |
| `--valgrind [N]` | | navíc valgrind na nejvýš N vstupech (bez čísla 300) |
| `--suite SADA` | | jen vybraná sada vzorových dat (`basic`, `extra`, `bonus…`, `tests`); jde opakovat |
| `--lang CZE\|ENG\|all` | `CZE` | jazyk vzorových dat |
| `--fuzz N` | `200` | počet náhodných vstupů |
| `--seed N` | `1` | seed pro náhodné vstupy |
| `--ref BIN` | | referenční program, se kterým se porovnají všechny výstupy |
| **Limity** | | |
| `--timeout S` | `1` | časový limit na jeden běh v sekundách |
| `--mem MB` | `256` | limit paměti pro build `-O2` |
| **Překlad** | | |
| `--src SOUBOR` | | zdrojový soubor, když je ve složce víc |
| `--cc g++\|gcc` | `g++` | překladač; `gcc` přeloží `.c` jako C |
| `--strict` | | překlad s `-Werror` |
| **Odhad složitosti** | | |
| `--complexity SOUBOR` | `<úloha>/complexity.py` | vlastní generátor vstupů |
| `--complexity-max N` | `6` | kolik nejhorších způsobů zvětšení změřit přesně |
| **Výstup** | | |
| `--show N` | `3` | kolik problémů vypsat podrobně v každé skupině |
| `--out SLOŽKA` | `vysledky/<úloha>` | kam uložit problémové vstupy; na začátku se vyprázdní, existující neprázdnou složku, kterou nevytvořil tester, odmítne |
| `-j N` | počet jader | kolik testů pouštět paralelně |

## Vývoj testeru

Tester má vlastní testy ve složce [tests/](tests/): unit testy jednotlivých částí a end-to-end testy,
které pouštějí celý tester na malé programy se známou chybou ([tests/fixtures/](tests/fixtures/)).

```sh
python3 -m unittest discover -s tests            # vše (~1 min)
PT_FAST=1 python3 -m unittest discover -s tests  # bez odhadu složitosti (~25 s)
```

Pusťte je hlavně po úpravě heuristik (odhad složitosti, štábní kultura, generování vstupů). Tyhle
části se dají rozbít, aniž by to bylo na první pohled vidět.
