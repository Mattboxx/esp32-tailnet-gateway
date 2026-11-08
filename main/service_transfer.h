/* SPDX-License-Identifier: GPL-3.0-only
 * Copyright (C) 2026 Mattboxx. ESP32 Tailnet Gateway, Mattboxx Edition: see LICENSE
 * and LICENSE-EXCEPTION.md. */
/* Local explicit service-rule transfer, not a credential backup. MIT. */
#pragma once
#include "esp_http_server.h"
esp_err_t service_transfer_register_http(httpd_handle_t server);
