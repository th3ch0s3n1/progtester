#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#endif /* __PROGTEST__ */

int square(int x);

/* Soucet ctvercu - pouziva pomocnou funkci, ktera je omylem jen v testovaci casti. */
int sumSquares(int a, int b)
{
    return square(a) + square(b);
}

#ifndef __PROGTEST__
int square(int x)
{
    return x * x;
}

int main(void)
{
    assert(sumSquares(1, 2) == 5);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
