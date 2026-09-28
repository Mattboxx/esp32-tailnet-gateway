#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../main/upstream_validation.h"

int main(void)
{
    char routes[640] = "";
    assert(route_list_add(routes, sizeof routes, "192.168.4.0/24"));
    assert(route_list_add(routes, sizeof routes, " 192.168.4.0/24 \r\n10.0.0.0/24\n10.0.0.0/24\n"));
    assert(!strcmp(routes, "192.168.4.0/24\n10.0.0.0/24"));
    assert(route_list_add(routes, sizeof routes, "fd7a:115c:a1e0:b1a::/96\n0.0.0.0/0\n::/0"));
    char small[4] = "abc";
    assert(!route_list_add(small, sizeof small, "x"));
    assert(!strcmp(small, "abc"));
    char exact[4] = "";
    assert(route_list_add(exact, sizeof exact, "abc"));
    assert(!route_list_add(exact, sizeof exact, "abcd"));
    assert(route_list_add(exact, sizeof exact, "\n abc\t\r\n"));
    assert(ipn_version_valid(""));
    assert(ipn_version_valid("1.98.9"));
    assert(ipn_version_valid("1.98.9-t00000000000-g00000000000"));
    assert(!ipn_version_valid("1.0\r\nInjected"));
    assert(!ipn_version_valid("012345678901234567890123456789012"));
    const char *token = "0123456789abcdef";
    assert(session_cookie_matches("ts_session=0123456789abcdef", token));
    assert(session_cookie_matches("a=b; ts_session=0123456789abcdef; c=d", token));
    assert(!session_cookie_matches("other_ts_session=0123456789abcdef", token));
    assert(!session_cookie_matches("a=ts_session=0123456789abcdef", token));
    assert(!session_cookie_matches("ts_session=0123456789abcdef0", token));
    assert(!session_cookie_matches("ts_session=0123456789abcde", token));
    assert(!session_cookie_matches("ts_session=1123456789abcdef", token));
    assert(!session_cookie_matches(";;;; \t", token));
    char large[1800];
    memset(large, 'x', 1500);
    strcpy(large + 1500, "; ts_session=0123456789abcdef; other=value");
    assert(session_cookie_matches(large, token));
    puts("PASS: route composition/deduplication/bounds, client version, exact long-cookie authentication");
    return 0;
}
