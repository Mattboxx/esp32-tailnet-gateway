/* Tailnet (MagicDNS) names for devices behind the gateway.
 *
 * When switched on, the AP-side DNS relay answers A queries for tailnet peer
 * names itself: the short name ("nas") and the full MagicDNS name
 * ("nas.tail1234.ts.net", or a Headscale base domain) resolve to the peer's
 * 100.x address. Unknown names inside the tailnet domain get NXDOMAIN and
 * are never sent to the public resolver; everything else is forwarded as
 * before. Optionally the relay also listens on the uplink address, for LAN
 * devices that use the gateway as their DNS server.
 *
 * A name is not access: reaching the peer still depends on the gateway's
 * routes, firewall and the tailnet policy. Off by default; off, the relay
 * does exactly what it did before.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define TN_NAME_MAX 64
#define TN_TTL 60

/* Core (pure, host-tested). `peer` returns false past the last peer. */
typedef bool (*tn_peer_fn)(void *ctx, int index, char fqdn[TN_NAME_MAX], uint32_t *ip_nbo);
int tailnet_names_answer(const uint8_t *query, int len, uint8_t *out, int cap, tn_peer_fn peer, void *ctx);

/* Firmware. */
void tailnet_names_init(void);                 /* after dns_relay_init */
void tailnet_names_uplink(uint32_t ip_nbo);    /* uplink address, 0 when down */
void tailnet_names_get(bool *enabled, bool *lan);
esp_err_t tailnet_names_set(bool enabled, bool lan);   /* persist, then apply */
#include "esp_http_server.h"
esp_err_t tailnet_names_register_http(httpd_handle_t server);
