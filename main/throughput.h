/* Throughput test (Diagnostics), only on request.
 *
 * Gateway download: the gateway fetches a URL (HTTP or verified HTTPS) for
 * up to THR_MAX_S seconds or THR_MAX_BYTES and discards the data, measuring
 * its own uplink or tailnet throughput (a file on a NAS over the tailnet,
 * or a public speed-test URL). Browser download: the browser fetches up to
 * THR_BLOB_MAX zero bytes from the gateway, measuring the link to it.
 *
 * Nothing runs between tests: the download worker (PSRAM stack) exists only
 * while a test runs; one test at a time; it stops early when internal
 * memory gets low. Results are local and never sent anywhere.
 *
 * Original implementation, Mattboxx Edition. MIT. */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#define THR_MAX_S 30
#define THR_MAX_BYTES (512u * 1024u * 1024u)
#define THR_BLOB_MAX (16u * 1024u * 1024u)

/* Core (pure, host-tested). */
bool throughput_url_valid(const char *url, char *why, size_t cap);
/* kbit/s, rounded; 0 when nothing was measured. */
uint32_t throughput_kbps(uint64_t bytes, uint64_t elapsed_us);
/* Why a running download stops (NULL = keep going). */
const char *throughput_stop(uint64_t bytes, uint64_t elapsed_us, uint32_t seconds, size_t internal_free);

/* Firmware. */
#include "esp_http_server.h"
esp_err_t throughput_register_http(httpd_handle_t server);
