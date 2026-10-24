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
struct httpd_req;

#ifdef __cplusplus
extern "C" {
#endif

/* Start the HTTP server. Idempotent — subsequent calls are no-ops. */
void web_ui_init(void);
/* Shared session + browser write-origin gate for extension API handlers. */
esp_err_t web_ui_require_auth(struct httpd_req *req);
/* A password-backed session even when the ordinary UI gate is off: for
 * firmware and flash-layout changes. */
esp_err_t web_ui_require_password_session(struct httpd_req *req);

/* First-boot setup endpoints: true when the request came through the
 * device's own AP and passes the same-origin screening; otherwise an error
 * response has been sent. */
bool web_ui_setup_request_ok(struct httpd_req *req);

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
