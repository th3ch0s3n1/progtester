#ifndef __PROGTEST__
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#endif /* __PROGTEST__ */

/* Vrati kopii retezce - volajici ji ma uvolnit, test to nedela. */
char *dup(const char *s)
{
    char *r = (char *)malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

#ifndef __PROGTEST__
int main(void)
{
    assert(strcmp(dup("ahoj"), "ahoj") == 0);
    return EXIT_SUCCESS;
}
#endif /* __PROGTEST__ */
