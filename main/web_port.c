/* Keep live and next-boot admin listeners separate from forwarding.
 * SPDX-License-Identifier: MIT */
#include "web_ui.h"
#include "nvs_params.h"
#include "forwarding_config.h"
#include "portmap.h"
#include "tailnet_forward.h"
#include "tailscale_config.h"
#include "freertos/FreeRTOS.h"

static uint16_t s_active_port;
static portMUX_TYPE s_port_lock = portMUX_INITIALIZER_UNLOCKED;

uint16_t web_ui_configured_port(void)
{
    uint16_t port = 80;
    if (nvs_param_get_u16("web_port", &port) != ESP_OK || !port) port = 80;
    return port;
}

bool web_ui_port_reserved(uint16_t port)
{
    portENTER_CRITICAL(&s_port_lock);
    uint16_t active = s_active_port;
    portEXIT_CRITICAL(&s_port_lock);
    return port && (port == active || port == web_ui_configured_port());
}

void web_ui_set_active_port(uint16_t port)
{
    forwarding_config_lock();
    portENTER_CRITICAL(&s_port_lock);
    s_active_port = port;
    portEXIT_CRITICAL(&s_port_lock);
    forwarding_config_unlock();
}

esp_err_t web_ui_save_port(uint16_t port, bool *changed)
{
    if (changed) *changed = false;
    if (!port) return ESP_ERR_INVALID_ARG;
    forwarding_config_lock();
    esp_err_t err = ESP_OK;
    if (portmap_listen_conflicts(PORTMAP_PROTO_TCP, port) ||
        tailnet_forward_listen_conflicts(TAILNET_FORWARD_PROTO_TCP, port) ||
        (tailscale_exit_server_active() && port == tailscale_peerapi_port())) {
        err = ESP_ERR_INVALID_STATE;
    } else {
        bool different = port != web_ui_configured_port();
        err = nvs_param_set_u16("web_port", port);
        if (changed && err == ESP_OK) *changed = different;
    }
    forwarding_config_unlock();
    return err;
}
