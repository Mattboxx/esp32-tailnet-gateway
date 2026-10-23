#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "lwip/sockets.h"
#endif

/* ESP-IDF's HTTP server listens with PF_INET6 when lwIP IPv6 support is
 * enabled, so an IPv4 connection is exposed by getsockname/getpeername as an
 * IPv4-mapped IPv6 sockaddr (::ffff:a.b.c.d). Normalize only the two IPv4
 * representations; native IPv6 is not an IPv4 address and is refused.
 * Every caller that compares a socket address with an IPv4 interface or
 * keys state by client must use this, not a plain AF_INET check. */
static inline bool sockaddr_ipv4_nbo(const struct sockaddr_storage *address, uint32_t *ipv4_nbo)
{
    if (address->ss_family == AF_INET) {
        *ipv4_nbo = ((const struct sockaddr_in *)address)->sin_addr.s_addr;
        return true;
    }
    if (address->ss_family == AF_INET6) {
        const struct sockaddr_in6 *v6 = (const struct sockaddr_in6 *)address;
        if (!IN6_IS_ADDR_V4MAPPED(&v6->sin6_addr)) return false;
        memcpy(ipv4_nbo, &v6->sin6_addr.s6_addr[12], sizeof *ipv4_nbo);
        return true;
    }
    return false;
}
