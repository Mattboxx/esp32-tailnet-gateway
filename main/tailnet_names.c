/* Tailnet names for devices behind the gateway; see tailnet_names.h.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
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

int tailnet_names_answer(const uint8_t *q, int len, uint8_t *out, int cap, tn_peer_fn peer, void *ctx)
{
    if (!q || !out || !peer || len < 17 || len > 512 || cap < 64) return 0;
    /* A standard query with one question and no answers. */
    if ((q[2] & 0xF8) != 0 || q[4] != 0 || q[5] != 1 || q[6] || q[7] || q[8] || q[9]) return 0;
    char name[256];
    uint16_t type, cls;
    int end = read_question(q, len, name, sizeof name, &type, &cls);
    if (!end || cls != 1) return 0;
    bool bare = !strchr(name, '.');
    size_t name_len = strlen(name), dots = 0;
    for (const char *c = name; *c; c++) dots += *c == '.';
    if (!bare && dots < 2) return 0;                     /* MagicDNS names have at least two dots */
    bool found = false, in_domain = false;
    uint32_t ip = 0;
    char fqdn[TN_NAME_MAX];
    for (int i = 0; !found && i < 4096 && peer(ctx, i, fqdn, &ip); i++) {
        fqdn[TN_NAME_MAX - 1] = 0;
        for (char *c = fqdn; *c; c++) *c = lower(*c);
        size_t f = strlen(fqdn);
        while (f && fqdn[f - 1] == '.') fqdn[--f] = 0;
        const char *dot = strchr(fqdn, '.');
        if (!f || !ip) continue;
        size_t first = dot ? (size_t)(dot - fqdn) : f;
        if (!strcmp(name, fqdn) || (bare && name_len == first && !strncmp(name, fqdn, first))) {found = true; break;}
        /* The tailnet domain is whatever follows a peer's first label. */
        if (dot && name_len > f - first && !strcmp(name + name_len - (f - first), dot)) in_domain = true;
    }
    if (!found && !in_domain) return 0;                  /* not a tailnet name: forward */
    bool answer = found && (type == 1 || type == 255);   /* A or ANY; others: no data */
    int total = end + (answer ? 16 : 0);
    if (total > cap) return 0;
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
/* --- names core (end) --- */

#ifdef ESP_PLATFORM
#include "dns_relay.h"
#include "json_guard.h"
#include "nvs_params.h"
#include "tailscale_config.h"
#include "web_ui.h"
#include "microlink.h"
#include "esp_log.h"
#include "lwip/inet.h"
#include <stdio.h>

static bool s_enabled, s_lan;
static volatile uint32_t s_uplink;

static bool next_peer(void *ctx, int index, char fqdn[TN_NAME_MAX], uint32_t *ip)
{
    microlink_t *ml = ctx;
    if (index >= microlink_get_peer_count(ml)) return false;
    microlink_peer_info_t info = {0};
    if (microlink_get_peer_info(ml, index, &info) != ESP_OK) {fqdn[0] = 0; *ip = 0; return true;}
    memcpy(fqdn, info.hostname, TN_NAME_MAX);
    *ip = htonl(info.vpn_ip);
    return true;
}

static int resolve(const uint8_t *q, int len, uint8_t *out, int cap)
{
    microlink_t *ml = tailscale_get_microlink();
    return ml ? tailnet_names_answer(q, len, out, cap, next_peer, ml) : 0;
}

static void apply(void)
{
    dns_relay_set_local_resolver(s_enabled ? resolve : NULL);
    dns_relay_set_lan(s_enabled && s_lan, s_uplink);
}

void tailnet_names_init(void)
{
    uint8_t v = 0;
    s_enabled = nvs_param_get_u8("tsn_en", &v) == ESP_OK && v == 1;
    s_lan = nvs_param_get_u8("tsn_lan", &v) == ESP_OK && v == 1;
    if (s_enabled) apply();
}

void tailnet_names_uplink(uint32_t ip_nbo)
{
    s_uplink = ip_nbo;
    if (s_enabled && s_lan) dns_relay_set_lan(true, ip_nbo);
}

void tailnet_names_get(bool *enabled, bool *lan) {*enabled = s_enabled; *lan = s_lan;}

esp_err_t tailnet_names_set(bool enabled, bool lan)
{
    esp_err_t err = nvs_param_set_u8("tsn_en", enabled);
    if (!err) err = nvs_param_set_u8("tsn_lan", lan);
    if (err) return err;
    s_enabled = enabled; s_lan = lan;
    apply();
    return ESP_OK;
}

static esp_err_t get_names(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    microlink_t *ml = tailscale_get_microlink();
    char out[192];
    snprintf(out, sizeof out, "{\"enabled\":%s,\"lan\":%s,\"relay\":%s,\"lan_listening\":%s,\"peers\":%d}",
             s_enabled ? "true" : "false", s_lan ? "true" : "false", dns_relay_is_enabled() ? "true" : "false",
             dns_relay_lan_listening() ? "true" : "false", ml ? microlink_get_peer_count(ml) : 0);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, out);
}

static esp_err_t post_names(httpd_req_t *req)
{
    if (web_ui_require_auth(req) != ESP_OK) return ESP_FAIL;
    char body[96];
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
    bool valid = cJSON_IsObject(root) && cJSON_IsBool(en) && cJSON_IsBool(lan);
    bool next_en = cJSON_IsTrue(en), next_lan = cJSON_IsTrue(lan);
    cJSON_Delete(root);
    if (!valid) {httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "expected boolean enabled and lan"); return ESP_FAIL;}
    esp_err_t err = tailnet_names_set(next_en, next_lan);
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
