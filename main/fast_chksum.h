#pragma once

/* Faster UDP/TCP checksum (ip_chksum_pseudo) for IPv4.
 *
 * Every lwIP call of ip_chksum_pseudo() is linked to __wrap_ip_chksum_pseudo
 * (-Wl,--wrap, main/CMakeLists.txt). IPv4 sums use the Xtensa loop of
 * fast_chksum_xtensa.S with the exact folding of lwIP's algorithm 2; IPv6
 * and any build without the loop use lwIP's own function. Before its first
 * use the loop is compared with lwIP on random data, every alignment, odd
 * lengths and odd pbuf chains; if any result differs lwIP's function is
 * used from then on. */

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    bool     checked;         /* self-test has run */
    bool     active;          /* the fast path is in use */
    uint32_t cycles_fast;     /* 1,400-byte checksum, fast path (self-test) */
    uint32_t cycles_lwip;     /* the same buffer, lwIP's function */
} fast_chksum_status_t;

void fast_chksum_status(fast_chksum_status_t *out);
