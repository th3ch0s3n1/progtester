/* progtester: behova cast assertu z pt/include/assert.h (preklada se zvlast jako C a prilinkuje se).
 *
 * Hlaseni jde do souboru z promenne PT_ASSERT_LOG (strojove, oddelene tabulatorem), aby se
 * nemichalo s vystupem programu; bez ni na stderr pro cloveka:
 *   F <radek> <vyraz> <hodnoty>     selhany assert (vypisuje se jen prvnich MAX_REPORTED)
 *   S <proslo> <selhalo> <radek>    souhrn pri normalnim konci (radek posledniho splneneho)
 *   C <signal> <radek> <radek>      pad: assert, ktery se prave vyhodnocoval (0 = zadny), posledni splneny
 *   T <radek> <radek>               casovy limit z PT_ASSERT_TIMEOUT_MS, stejne udaje
 */
#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

#define MAX_REPORTED 100
#define MAX_DEPTH 64

static long passed, failed;
static int stack[MAX_DEPTH], depth, last_ok;
static int log_fd = 2, machine;

static void put(const char *s) {
    size_t n = strlen(s);
    while (n > 0) {
        ssize_t w = write(log_fd, s, n);
        if (w <= 0) return;
        s += w;
        n -= (size_t)w;
    }
}

static void put_num(long v) {  /* bez printf - vola se i z obsluhy signalu */
    char buf[24], *p = buf + sizeof buf - 1;
    int neg = v < 0;
    unsigned long u = neg ? -(unsigned long)v : (unsigned long)v;
    *p = 0;
    do { *--p = (char)('0' + u % 10); u /= 10; } while (u);
    if (neg) *--p = '-';
    put(p);
}

static int current(void) { return depth > 0 ? stack[0] : 0; }  /* assert z main(), ne vnoreny */

void pt_assert_begin(int line) {
    if (depth < MAX_DEPTH) stack[depth] = line;
    depth++;
}

void pt_assert_end(int ok, const char *expr, const char *file, int line, const char *detail) {
    if (depth > 0) depth--;
    if (ok) {
        passed++;
        last_ok = line;
        return;
    }
    if (++failed > MAX_REPORTED) return;
    if (machine) {
        put("F\t"); put_num(line); put("\t"); put(expr); put("\t"); put(detail ? detail : ""); put("\n");
    } else {
        put(file); put(":"); put_num(line); put(": assert("); put(expr); put(") selhal");
        if (detail && *detail) { put(": "); put(detail); }
        put("\n");
    }
}

static void summary(void) {
    if (machine) {
        put("S\t"); put_num(passed); put("\t"); put_num(failed); put("\t"); put_num(last_ok); put("\n");
    } else {
        put_num(passed); put(" assertu proslo, "); put_num(failed); put(" selhalo\n");
    }
}

static void on_crash(int sig) {
    put("C\t"); put_num(sig); put("\t"); put_num(current()); put("\t"); put_num(last_ok); put("\n");
    signal(sig, SIG_DFL);
    raise(sig);
}

static void on_alarm(int sig) {
    put("T\t"); put_num(current()); put("\t"); put_num(last_ok); put("\n");
    signal(sig, SIG_DFL);
    raise(SIGKILL);
}

/* s ASan nechame padani na nem - jeho hlaseni je podrobnejsi */
extern void __asan_init(void) __attribute__((weak));

__attribute__((constructor)) static void pt_assert_init(void) {
    const char *log = getenv("PT_ASSERT_LOG");
    if (log && *log) {
        int fd = open(log, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
        if (fd >= 0) {
            log_fd = fd;
            machine = 1;
        }
    }
    atexit(summary);
    if (machine) {
        int sigs[] = {SIGABRT, SIGSEGV, SIGBUS, SIGFPE, SIGILL};
        size_t n = __asan_init ? 1 : sizeof sigs / sizeof *sigs;  /* abort (vyjimka) ASan nehlasi */
        for (size_t i = 0; i < n; i++) signal(sigs[i], on_crash);
    }
    const char *ms = getenv("PT_ASSERT_TIMEOUT_MS");
    if (ms && atol(ms) > 0) {
        long t = atol(ms);
        struct itimerval it = {{0, 0}, {t / 1000, (t % 1000) * 1000}};
        signal(SIGALRM, on_alarm);
        setitimer(ITIMER_REAL, &it, NULL);
    }
}
