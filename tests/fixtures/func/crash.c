#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Vrati prvek pole na indexu, pro idx < 0 omylem dereferencuje NULL. */
int getItem(const int *arr, int idx)
{
    if (idx < 0) {
        const int *p = NULL;
        return *p;
    }
    return arr[idx];
}

#ifndef __PROGTEST__
int main(void)
{
    int a[] = {1, 2, 3};
    assert(getItem(a, 0) == 1);
    assert(getItem(a, 2) == 3);
    assert(getItem(a, -1) == 0);
    assert(getItem(a, 1) == 2);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
