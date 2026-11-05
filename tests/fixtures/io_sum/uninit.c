/* Chyba: soucet neni inicializovany (ASan to nepozna, valgrind ano). */
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    long long *sum = (long long *)malloc(sizeof(*sum));
    long long x;
    int r;
    printf("Zadejte cisla:\n");
    while ((r = scanf("%lld", &x)) == 1) {
        *sum += x;
        printf("Soucet: %lld\n", *sum);
    }
    free(sum);
    if (r != EOF) {
        printf("Nespravny vstup.\n");
        return 1;
    }
    return 0;
}
