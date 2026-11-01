/* Web UI session admission: idle close instead of LRU purge (see web_idle.c).
 * SPDX-License-Identifier: MIT */
#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_http_server.h"

/* Sessions without traffic for this long are closed (keep-alive idle timeout). */
#define WEB_IDLE_CLOSE_MS 5000
/* Tracked sessions; at least the server's max_open_sockets. */
#define WEB_IDLE_SLOTS 8

/* httpd open_fn: tracks the session and wraps its send/recv to record activity. */
esp_err_t web_idle_open(httpd_handle_t hd, int fd);
/* Starts/stops the once-a-second sweep for the running server. */
void web_idle_start(httpd_handle_t hd);
void web_idle_stop(void);
/* Idle sessions closed since boot. */
uint32_t web_idle_closed(void);

/* Exposed for the host test. */
void web_idle_reset(void);
void web_idle_touch(int fd, int64_t now_us);
int web_idle_sweep_fds(httpd_handle_t hd, const int *fds, size_t n, int64_t now_us);
