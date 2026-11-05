/* Spravne, ale pomale: po kazdem cisle secte znovu vsechna dosavadni - O(n^2). */
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    long long *nums = NULL, x;
    size_t n = 0, cap = 0;
    int r;
    printf("Zadejte cisla:\n");
    while ((r = scanf("%lld", &x)) == 1) {
        if (n == cap) {
            cap = cap ? 2 * cap : 16;
            long long *tmp = (long long *)realloc(nums, cap * sizeof(*nums));
            if (!tmp) {
                free(nums);
                return 1;
            }
            nums = tmp;
        }
        nums[n++] = x;
        long long sum = 0;
        for (size_t i = 0; i < n; i++) {
            if (__builtin_add_overflow(sum, nums[i], &sum)) {
                printf("Nespravny vstup.\n");
                free(nums);
                return 1;
            }
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
