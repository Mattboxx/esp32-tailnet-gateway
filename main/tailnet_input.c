/* Enforce listener policy where the SDK processes IPv4 input, not at the
 * earlier physical/tunnel callback that queues packets to tcpip_thread.
 * SPDX-License-Identifier: MIT */
#include "tailnet_forward.h"
#include "lwip/tcpip.h"
#include "lwip/ip4.h"

err_t __real_ip4_input(struct pbuf *packet, struct netif *input);

err_t __wrap_ip4_input(struct pbuf *packet, struct netif *input)
{
    LWIP_ASSERT_CORE_LOCKED();
    if (!tailnet_forward_allow_ipv4_packet(packet, input)) {
        pbuf_free(packet);
        return ERR_OK;
    }
    return __real_ip4_input(packet, input);
}
