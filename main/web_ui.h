/* Single-page web UI server.
 *
 * Boots an esp_http_server on port 80 and serves the embedded SPA at /.
 * JSON API endpoints under /api and the auth gate land in follow-up commits.
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Start the HTTP server. Idempotent — subsequent calls are no-ops. */
void web_ui_init(void);

/* Persisted listener port (default 80); changes take effect after restart. */
uint16_t web_ui_configured_port(void);

/* Reserve the running listener as well as the next-boot configured port. */
bool web_ui_port_reserved(uint16_t port);
void web_ui_set_active_port(uint16_t port);

/* Transactional conflict check and save; changed is false on failure. */
esp_err_t web_ui_save_port(uint16_t port, bool *changed);

#ifdef __cplusplus
}
#endif
