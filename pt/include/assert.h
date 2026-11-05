/* progtester: assert pro testovaci main() u uloh "napis funkci".
 *
 * Proti standardnimu assertu:
 *  - neukonci program - selhani se zapocita a testy bezi dal (vidis vsechny chyby najednou),
 *  - u porovnani vypise hodnoty obou stran (jen C++, napr. "dateToIndex(1, 1, 2000, &idx) == 1"
 *    -> "0 == 1"); g++ preklada jako C++ i soubory .c, takze to funguje i pro C kod,
 *  - pri padu / timeoutu rekne, u ktereho assertu se to stalo.
 *
 * Pouziva se jen pri lokalnim testovani (slozka je v -I), progtest ma svuj vlastni assert.
 * Behova cast (pocitadla, hlaseni, signaly) je v pt/assert_rt.c, aby tento soubor
 * nemusel vkladat dalsi hlavicky a nemichal je do jmen v testovanem programu.
 */
#pragma GCC system_header
#include_next <assert.h>

#ifndef NDEBUG

#ifndef PT_ASSERT_DECL
#define PT_ASSERT_DECL
#ifdef __cplusplus
extern "C" {
#endif
void pt_assert_begin(int line);
void pt_assert_end(int ok, const char *expr, const char *file, int line, const char *detail);
#ifdef __cplusplus
}
#endif
#endif /* PT_ASSERT_DECL */

#ifdef __cplusplus

#ifndef PT_ASSERT_CXX
#define PT_ASSERT_CXX
#include <cstdint>
#include <limits>
#include <ostream>
#include <sstream>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace pt_assert {

/* Rozklad vyrazu (jako Catch2): Dec{} <= a == b  se vyhodnoti jako  (Dec{} <= a) == b,
 * protoze <= ma vyssi prioritu nez == a stejnou jako <, >. Leva strana se tak zachyti
 * zvlast a da se vypsat. Pro && || ?: se pouzije explicit operator bool - zkracene
 * vyhodnoceni zustava zachovane. */

template <class T, class = void> struct printable : std::false_type {};
template <class T>
struct printable<T, std::void_t<decltype(std::declval<std::ostream &>() << std::declval<const T &>())>>
    : std::true_type {};

inline std::string escape(const std::string &s) {
    std::string r;
    for (char ch : s) {
        if (ch == '\n') r += "\\n";
        else if (ch == '\t') r += "\\t";
        else if (ch == '\r') r += "\\r";
        else if (ch == '"') r += "\\\"";
        else r += ch;
        if (r.size() > 80) { r += "..."; break; }
    }
    return r;
}

template <class T> std::string show(const T &v) {
    using U = std::remove_cv_t<std::decay_t<T>>;
    std::ostringstream os;
    if constexpr (std::is_same_v<U, bool>) {
        os << (v ? "true" : "false");
    } else if constexpr (std::is_same_v<U, char> || std::is_same_v<U, signed char> ||
                         std::is_same_v<U, unsigned char>) {
        int code = static_cast<int>(v);
        if (code >= 32 && code < 127) os << '\'' << static_cast<char>(v) << "' (" << code << ')';
        else os << code;
    } else if constexpr (std::is_same_v<U, char *> || std::is_same_v<U, const char *>) {
        if (!v) os << "NULL";
        else os << '"' << escape(v) << '"';
    } else if constexpr (std::is_same_v<U, std::string>) {
        os << '"' << escape(v) << '"';
    } else if constexpr (std::is_floating_point_v<U>) {
        /* nejkratsi zapis, ktery se precte zpet jako stejne cislo (0.3, ne 0.29999999999999999) */
        for (int prec = 6; prec <= std::numeric_limits<U>::max_digits10; prec++) {
            std::ostringstream t;
            t.precision(prec);
            t << v;
            std::istringstream back(t.str());
            U r{};
            if ((back >> r) && r == v) return t.str();
        }
        os.precision(std::numeric_limits<U>::max_digits10);
        os << v;
    } else if constexpr (std::is_enum_v<U>) {
        os << +static_cast<std::underlying_type_t<U>>(v);
    } else if constexpr (std::is_null_pointer_v<U>) {
        os << "nullptr";
    } else if constexpr (std::is_pointer_v<U>) {
        if (!v) os << "NULL";
        else os << reinterpret_cast<const void *>(v);
    } else if constexpr (printable<U>::value) {
        os << v;
    } else {
        return "?";
    }
    return os.str();
}

/* p == NULL: NULL je v C++ celociselna 0 (__null), po predani sablonou uz to neni
 * konstanta nuloveho ukazatele -> prevest na ukazatel stejneho typu */
template <class Other, class V> decltype(auto) adj(const V &v) {
    using O = std::decay_t<Other>;
    if constexpr (std::is_pointer_v<O> && std::is_integral_v<V>)
        return v ? reinterpret_cast<O>(static_cast<std::intptr_t>(v)) : static_cast<O>(nullptr);
    else
        return (v);
}

struct Frame { bool noted = false; std::string text; };
inline std::vector<Frame> &frames() { static std::vector<Frame> f; return f; }

/* zapamatuje si prvni nesplnene porovnani v ramci prave vyhodnocovaneho assertu */
inline void note(const std::string &text) {
    auto &f = frames();
    if (!f.empty() && !f.back().noted) { f.back().noted = true; f.back().text = text; }
}

struct Res {
    bool ok;
    explicit operator bool() const { return ok; }
};

template <class T> struct Lhs {
    T v;  /* reference na levou stranu, nebo hodnota (vysledek &, |, ^) */
    explicit operator bool() const { return static_cast<bool>(v); }
};

struct Dec {};
template <class T> Lhs<const T &> operator<=(Dec, const T &v) { return {v}; }

#define PT_ASSERT_CMP(op)                                                               \
    template <class T, class U> Res operator op(const Lhs<T> &l, const U &r) {          \
        bool ok = static_cast<bool>(adj<U>(l.v) op adj<T>(r));                          \
        if (!ok) note(show(l.v) + " " #op " " + show(r));                               \
        return {ok};                                                                    \
    }
PT_ASSERT_CMP(==)
PT_ASSERT_CMP(!=)
PT_ASSERT_CMP(<)
PT_ASSERT_CMP(<=)
PT_ASSERT_CMP(>)
PT_ASSERT_CMP(>=)
#undef PT_ASSERT_CMP

#define PT_ASSERT_BIT(op)                                                               \
    template <class T, class U> auto operator op(const Lhs<T> &l, const U &r)           \
        -> Lhs<decltype(l.v op r)> { return {l.v op r}; }                               \
    template <class U> bool operator op(const Res &l, const U &r) {                     \
        return static_cast<bool>(l.ok op r);                                            \
    }
PT_ASSERT_BIT(&)
PT_ASSERT_BIT(|)
PT_ASSERT_BIT(^)
#undef PT_ASSERT_BIT

inline bool truth(const Res &r) { return r.ok; }
template <class T> bool truth(const Lhs<T> &l) {
    bool ok = static_cast<bool>(l.v);
    if (!ok && !std::is_same_v<std::remove_cv_t<std::remove_reference_t<T>>, bool>) note(show(l.v));
    return ok;
}
template <class T> bool truth(const T &v) { return static_cast<bool>(v); }

inline void begin(int line) { frames().emplace_back(); pt_assert_begin(line); }
inline void end(bool ok, const char *expr, const char *file, int line) {
    auto &f = frames();
    std::string detail;
    if (!f.empty()) { detail = std::move(f.back().text); f.pop_back(); }
    pt_assert_end(ok, expr, file, line, detail.c_str());
}

}  // namespace pt_assert
#endif /* PT_ASSERT_CXX */

#undef assert
#define assert(...)                                                                     \
    (::pt_assert::begin(__LINE__),                                                      \
     ::pt_assert::end(::pt_assert::truth(::pt_assert::Dec{} <= __VA_ARGS__),            \
                      #__VA_ARGS__, __FILE__, __LINE__))

#else /* C: bez rozkladu na hodnoty, ale s pocitanim a bez ukonceni programu */

#undef assert
#define assert(...)                                                                     \
    (pt_assert_begin(__LINE__),                                                         \
     pt_assert_end((__VA_ARGS__) ? 1 : 0, #__VA_ARGS__, __FILE__, __LINE__, ""))

#endif /* __cplusplus */

#endif /* NDEBUG */
