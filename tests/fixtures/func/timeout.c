#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Pocet kroku Collatzovy posloupnosti; pro 0 se zacykli. */
int collatz(unsigned x)
{
    int steps = 0;
    while (x != 1) {
        x = (x % 2) ? 3 * x + 1 : x / 2;
        steps++;
    }
    return steps;
}

#ifndef __PROGTEST__
int main(void)
{
    assert(collatz(1) == 0);
    assert(collatz(6) == 8);
    assert(collatz(0) == 0);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
