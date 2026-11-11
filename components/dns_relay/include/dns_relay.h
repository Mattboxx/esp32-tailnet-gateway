/* Mattboxx Edition changes: Copyright (C) 2026 Mattboxx, GPL-3.0-only (LICENSE,
 * LICENSE-EXCEPTION.md). The original code keeps the licence stated in its own
 * notice below (see also NOTICE.md and licenses/upstream/). */
/* DNS forwarder for AP clients.
 *
 * The ESP binds a UDP socket on the AP-side IP:53 and forwards every
 * query it receives to the configured upstream resolver, then sends the
 * response back to the originating client. Compared to handing the
 * upstream DNS to clients directly via DHCP Option 6, this protects AP
 * clients from stale-cache problems when the STA uplink (and hence the
 * effective upstream resolver) changes — clients always send queries to
 * the ESP and the ESP picks the live upstream at forward time.
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_netif.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Initialise the relay: spawns the forwarder task and loads enable +
 * upstream-override from NVS. Idempotent. The task self-pauses on
 * recvfrom while disabled, so the call is cheap when the operator
 * leaves the feature off. */
void dns_relay_init(void);

/* Enable / disable the relay at runtime (mirrored to NVS). When off,
 * the forwarder closes its bind socket; AP clients see no listener on
 * 53/udp and DHCP should hand out the direct upstream instead. */
void dns_relay_set_enabled(bool on);
bool dns_relay_is_enabled(void);

/* True iff the forwarder task is bound and ready to serve queries.
 * softap_set_dns_addr gates the "advertise AP IP as DNS server" path on
 * this so DHCP clients never get pointed at a resolver that isn't there
 * (e.g. during boot, after a bind failure, or while the relay is
 * transitioning to/from enabled). */
bool dns_relay_is_healthy(void);

/* Register a callback invoked on every health-state transition. Used by
 * main.c to re-run softap_set_dns_addr the moment the relay flips
 * healthy ↔ not-healthy so the DHCP-offered DNS follows the actual
 * relay availability. Pass NULL to clear. */
typedef void (*dns_relay_state_cb_t)(bool healthy);
void dns_relay_set_state_cb(dns_relay_state_cb_t cb);
/* Install before init. Returns the current Internet-facing interface. */
void dns_relay_set_uplink_provider(esp_netif_t *(*provider)(void));

/* Override the upstream resolver (network byte order).
 * Pass 0 to fall back to the active uplink DNS at forward time. */
void dns_relay_set_upstream(uint32_t ip_nbo);
uint32_t dns_relay_get_upstream(void);

/* Tell the relay which local IP to bind on. main.c calls this once
 * with the AP IP just after wifi_init_softap configures it, and again
 * whenever the AP IP changes (rare — operator-driven only). */
void dns_relay_set_bind_addr(uint32_t ip_nbo);

/* First-boot captive portal: answer every A query with this address (network
 * byte order) instead of relaying; 0 restores normal relaying. */
void dns_relay_set_captive(uint32_t answer_ip_nbo);

/* Runtime snapshot of the SPIRAM response cache + forwarder, for the
 * diagnostics page. Counters are cumulative since boot. */
typedef struct {
    uint32_t queries;      /* total client queries seen                     */
    uint32_t hits;         /* served from cache                             */
    uint32_t misses;       /* forwarded upstream (incl. uncacheable)        */
    uint32_t inserts;      /* responses written into the cache              */
    uint32_t evictions;    /* inserts that overwrote a different live entry */
    uint32_t stray;        /* upstream datagrams discarded: wrong source, ID or question */
    uint32_t entries;      /* currently-valid (unexpired) cache entries     */
    uint32_t capacity;     /* total cache slots                             */
    uint32_t cache_bytes;  /* SPIRAM footprint of the cache table           */
    uint32_t hit_pct;      /* hits*100/(hits+misses), 0 if no traffic yet   */
    uint8_t  enabled;      /* relay enabled                                 */
    uint8_t  healthy;      /* listener bound + serving                      */
} dns_relay_stats_t;

void dns_relay_get_stats(dns_relay_stats_t *out);

/* Optional listener on the uplink (LAN) address, for LAN devices that use
 * this gateway as their resolver. Off by default; `ip_nbo` is the current
 * uplink address (0 while it has none). */
void dns_relay_set_lan(bool on, uint32_t ip_nbo);
bool dns_relay_lan_listening(void);

/* Optional local resolver tried before the cache: returns the length of a
 * complete response written to `out`, or 0 to forward the query as usual.
 * Runs on the relay listener task; must not block. NULL = none (default). */
typedef int (*dns_relay_local_cb_t)(const uint8_t *query, int len, uint8_t *out, int cap);
void dns_relay_set_local_resolver(dns_relay_local_cb_t cb);

/* Optional upstream choice per forwarded query (e.g. a split-DNS route of
 * the tailnet): returns an IPv4 resolver (network byte order) or 0 for the
 * usual upstream. Runs on the relay listener task; must not block. */
typedef uint32_t (*dns_relay_route_cb_t)(const uint8_t *query, int len);
void dns_relay_set_route(dns_relay_route_cb_t cb);

#ifdef __cplusplus
}
#endif
