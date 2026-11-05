#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Vrati soucet cifer cisla (zaporne cislo bere v absolutni hodnote). */
int digitSum(long long x)
{
    if (x < 0)
        x = -x;
    int sum = 0;
    while (x > 0) {
        sum += (int)(x % 10);
        x /= 10;
    }
    return sum;
}

#ifndef __PROGTEST__
int main(void)
{
    assert(digitSum(0) == 0);
    assert(digitSum(9) == 9);
    assert(digitSum(123) == 6);
    assert(digitSum(-45) == 9);
    assert(digitSum(1000000007LL) == 8);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
