#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Chyba: zaporna cisla nepreklopi. */
int absVal(int x)
{
    return x;
}

/* Vrati ukazatel na prvni vyskyt znaku, nebo NULL. */
const char *findChar(const char *s, char c)
{
    return strchr(s, c);
}

double third(void)
{
    return 0.1 + 0.2;
}

#ifndef __PROGTEST__
int main(void)
{
    int idx = 3;
    assert(absVal(5) == 5);
    assert(absVal(-5) == 5);
    assert(absVal(-7) == 7 && idx == 3);
    assert(findChar("abc", 'b') != NULL);
    assert(findChar("abc", 'x') == NULL);
    assert(!absVal(0));
    assert(idx & 1);
    assert(third() == 0.3);
    assert(fabs(third() - 0.3) < 1e-12);
    assert(idx ? absVal(1) == 1 : 0);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
