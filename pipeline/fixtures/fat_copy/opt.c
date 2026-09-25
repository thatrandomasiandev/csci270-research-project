/* Same observable result as stock.c; no fat-struct copies. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    uint64_t a[32];
} Fat;

__attribute__((noinline)) static void work(Fat *x) {
    x->a[0] += 1;
}

int main(int argc, char **argv) {
    long n = argc > 1 ? strtol(argv[1], NULL, 10) : 8000000L;
    Fat x = {0};
    for (long i = 0; i < n; i++) {
        work(&x);
    }
    printf("%llu\n", (unsigned long long)x.a[0]);
    return 0;
}
