/* Mattboxx Edition changes: Copyright (C) 2026 Mattboxx, GPL-3.0-only (LICENSE,
 * LICENSE-EXCEPTION.md). Ported from Csontikka/esp32-tailscale-subnet-router, whose
 * code keeps its MIT licence (licenses/upstream/, NOTICE.md). */
/* Tailscale PeerAPI DNS service. Original implementation: 5queezer/Csontikka.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void peer_dns_start(void);
bool peer_dns_is_running(void);
/* Internal RAM the exit-node DNS server took when it started (bytes, 0 if it
 * never started): free internal heap and sockets before vs after start. */
int32_t peer_dns_start_internal_bytes(void);
int32_t peer_dns_start_sockets(void);
#ifdef __cplusplus
}
#endif
