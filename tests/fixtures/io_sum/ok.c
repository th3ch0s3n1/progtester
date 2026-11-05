/* Spravne reseni: cte cela cisla az do konce vstupu a po kazdem vypise prubezny soucet. */
#include <stdio.h>

int main(void)
{
    long long sum = 0, x;
    int r;
    printf("Zadejte cisla:\n");
    while ((r = scanf("%lld", &x)) == 1) {
        if (__builtin_add_overflow(sum, x, &sum)) {
            printf("Nespravny vstup.\n");
            return 1;
        }
        printf("Soucet: %lld\n", sum);
    }
    if (r != EOF) {
        printf("Nespravny vstup.\n");
        return 1;
    }
    return 0;
}
