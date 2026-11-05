#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Vrati dvojnasobek. */
int twice(int x)
{
    return 2 * x;
}

#ifndef __PROGTEST__
int main(void)
{
    int y;
    assert(twice(2) == 4);
    /* prirazeni na nejvyssi urovni - vlastni assert ho nerozlozi, pouzije se standardni */
    assert(y = twice(0));
    assert(twice(3) == 7);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
