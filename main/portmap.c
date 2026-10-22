/* See portmap.h for the rationale.
 *
 * SPDX-License-Identifier: MIT
 */
#include <string.h>
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs.h"
#include "lwip/lwip_napt.h"
#include "lwip/tcpip.h"
#include "nvs_params.h"
#include "portmap.h"
#include "tailnet_forward.h"
#include "forwarding_config.h"
#include "web_ui.h"
#include "tailscale_config.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "portmap";

#define NVS_KEY "portmap"

static portmap_entry_t s_table[PORTMAP_MAX];
static int             s_count  = 0;
static bool            s_loaded = false;
/* Publish/copy the saved AP table under a
 * short cross-core lock; never hold this lock across NVS, lwIP or Tailnet. */
static portMUX_TYPE s_table_lock = portMUX_INITIALIZER_UNLOCKED;
typedef struct { uint8_t proto; uint16_t port; } installed_t;
static installed_t s_installed[PORTMAP_MAX + TAILNET_FORWARD_MAX];
static int s_installed_count;
static bool entry_is_filled(const portmap_entry_t *entry);

static bool cache_loaded(void)
{
    portENTER_CRITICAL(&s_table_lock);
    bool loaded = s_loaded;
    portEXIT_CRITICAL(&s_table_lock);
    return loaded;
}

static void publish_table(const portmap_entry_t *table, int count)
{
    portENTER_CRITICAL(&s_table_lock);
    memcpy(s_table, table, sizeof s_table);
    s_count = count;
    s_loaded = true;
    portEXIT_CRITICAL(&s_table_lock);
}

void portmap_init(void)
{
    if (cache_loaded()) return;
    portmap_entry_t table[PORTMAP_MAX] = {0};
    int count = 0;

    nvs_handle_t nvs;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs) == ESP_OK) {
        size_t expected = sizeof s_table;
        size_t actual   = expected;
        if (nvs_get_blob(nvs, NVS_KEY, table, &actual) == ESP_OK
            && actual == expected) {
            bool consistent = true;
            for (int i = 0; i < PORTMAP_MAX; i++) {
                if (!table[i].valid) continue;
                if (table[i].valid != 1 || !entry_is_filled(&table[i]) ||
                    !memchr(table[i].name, 0, sizeof table[i].name)) {
                    consistent = false;
                    break;
                }
                for (int j = 0; j < count; j++) {
                    if (table[j].proto == table[i].proto && table[j].ext_port == table[i].ext_port) {
                        consistent = false;
                        break;
                    }
                }
                if (!consistent) break;
                /* Compact in place; getters/UI iterate 0..count, not all slots. */
                table[count++] = table[i];
            }
            if (!consistent) {
                count = 0;
                ESP_LOGE(TAG, "Invalid stored AP forwarding rules; ignoring the whole table");
            }
            memset(table + count, 0, sizeof table - count * sizeof table[0]);
            ESP_LOGI(TAG, "loaded %d portmap(s) from NVS", count);
        } else {
            memset(table, 0, sizeof table);
        }
        nvs_close(nvs);
    }

    publish_table(table, count);
}

int portmap_count(void)
{
    if (!cache_loaded()) portmap_init();
    portENTER_CRITICAL(&s_table_lock);
    int count = s_count;
    portEXIT_CRITICAL(&s_table_lock);
    return count;
}

bool portmap_get(int i, portmap_entry_t *out)
{
    if (!cache_loaded()) portmap_init();
    if (!out || i < 0 || i >= PORTMAP_MAX) return false;
    portENTER_CRITICAL(&s_table_lock);
    bool valid = s_table[i].valid;
    if (valid) memcpy(out, &s_table[i], sizeof *out);
    portEXIT_CRITICAL(&s_table_lock);
    return valid;
}

static bool entry_is_filled(const portmap_entry_t *e)
{
    if (!e->ext_port || !e->int_port || !e->int_ip) return false;
    if (e->proto != PORTMAP_PROTO_TCP && e->proto != PORTMAP_PROTO_UDP) return false;
    return true;
}

bool portmap_listen_conflicts(uint8_t proto, uint16_t port)
{
    bool conflict = false;
    portENTER_CRITICAL(&s_table_lock);
    for (int i = 0; i < PORTMAP_MAX; i++)
        if (s_table[i].valid && s_table[i].proto == proto && s_table[i].ext_port == port) { conflict = true; break; }
    portEXIT_CRITICAL(&s_table_lock);
    return conflict;
}

static esp_err_t set_all_locked(const portmap_entry_t *arr, int count)
{
    if (!arr) return ESP_ERR_INVALID_ARG;
    if (count < 0 || count > PORTMAP_MAX) return ESP_ERR_INVALID_ARG;

    for (int i = 0; i < count; i++) {
        if(!entry_is_filled(&arr[i])){
            if(!arr[i].valid&&!arr[i].proto&&!arr[i].ext_port&&!arr[i].int_port&&!arr[i].int_ip&&!arr[i].name[0])continue;
            return ESP_ERR_INVALID_ARG;
        }
        /* Native callers historically omit valid; persistence normalizes it.
         * Filled rows MUST still receive every conflict/name check. */
        if(arr[i].valid>1)return ESP_ERR_INVALID_ARG;
        if (!memchr(arr[i].name, 0, sizeof arr[i].name)) return ESP_ERR_INVALID_ARG;
        if (tailnet_forward_listen_conflicts(arr[i].proto, arr[i].ext_port)) return ESP_ERR_INVALID_STATE;
        if (arr[i].proto == PORTMAP_PROTO_TCP && web_ui_port_reserved(arr[i].ext_port)) return ESP_ERR_INVALID_STATE;
        if (arr[i].proto == PORTMAP_PROTO_TCP && tailscale_exit_server_active()
            && arr[i].ext_port == tailscale_peerapi_port()) return ESP_ERR_INVALID_STATE;
        for (int j = 0; j < i; j++)
            if (entry_is_filled(&arr[j]) && arr[j].proto == arr[i].proto && arr[j].ext_port == arr[i].ext_port)
                return ESP_ERR_INVALID_STATE;
    }
    portmap_entry_t candidate[PORTMAP_MAX] = {0};
    int candidate_count = 0;
    for (int i = 0; i < count; i++) {
        if (!entry_is_filled(&arr[i])) continue;
        memcpy(&candidate[candidate_count], &arr[i], sizeof candidate[0]);
        candidate[candidate_count].valid = 1;
        candidate_count++;
    }

    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (err != ESP_OK) return err;
    err = nvs_set_blob(nvs, NVS_KEY, candidate, sizeof candidate);
    if (err == ESP_OK) err = nvs_commit(nvs);
    nvs_close(nvs);

    if (err == ESP_OK) {
        /* Do not expose or install the new policy until it is durable.
         * A failed save must leave the old cache and bindings unchanged,
         * including on a later DHCP-triggered refresh. */
        publish_table(candidate, candidate_count);
        ESP_LOGI(TAG, "saved %d portmap(s) to NVS", candidate_count);
    } else {
        ESP_LOGE(TAG, "save failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t portmap_set_all(const portmap_entry_t *arr, int count)
{
    /* Conflict validation, persistence and publication are one transaction
     * across both tables, not just independently locked memory copies. */
    forwarding_config_lock();
    esp_err_t err = set_all_locked(arr, count);
    forwarding_config_unlock();
    if (err == ESP_OK) portmap_install_all();
    return err;
}

static void portmap_install_cb(void *arg)
{
    (void)arg;
    if (!cache_loaded()) portmap_init();
    portmap_entry_t table[PORTMAP_MAX];
    tailnet_forward_mapping_t mappings[TAILNET_FORWARD_MAX];
    /* Do not combine an AP table from before a save with a Tailnet table
     * from after it. Release before any lwIP mutation or install reporting. */
    forwarding_config_lock();
    portENTER_CRITICAL(&s_table_lock);
    memcpy(table, s_table, sizeof table);
    portEXIT_CRITICAL(&s_table_lock);
    int mapping_count=tailnet_forward_snapshot_mappings(mappings,TAILNET_FORWARD_MAX);
    forwarding_config_unlock();

    /* Remove stale bindings even when the uplink has lost its address.
     * Tailnet runtime status must not report these mappings as installed. */
    for (int i = 0; i < s_installed_count; i++)
        ip_portmap_remove(s_installed[i].proto, s_installed[i].port);
    s_installed_count = 0;
    tailnet_forward_prepare_install();

    /* Pull the current STA IP — without it the NAPT bind has nothing to
     * tie the external side to. Skip silently when STA isn't up yet;
     * we'll be called again from IP_GOT_IP. */
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t ip_info = {0};
    if (!sta || esp_netif_get_ip_info(sta, &ip_info) != ESP_OK || !ip_info.ip.addr) {
        ESP_LOGI(TAG, "STA has no IP yet; deferring portmap install");
        return;
    }
    uint32_t bind_ip = ip_info.ip.addr;

    int ap_installed = 0, tailnet_installed = 0;
    for (int i = 0; i < PORTMAP_MAX; i++) {
        if (!table[i].valid) continue;
        if (table[i].proto == PORTMAP_PROTO_TCP && web_ui_port_reserved(table[i].ext_port)) continue;
        if (ip_portmap_add(table[i].proto, bind_ip, table[i].ext_port,
                           table[i].int_ip, table[i].int_port)) {
            s_installed[s_installed_count++] = (installed_t){table[i].proto, table[i].ext_port};
            ap_installed++;
        }
    }
    for (int i = 0; i < mapping_count; i++) {
        tailnet_forward_mapping_t *m=&mappings[i];
        m->binding_ip_nbo=bind_ip;
        if (m->rule.proto == TAILNET_FORWARD_PROTO_TCP && web_ui_port_reserved(m->rule.listen_port)) {
            tailnet_forward_mark_installed(m, false, "Web UI listener conflict");
            continue;
        }
        bool ok = ip_portmap_add(m->rule.proto, bind_ip, m->rule.listen_port, m->destination_nbo, m->rule.destination_port);
        if (ok) {
            s_installed[s_installed_count++] = (installed_t){m->rule.proto, m->rule.listen_port};
            tailnet_installed++;
        }
        tailnet_forward_mark_installed(m, ok, ok ? NULL : "lwIP port-map table full");
    }
    ESP_LOGI(TAG, "installed %d AP-side + %d LAN-to-Tailnet mapping(s) on STA " IPSTR,
             ap_installed, tailnet_installed, IP2STR(&ip_info.ip));
}

void portmap_install_all(void)
{
    /* ip_portmap_* mutates lwIP-global tables. Serialize it on tcpip_thread
     * instead of racing packet input from the HTTP/event/manager tasks. */
    err_t err = tcpip_callback_with_block(portmap_install_cb, NULL, 1);
    if (err != ERR_OK) ESP_LOGE(TAG, "portmap refresh scheduling failed: %d", err);
}
