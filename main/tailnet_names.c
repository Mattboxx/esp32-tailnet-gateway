/* Tailnet names for devices behind the gateway; see tailnet_names.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: GPL-3.0-only */
#include "tailnet_names.h"
#include <string.h>

/* --- names core (begin) --- */
static char lower(char c) {return c >= 'A' && c <= 'Z' ? (char)(c - 'A' + 'a') : c;}

/* Question name as lowercase dotted text; returns the offset after the
 * question (type and class included), or 0 for anything malformed. */
static int read_question(const uint8_t *q, int len, char *name, size_t cap, uint16_t *type, uint16_t *cls)
{
    int at = 12;
    size_t n = 0;
    for (;;) {
        if (at >= len) return 0;
        unsigned label = q[at++];
        if (!label) break;
        if (label > 63 || at + (int)label > len || n + label + 2 > cap) return 0;   /* no compression in a question */
        if (n) name[n++] = '.';
        for (unsigned i = 0; i < label; i++) {
            char c = lower((char)q[at + i]);
            if (c == '.' || !c) return 0;
            name[n++] = c;
        }
        at += (int)label;
    }
    if (!n || at + 4 > len) return 0;
    name[n] = 0;
    *type = (uint16_t)(q[at] << 8 | q[at + 1]);
    *cls = (uint16_t)(q[at + 2] << 8 | q[at + 3]);
    return at + 4;
}

int tailnet_names_question(const uint8_t *q, int len, char name[TN_QNAME_MAX], uint16_t *type)
{
    if (!q || len < 17 || len > 1024) return 0;
    /* A standard query with one question and no answers. */
    if ((q[2] & 0xF8) != 0 || q[4] != 0 || q[5] != 1 || q[6] || q[7] || q[8] || q[9]) return 0;
    uint16_t cls;
    int end = read_question(q, len, name, TN_QNAME_MAX, type, &cls);
    return end && cls == 1 ? end : 0;
}

static bool in_zone(const char *name, const char *zone)
{
    size_t n = strlen(name), z = strlen(zone);
    return z && n >= z && !strcmp(name + n - z, zone) &&
           (n == z || name[n - z - 1] == '.');
}

bool tailnet_names_private_zone(const char *name, const char *live_zone, const char *saved_zone)
{
    if (live_zone && *live_zone) return in_zone(name, live_zone);
    return (saved_zone && in_zone(name, saved_zone)) || in_zone(name, "ts.net");
}

bool tailnet_names_match(const char *name, tn_peer_fn peer, void *ctx, uint32_t *ip_out, bool *in_domain)
{
    *in_domain = false;
    bool bare = !strchr(name, '.');
    size_t name_len = strlen(name), dots = 0;
    for (const char *c = name; *c; c++) dots += *c == '.';
    if (!bare && dots < 2) return false;                 /* MagicDNS names have at least two dots */
    uint32_t ip = 0;
    char fqdn[TN_NAME_MAX];
    for (int i = 0; i < 4096 && peer(ctx, i, fqdn, &ip); i++) {
        fqdn[TN_NAME_MAX - 1] = 0;
        for (char *c = fqdn; *c; c++) *c = lower(*c);
        size_t f = strlen(fqdn);
        while (f && fqdn[f - 1] == '.') fqdn[--f] = 0;
        const char *dot = strchr(fqdn, '.');
        if (!f || !ip) continue;
        size_t first = dot ? (size_t)(dot - fqdn) : f;
        if (!strcmp(name, fqdn) || (bare && name_len == first && !strncmp(name, fqdn, first))) {*ip_out = ip; return true;}
        /* The tailnet domain is whatever follows a peer's first label. */
        if (dot && name_len > f - first && !strcmp(name + name_len - (f - first), dot)) *in_domain = true;
    }
    return false;
}

int tailnet_names_reply(const uint8_t *q, int end, uint8_t *out, int cap, bool found, uint32_t ip, uint16_t type)
{
    bool answer = found && (type == 1 || type == 255);   /* A or ANY; others: no data */
    int total = end + (answer ? 16 : 0);
    if (!q || !out || end < 17 || total > cap) return 0;
    memcpy(out, q, (size_t)end);
    out[2] = (uint8_t)(0x84 | (q[2] & 0x01));             /* response, authoritative, keep RD */
    out[3] = (uint8_t)(0x80 | (found ? 0 : 3));          /* RA; NOERROR or NXDOMAIN */
    memset(out + 6, 0, 6);
    if (answer) {
        out[7] = 1;
        uint8_t *rr = out + end;
        const uint8_t head[] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, TN_TTL >> 8, TN_TTL & 0xFF, 0, 4};
        memcpy(rr, head, sizeof head);
        memcpy(rr + sizeof head, &ip, 4);
    }
    return total;
}

int tailnet_names_answer(const uint8_t *q, int len, uint8_t *out, int cap, tn_peer_fn peer, void *ctx)
{
    if (!q || !out || !peer || cap < 64) return 0;
    char name[TN_QNAME_MAX];
    uint16_t type;
    int end = tailnet_names_question(q, len, name, &type);
    if (!end) return 0;
    uint32_t ip = 0;
    bool in_domain, found = tailnet_names_match(name, peer, ctx, &ip, &in_domain);
    if (!found && !in_domain) return 0;                  /* not a tailnet name: forward */
    return tailnet_names_reply(q, end, out, cap, found, ip, type);
}

int tailnet_names_query(const char *name, uint16_t id, uint8_t *buf, int cap)
{
    if (!name || !buf || cap < 18) return 0;
    int at = 12;
    const char *p = name;
    memset(buf, 0, 12);
    buf[0] = (uint8_t)(id >> 8); buf[1] = (uint8_t)id;
    buf[2] = 0x01;                                       /* RD */
    buf[5] = 1;
    while (*p) {
        const char *dot = strchr(p, '.');
        size_t l = dot ? (size_t)(dot - p) : strlen(p);
        if (!l || l > 63 || at + 1 + (int)l + 5 > cap) return 0;
        buf[at++] = (uint8_t)l;
        memcpy(buf + at, p, l);
        at += (int)l;
        p += l;
        if (*p == '.') {p++; if (!*p) break;}
    }
    if (at == 12 || at - 12 > 254) return 0;
    buf[at++] = 0;
    buf[at++] = 0; buf[at++] = 1;                        /* A */
    buf[at++] = 0; buf[at++] = 1;                        /* IN */
    return at;
}

/* Skip a possibly compressed name; offset after it, or 0. */
static int skip_name(const uint8_t *r, int len, int at)
{
    for (int labels = 0; labels < 128; labels++) {
        if (at >= len) return 0;
        uint8_t l = r[at];
        if (!l) return at + 1;
        if ((l & 0xC0) == 0xC0) return at + 2 <= len ? at + 2 : 0;
        if (l & 0xC0) return 0;
        at += 1 + l;
    }
    return 0;
}

int tailnet_names_parse_a(const uint8_t *r, int rlen, const uint8_t *query, int qlen, uint32_t *ip_out)
{
    if (!r || !query || rlen < 12 || qlen < 17 || rlen > 4096) return -1;
    if (r[0] != query[0] || r[1] != query[1] || !(r[2] & 0x80) || (r[2] & 0x78)) return -1;
    if (((r[4] << 8) | r[5]) != 1 || rlen < qlen) return -1;
    for (int i = 12; i < qlen; i++)                      /* same question, any letter case */
        if (lower((char)r[i]) != lower((char)query[i])) return -1;
    int rcode = r[3] & 0x0F;
    if (rcode == 3) return 0;                            /* NXDOMAIN */
    if (rcode) return -1;                                /* SERVFAIL, REFUSED…: no verdict */
    int an = (r[6] << 8) | r[7], at = qlen;
    for (int i = 0; i < an && i < 32; i++) {
        at = skip_name(r, rlen, at);
        if (!at || at + 10 > rlen) return -1;
        uint16_t type = (uint16_t)(r[at] << 8 | r[at + 1]), cls = (uint16_t)(r[at + 2] << 8 | r[at + 3]);
        uint16_t rdlen = (uint16_t)(r[at + 8] << 8 | r[at + 9]);
        at += 10;
        if (at + rdlen > rlen) return -1;
        if (type == 1 && cls == 1 && rdlen == 4) {
            uint32_t ip;
            memcpy(&ip, r + at, 4);
            if (ip) {*ip_out = ip; return 1;}
        }
        at += rdlen;
    }
    return 0;                                            /* no IPv4 address */
}
/* --- names core (end) --- */

#ifdef ESP_PLATFORM
#include "dns_relay.h"
#include "json_guard.h"
#include "nvs_params.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "microlink.h"
#include "ml_dns_config.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "lwip/ip_addr.h"
#include "lwip/api.h"
#include <stdio.h>
#include <stdlib.h>

static bool s_enabled, s_lan;
static volatile bool s_dnscfg, s_self;
static volatile uint32_t s_uplink;
static char s_saved_zone[ML_DNS_NAME_MAX];
static portMUX_TYPE s_zone_lock = portMUX_INITIALIZER_UNLOCKED;
static SemaphoreHandle_t s_query_sem;   /* one routed lookup of the gateway's own at a time */

static bool private_name(const char *name)
{
    char self[ML_DNS_NAME_MAX], saved[ML_DNS_NAME_MAX];
    const char *dot = ml_dns_self_name(self) ? strchr(self, '.') : NULL;
    if (dot) return tailnet_names_private_zone(name, dot + 1, NULL);
    taskENTER_CRITICAL(&s_zone_lock);
    memcpy(saved, s_saved_zone, sizeof saved);
    taskEXIT_CRITICAL(&s_zone_lock);
    return tailnet_names_private_zone(name, NULL, saved);
}

void tailnet_names_remember_zone(void)
{
    char self[ML_DNS_NAME_MAX];
    const char *dot = ml_dns_self_name(self) ? strchr(self, '.') : NULL;
    if (!dot || !dot[1]) return;
    const char *zone = dot + 1;
    taskENTER_CRITICAL(&s_zone_lock);
    bool changed = strcmp(s_saved_zone, zone) != 0;
    taskEXIT_CRITICAL(&s_zone_lock);
    if (!changed || nvs_param_set_str("tsn_zone", zone) != ESP_OK) return;
    taskENTER_CRITICAL(&s_zone_lock);
    strlcpy(s_saved_zone, zone, sizeof s_saved_zone);
    taskEXIT_CRITICAL(&s_zone_lock);
}

/* Peers, then this gateway itself (its own MagicDNS name). */
static bool next_peer(void *ctx, int index, char fqdn[TN_NAME_MAX], uint32_t *ip)
{
    microlink_t *ml = ctx;
    int count = microlink_get_peer_count(ml);
    if (index > count) return false;
    if (index == count) {
        char self[ML_DNS_NAME_MAX];
        uint32_t own = microlink_get_vpn_ip(ml);
        if (!ml_dns_self_name(self) || !own) {fqdn[0] = 0; *ip = 0; return true;}
        snprintf(fqdn, TN_NAME_MAX, "%s", self);
        *ip = htonl(own);
        return true;
    }
    microlink_peer_info_t info = {0};
    if (microlink_get_peer_info(ml, index, &info) != ESP_OK) {fqdn[0] = 0; *ip = 0; return true;}
    memcpy(fqdn, info.hostname, TN_NAME_MAX);
    *ip = htonl(info.vpn_ip);
    return true;
}

/* An extra record from the admin console: exact, or a bare name completed
 * with the search domains. */
static bool extra_record(const char *name, uint32_t *ip)
{
    return s_dnscfg && (ml_dns_extra_lookup(name, ip) || (!strchr(name, '.') && ml_dns_extra_lookup_search(name, ip)));
}

static int resolve(const uint8_t *q, int len, uint8_t *out, int cap)
{
    microlink_t *ml = tailscale_get_microlink();
    char name[TN_QNAME_MAX];
    uint16_t type;
    int end = tailnet_names_question(q, len, name, &type);
    if (!end) return 0;
    uint32_t ip = 0;
    if (ml && extra_record(name, &ip)) return tailnet_names_reply(q, end, out, cap, true, ip, type);
    bool in_domain = false;
    bool found = ml && tailnet_names_match(name, next_peer, ml, &ip, &in_domain);
    if (found || in_domain) return tailnet_names_reply(q, end, out, cap, found, ip, type);
    int split = ml && s_dnscfg ? ml_dns_route(name, NULL) : ML_DNS_ROUTE_NONE;
    if (split == ML_DNS_ROUTE_LOCAL) return tailnet_names_reply(q, end, out, cap, false, 0, type);
    if (split == ML_DNS_ROUTE_FWD || !private_name(name)) return 0;
    /* During bootstrap use SERVFAIL so clients can retry after the netmap arrives. */
    int reply = tailnet_names_reply(q, end, out, cap, false, 0, type);
    if (reply > 0) out[3] = (out[3] & 0xf0) | 2;
    return reply;
}

/* Upstream for a forwarded query: a split-DNS route's resolver, else the
 * tailnet's own resolver when the admin console overrides local DNS and the
 * tunnel is up (a resolver behind a down tunnel would stall every lookup);
 * 0 keeps the relay's usual upstream. */
static uint32_t route(const uint8_t *q, int len)
{
    char name[TN_QNAME_MAX];
    uint16_t type;
    uint32_t addr = 0;
    if (!s_dnscfg || !tailnet_names_question(q, len, name, &type)) return 0;
    if (ml_dns_route(name, &addr) == ML_DNS_ROUTE_FWD) return addr;
    microlink_t *ml = tailscale_get_microlink();
    return ml && microlink_is_connected(ml) ? ml_dns_global_resolver() : 0;
}

static void apply(void)
{
    dns_relay_set_local_resolver(s_enabled ? resolve : NULL);
    dns_relay_set_route(s_enabled && s_dnscfg ? route : NULL);
    dns_relay_set_lan(s_enabled && s_lan, s_uplink);
    if (s_self && !s_query_sem) {
        s_query_sem = xSemaphoreCreateBinary();
        if (s_query_sem) xSemaphoreGive(s_query_sem);
    }
}

static const char *const NAMES_LEGACY[] = {"tsn_en", "tsn_lan"};
const nvs_flags_t tailnet_names_flags = {.record = "tsn_cfg", .legacy = NAMES_LEGACY, .count = 2};
static const char *const EXT_LEGACY[] = {"tsn_dns", "tsn_self"};
const nvs_flags_t tailnet_names_ext_flags = {.record = "tsn_ext", .legacy = EXT_LEGACY, .count = 2};

void tailnet_names_init(void)
{
    char *zone = nvs_param_get_str("tsn_zone");
    if (zone && strlen(zone) < sizeof s_saved_zone) strlcpy(s_saved_zone, zone, sizeof s_saved_zone);
    free(zone);
    uint8_t bits = nvs_flags_load(&tailnet_names_flags), ext = nvs_flags_load(&tailnet_names_ext_flags);
    s_enabled = bits & 1; s_lan = bits >> 1 & 1;
    s_dnscfg = ext & 1; s_self = ext >> 1 & 1;
    if (s_enabled || s_self) apply();
}

void tailnet_names_uplink(uint32_t ip_nbo)
{
    s_uplink = ip_nbo;
    dns_relay_set_lan(s_enabled && s_lan, ip_nbo);
}

void tailnet_names_get(bool *enabled, bool *lan) {*enabled = s_enabled; *lan = s_lan;}
void tailnet_names_get_ext(bool *dns_config, bool *self_resolve) {*dns_config = s_dnscfg; *self_resolve = s_self;}

esp_err_t tailnet_names_set(bool enabled, bool lan)
{
    esp_err_t err = nvs_flags_save(&tailnet_names_flags, (uint8_t)(enabled | lan << 1));   /* all or nothing */
    if (err) return err;
    s_enabled = enabled; s_lan = lan;
    apply();
    return ESP_OK;
}

esp_err_t tailnet_names_set_ext(bool dns_config, bool self_resolve)
{
    esp_err_t err = nvs_flags_save(&tailnet_names_ext_flags, (uint8_t)(dns_config | self_resolve << 1));
    if (err) return err;
    s_dnscfg = dns_config; s_self = self_resolve;
    apply();
    return ESP_OK;
}

/* One A lookup at a split-DNS route's resolver, in the caller's task: two
 * tries of 1.5 s, only answers from that server to this query count.
 * 1 found, 0 no such name, -1 no verdict. */
static int ask_resolver(uint32_t server, const char *name, uint32_t *ip)
{
    if (!s_query_sem || xSemaphoreTake(s_query_sem, pdMS_TO_TICKS(3000)) != pdTRUE) return -1;
    int result = -1, s = -1;
    uint8_t *buf = heap_caps_malloc(1024, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    int qlen = buf ? tailnet_names_query(name, (uint16_t)esp_random(), buf, 512) : 0;
    if (qlen) s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (s >= 0) {
        struct timeval to = {.tv_sec = 1, .tv_usec = 500000};
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &to, sizeof to);
        struct sockaddr_in to_addr = {.sin_family = AF_INET, .sin_port = htons(53), .sin_addr.s_addr = server};
        for (int attempt = 0; attempt < 2 && result < 0; attempt++) {
            if (sendto(s, buf, qlen, 0, (struct sockaddr *)&to_addr, sizeof to_addr) < 0) break;
            for (int stray = 0; stray < 4; stray++) {
                struct sockaddr_in from = {0};
                socklen_t fl = sizeof from;
                int n = recvfrom(s, buf + 512, 512, 0, (struct sockaddr *)&from, &fl);
                if (n <= 0) break;                              /* timeout: next attempt */
                if (from.sin_addr.s_addr != server || from.sin_port != htons(53)) continue;
                int r = tailnet_names_parse_a(buf + 512, n, buf, qlen, ip);
                if (r >= 0) {result = r; break;}
            }
        }
        close(s);
    }
    heap_caps_free(buf);
    xSemaphoreGive(s_query_sem);
    return result;
}

/* lwIP: name lookups of the gateway itself (getaddrinfo/netconn) try the
 * tailnet first while switched on. Runs in the calling task, never in the
 * TCP/IP thread. Tailnet names and names under a split-DNS route never reach
 * the public resolver; everything else goes on as before. */
int lwip_hook_netconn_external_resolve(const char *name, ip_addr_t *addr, u8_t addrtype, err_t *err)
{
    if (!s_self || !name || !addr || !err) return 0;
    microlink_t *ml = tailscale_get_microlink();
    char n[TN_QNAME_MAX];
    size_t l = strlen(name);
    while (l && name[l - 1] == '.') l--;
    if (!l || l >= sizeof n) return 0;
    for (size_t i = 0; i < l; i++) n[i] = lower(name[i]);
    n[l] = 0;
    uint32_t ip = 0, server = 0;
    bool in_domain = false;
    bool found = ml && (extra_record(n, &ip) || tailnet_names_match(n, next_peer, ml, &ip, &in_domain));
    if (!found && !in_domain && ml && s_dnscfg) {
        int kind = ml_dns_route(n, &server);
        if (kind == ML_DNS_ROUTE_LOCAL) in_domain = true;
        else if (kind == ML_DNS_ROUTE_FWD) {
            if (addrtype == NETCONN_DNS_IPV6) {*err = ERR_VAL; return 1;}
            int r = ask_resolver(server, n, &ip);
            if (r < 0) {*err = ERR_TIMEOUT; return 1;}
            found = r;
            in_domain = true;
        }
    }
    if (found && addrtype != NETCONN_DNS_IPV6) {ip_addr_set_ip4_u32(addr, ip); *err = ERR_OK; return 1;}
    if (found || in_domain) {*err = ERR_VAL; return 1;}
    if (private_name(n)) {*err = ERR_TIMEOUT; return 1;}
    return 0;
}

static esp_err_t get_names(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    microlink_t *ml = tailscale_get_microlink();
    ml_dns_summary_t d;
    ml_dns_summary(&d);
    char out[512];
    snprintf(out, sizeof out, "{\"enabled\":%s,\"lan\":%s,\"dns_config\":%s,\"self_resolve\":%s,\"relay\":%s,\"lan_listening\":%s,\"peers\":%d,"
             "\"tailnet_dns\":{\"self\":\"%s\",\"present\":%s,\"magic_dns\":%s,\"resolvers\":%u,\"routes\":%u,\"domains\":%u,\"records\":%u,\"ignored\":%u}}",
             s_enabled ? "true" : "false", s_lan ? "true" : "false", s_dnscfg ? "true" : "false", s_self ? "true" : "false",
             dns_relay_is_enabled() ? "true" : "false", dns_relay_lan_listening() ? "true" : "false", ml ? microlink_get_peer_count(ml) : 0,
             d.self, d.present ? "true" : "false", d.magic_dns ? "true" : "false", d.resolvers, d.routes, d.domains, d.extra, d.ignored);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, out);
}

static esp_err_t post_names(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[160];
    int total = req->content_len, received = 0;
    if (total <= 0 || total >= (int)sizeof body) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid body size"); return ESP_FAIL;}
    while (received < total) {
        int n = httpd_req_recv(req, body + received, total - received);
        if (n <= 0) {httpd_resp_send_408(req); return ESP_FAIL;}
        received += n;
    }
    body[received] = 0;
    cJSON *root = json_guard_parse(body);
    const cJSON *en = cJSON_GetObjectItemCaseSensitive(root, "enabled"), *lan = cJSON_GetObjectItemCaseSensitive(root, "lan");
    const cJSON *cfg = cJSON_GetObjectItemCaseSensitive(root, "dns_config"), *self = cJSON_GetObjectItemCaseSensitive(root, "self_resolve");
    /* dns_config and self_resolve are optional (older pages send only the
     * first two); present, they must be booleans. */
    bool valid = cJSON_IsObject(root) && cJSON_IsBool(en) && cJSON_IsBool(lan) && (!cfg || cJSON_IsBool(cfg)) && (!self || cJSON_IsBool(self));
    bool next_en = cJSON_IsTrue(en), next_lan = cJSON_IsTrue(lan);
    bool next_cfg = cfg ? cJSON_IsTrue(cfg) : s_dnscfg, next_self = self ? cJSON_IsTrue(self) : s_self;
    cJSON_Delete(root);
    if (!valid) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "expected boolean enabled and lan"); return ESP_FAIL;}
    esp_err_t err = ESP_OK;
    if (next_cfg != s_dnscfg || next_self != s_self) err = tailnet_names_set_ext(next_cfg, next_self);
    if (!err) err = tailnet_names_set(next_en, next_lan);
    if (err) {httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, esp_err_to_name(err)); return ESP_FAIL;}
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_sendstr(req, "{\"ok\":true}");
}

esp_err_t tailnet_names_register_http(httpd_handle_t server)
{
    const httpd_uri_t routes[] = {
        {.uri = "/api/tailnet-names", .method = HTTP_GET, .handler = get_names},
        {.uri = "/api/tailnet-names", .method = HTTP_POST, .handler = post_names}};
    for (unsigned i = 0; i < sizeof routes / sizeof routes[0]; i++) {
        esp_err_t err = httpd_register_uri_handler(server, &routes[i]);
        if (err != ESP_OK) return err;
    }
    return ESP_OK;
}
#endif
