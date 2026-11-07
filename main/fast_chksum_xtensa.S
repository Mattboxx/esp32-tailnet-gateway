/* SPDX-License-Identifier: MIT
 * Internet checksum inner loop for Xtensa LX7 (ESP32-S3), Mattboxx 2026-11-07.
 *
 * lwIP's checksum (LWIP_CHKSUM_ALGORITHM 2) adds one 16-bit word per loop
 * iteration, about 3.5 cycles per byte measured on the board for the UDP
 * checksum of every WireGuard packet sent. This loop adds eight halfwords
 * per zero-overhead iteration (LBEG/LEND/LCOUNT, no branch) into two
 * accumulators, with each load issued two instructions before its use.
 *
 * uint32_t tsr_csum_halfwords(const void *p, uint32_t nhalf);
 *   p:     2-byte aligned
 *   nhalf: number of 16-bit words, at most 65535 (no 32-bit overflow:
 *          65535 * 65535 < 2^32)
 *   returns the plain 32-bit sum of the halfwords as read from memory
 *   (native little-endian), not folded; the C caller folds it exactly as
 *   lwip_standard_chksum() does and checks this routine against lwIP
 *   before first use (main/fast_chksum.c).
 *
 * Registers: a2 p, a3 nhalf, a4/a5 accumulators, a6 count, a7..a10 loads.
 */
#if defined(__XTENSA__)

#if defined(TSR_CRYPTO_IN_FLASH) && TSR_CRYPTO_IN_FLASH
    .section .text.tsr_csum_halfwords, "ax"
#else
    .section .iram1.tsr_csum_halfwords, "ax"
#endif
    .literal_position
    .align  4
    .global tsr_csum_halfwords
    .type   tsr_csum_halfwords, @function
tsr_csum_halfwords:
    entry   a1, 32
    movi.n  a4, 0
    movi.n  a5, 0
    srli    a6, a3, 3               /* blocks of eight halfwords */
    loopnez a6, .Lblocks_done
    l16ui   a7, a2, 0
    l16ui   a8, a2, 2
    l16ui   a9, a2, 4
    l16ui   a10, a2, 6
    add.n   a4, a4, a7
    add.n   a5, a5, a8
    l16ui   a7, a2, 8
    l16ui   a8, a2, 10
    add.n   a4, a4, a9
    add.n   a5, a5, a10
    l16ui   a9, a2, 12
    l16ui   a10, a2, 14
    add.n   a4, a4, a7
    add.n   a5, a5, a8
    addi    a2, a2, 16
    add.n   a4, a4, a9
    add.n   a5, a5, a10
.Lblocks_done:
    extui   a6, a3, 0, 3            /* zero to seven halfwords left */
    loopnez a6, .Ltail_done
    l16ui   a7, a2, 0
    addi.n  a2, a2, 2
    add.n   a4, a4, a7
.Ltail_done:
    add.n   a2, a4, a5
    retw.n
    .size   tsr_csum_halfwords, . - tsr_csum_halfwords

#endif /* __XTENSA__ */
