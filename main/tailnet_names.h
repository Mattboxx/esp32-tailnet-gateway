/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
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
 * The gateway's own MagicDNS name is answered too. With the tailnet DNS
 * settings switched on, extra records are answered, names under a split-DNS
 * route go to that route's resolver and, when the admin console overrides
 * local DNS, other names go to the tailnet's resolver while the tunnel is up.
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

#define TN_QNAME_MAX 256

/* Core (pure, host-tested). `peer` returns false past the last peer. */
typedef bool (*tn_peer_fn)(void *ctx, int index, char fqdn[TN_NAME_MAX], uint32_t *ip_nbo);
int tailnet_names_answer(const uint8_t *query, int len, uint8_t *out, int cap, tn_peer_fn peer, void *ctx);
/* Question of a standard one-question query (lower case, no final dot);
 * the offset after it, or 0. */
int tailnet_names_question(const uint8_t *q, int len, char name[TN_QNAME_MAX], uint16_t *type);
/* A peer (short or full name); `in_domain` tells an unknown name inside the
 * tailnet domain, which must never be forwarded. */
bool tailnet_names_match(const char *name, tn_peer_fn peer, void *ctx, uint32_t *ip_nbo, bool *in_domain);
/* Response to `q` whose question ends at `end`: the A record when found and
 * asked for (A/ANY), no data for other types, NXDOMAIN when not found. */
int tailnet_names_reply(const uint8_t *q, int end, uint8_t *out, int cap, bool found, uint32_t ip_nbo, uint16_t type);
/* An A query with recursion desired; length, or 0 for an invalid name. */
int tailnet_names_query(const char *name, uint16_t id, uint8_t *buf, int cap);
/* The answer to `query`: 1 with the first IPv4 address, 0 for NXDOMAIN or
 * no address, -1 when it is not a valid answer to that query. */
int tailnet_names_parse_a(const uint8_t *r, int rlen, const uint8_t *query, int qlen, uint32_t *ip_nbo);

/* Firmware. */
void tailnet_names_init(void);                 /* after dns_relay_init */
void tailnet_names_uplink(uint32_t ip_nbo);    /* uplink address, 0 when down */
void tailnet_names_get(bool *enabled, bool *lan);
esp_err_t tailnet_names_set(bool enabled, bool lan);   /* persist, then apply */
/* Tailnet DNS settings (extra records, split DNS, global resolvers) and the
 * gateway's own lookups (MQTT, ntfy, HTTP...) through tailnet names. Both off
 * by default, kept in their own record so an older image keeps the others. */
void tailnet_names_get_ext(bool *dns_config, bool *self_resolve);
esp_err_t tailnet_names_set_ext(bool dns_config, bool self_resolve);
/* NVS record of the switches (enabled bit 0, LAN listener bit 1). */
#include "nvs_flags.h"
extern const nvs_flags_t tailnet_names_flags;
extern const nvs_flags_t tailnet_names_ext_flags;
#include "esp_http_server.h"
esp_err_t tailnet_names_register_http(httpd_handle_t server);
