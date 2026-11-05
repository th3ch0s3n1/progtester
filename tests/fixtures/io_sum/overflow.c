/* Chyba: cisla uklada do pole pevne velikosti bez kontroly - pro vic nez 4 cisla pise mimo pole. */
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    long long *nums = (long long *)malloc(4 * sizeof(*nums));
    long long sum = 0, x;
    int n = 0, r;
    printf("Zadejte cisla:\n");
    while ((r = scanf("%lld", &x)) == 1) {
        nums[n++] = x;
        if (__builtin_add_overflow(sum, x, &sum)) {
            printf("Nespravny vstup.\n");
            free(nums);
            return 1;
        }
        printf("Soucet: %lld\n", sum);
    }
    free(nums);
    if (r != EOF) {
        printf("Nespravny vstup.\n");
        return 1;
    }
    return 0;
}
