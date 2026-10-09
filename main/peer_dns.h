/* Tailscale PeerAPI DNS service. Original implementation: 5queezer/Csontikka.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
void peer_dns_start(void);
bool peer_dns_is_running(void);
#ifdef __cplusplus
}
#endif
