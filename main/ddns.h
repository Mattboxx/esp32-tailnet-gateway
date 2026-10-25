/* Dynamic DNS: keeps a public name pointing at the home connection.
 *
 * Providers: DuckDNS, Cloudflare (an existing A record, via an API token
 * limited to DNS edit) and a custom HTTPS URL with an {ip} placeholder. The
 * public address comes from Tailscale's STUN result. Without it, DuckDNS and
 * custom URLs without {ip} let the provider use the address the request
 * comes from, and Cloudflare asks its own trace endpoint
 * (www.cloudflare.com/cdn-cgi/trace): no third lookup service is involved.
 *
 * Updates when the address changes, otherwise once a day; failures back off
 * up to an hour. HTTPS with certificate verification only; the token is
 * write-only in the API. Off by default: off, there is no timer and no task.
 * The name only points at the router: nothing is opened or forwarded.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

enum {DDNS_OFF = 0, DDNS_DUCKDNS, DDNS_CLOUDFLARE, DDNS_CUSTOM};
#define DDNS_REFRESH_S (24u * 3600u)
#define DDNS_BACKOFF_MAX_S 3600u
#define DDNS_BLIND_S 1800u

typedef struct {
    uint8_t provider;
    char name[128];      /* DuckDNS sub-domains (a,b) or Cloudflare record name */
    char zone[40];       /* Cloudflare zone id */
    char token[128];     /* secret: DuckDNS token / Cloudflare API token */
    char url[200];       /* custom: https://...{ip}... (may carry a secret) */
} ddns_config_t;

typedef struct {
    uint32_t last_ip;          /* network order; 0 = never updated */
    uint32_t last_ok_s;        /* uptime of the last success */
    uint32_t next_try_s;       /* uptime before which nothing is sent */
    uint32_t backoff_s;
    bool ever;
} ddns_state_t;

/* Core (pure, host-tested). */
bool ddns_config_valid(const ddns_config_t *c, char *why, size_t cap);
/* ip_nbo 0 = public address unknown. */
bool ddns_due(const ddns_state_t *st, uint8_t provider, uint32_t ip_nbo, uint32_t now_s);
void ddns_result(ddns_state_t *st, bool ok, uint32_t ip_nbo, uint32_t now_s);
/* Request for DuckDNS / custom (empty ip = provider uses the source address). */
bool ddns_build_url(const ddns_config_t *c, uint32_t ip_nbo, char *out, size_t cap);
/* "ip=203.0.113.7" line of a Cloudflare trace answer; false if absent or not IPv4. */
bool ddns_parse_trace(const char *text, uint32_t *ip_nbo);

/* Firmware. */
void ddns_init(void);
uint8_t ddns_provider(void);          /* DDNS_OFF when off */
bool ddns_last_update_ok(void);       /* the newest attempt succeeded */
#include "esp_http_server.h"
esp_err_t ddns_register_http(httpd_handle_t server);
