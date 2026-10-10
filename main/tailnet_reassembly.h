/* Private, bounded receive-DNAT reassembly; called on the TCP/IP core.
 * SPDX-License-Identifier: MIT */
#pragma once
#include "lwip/pbuf.h"
#include "lwip/netif.h"

/* Consumes every fragment, returning an owned complete packet or NULL. */
struct pbuf *tailnet_reassemble(struct pbuf *fragment,struct netif *input);

/* Best-effort idle expiry, queued by the existing forwarding manager.
 * A full queue or allocation failure is harmless; incoming fragments also
 * expire old contexts on the core, without allocating a timeout. */
void tailnet_reassembly_refresh(void);
