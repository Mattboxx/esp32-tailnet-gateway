/* Local explicit service-rule transfer, not a credential backup. MIT. */
#pragma once
#include "esp_http_server.h"
esp_err_t service_transfer_register_http(httpd_handle_t server);
