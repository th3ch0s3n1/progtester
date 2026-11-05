/* Chyba: konec vstupu (EOF) bere jako nespravny vstup. */
#include <stdio.h>

int main(void)
{
    long long sum = 0, x;
    printf("Zadejte cisla:\n");
    while (1) {
        if (scanf("%lld", &x) != 1) {
            printf("Nespravny vstup.\n");
            return 1;
        }
        if (__builtin_add_overflow(sum, x, &sum)) {
            printf("Nespravny vstup.\n");
            return 1;
        }
        printf("Soucet: %lld\n", sum);
    }
}
