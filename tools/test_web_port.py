"""Exercise actual admin-port policy and the real HTTP save prefix.

NVS, forwarding tables and HTTP transport are deterministic adapters; cJSON
is real. No device access or setting changes. WEB_PORT_SANITIZE=1 enables CI
memory/undefined-behavior instrumentation.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
policy = (ROOT / 'main/web_port.c').read_text(encoding='utf-8')
policy = '\n'.join(line for line in policy.splitlines() if not line.startswith('#include'))
web = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
handler = 'static esp_err_t system_save_handler' + web.split('static esp_err_t system_save_handler', 1)[1].split('    /* Device-name update', 1)[0]
handler += '''
    cJSON_Delete(root);
    req->status = recorded_error == ESP_OK ? 200 : 500;
    return recorded_error;
}
'''

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cJSON.h"
#include "json_guard.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#define HTTPD_400_BAD_REQUEST 400
#define PORTMAP_PROTO_TCP 6
#define TAILNET_FORWARD_PROTO_TCP 6
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
static unsigned critical, transaction, writes;
static bool read_failed, write_failed, authenticated = true;
static uint16_t configured, ap_conflict, tn_conflict;
static esp_err_t recorded_error;
#define portENTER_CRITICAL(p) do { (void)p; assert(!critical); critical = 1; } while(0)
#define portEXIT_CRITICAL(p) do { (void)p; assert(critical); critical = 0; } while(0)
static void forwarding_config_lock(void) { assert(!critical && !transaction); transaction = 1; }
static void forwarding_config_unlock(void) { assert(!critical && transaction); transaction = 0; }
static esp_err_t nvs_param_get_u16(const char *key, uint16_t *value) {
    assert(!critical && !strcmp(key, "web_port"));
    if (read_failed) return ESP_FAIL;
    *value = configured; return ESP_OK;
}
static esp_err_t nvs_param_set_u16(const char *key, uint16_t value) {
    assert(transaction && !critical && !strcmp(key, "web_port")); ++writes;
    if (write_failed) return ESP_FAIL;
    configured = value; return ESP_OK;
}
static bool portmap_listen_conflicts(uint8_t proto, uint16_t port) {
    assert(transaction && !critical && proto == 6); return port == ap_conflict;
}
static bool tailnet_forward_listen_conflicts(uint8_t proto, uint16_t port) {
    assert(transaction && !critical && proto == 6); return port == tn_conflict;
}
static bool tailscale_exit_server_active(void) { return true; }
static uint16_t tailscale_peerapi_port(void) { return 41180; }
typedef struct { const char *body; unsigned status; } httpd_req_t;
static esp_err_t require_auth(httpd_req_t *req) {
    if (authenticated) return ESP_OK;
    req->status = 401; return ESP_FAIL;
}
static void nvs_save_errors_reset(void) { recorded_error = ESP_OK; }
static void nvs_save_record_err(const char *key, esp_err_t err) {
    assert(!strcmp(key, "web_port")); recorded_error = err;
}
static esp_err_t recv_body(httpd_req_t *req, char *buf, size_t size, void *unused) {
    assert(!unused); size_t length = strlen(req->body);
    if (length >= size) return ESP_FAIL;
    memcpy(buf, req->body, length + 1); return ESP_OK;
}
static void httpd_resp_send_err(httpd_req_t *req, unsigned code, const char *message) {
    assert(message); req->status = code;
}
static void httpd_resp_set_status(httpd_req_t *req, const char *text) {
    assert(!strcmp(text, "409 Conflict")); req->status = 409;
}
static esp_err_t httpd_resp_sendstr(httpd_req_t *req, const char *text) {
    assert(req->status == 409 && text); return ESP_OK;
}
'''

tests = r'''
int main(void) {
    bool changed = true;
    assert(web_ui_configured_port() == 80 && web_ui_port_reserved(80));
    read_failed = true; assert(web_ui_configured_port() == 80); read_failed = false;
    web_ui_set_active_port(80);
    assert(web_ui_save_port(8080, &changed) == ESP_OK && changed);
    assert(web_ui_port_reserved(80) && web_ui_port_reserved(8080) && !web_ui_port_reserved(0));
    assert(web_ui_save_port(8080, &changed) == ESP_OK && !changed);
    write_failed = true;
    assert(web_ui_save_port(9090, &changed) == ESP_FAIL && !changed);
    assert(configured == 8080 && !web_ui_port_reserved(9090)); write_failed = false;
    unsigned before = writes; ap_conflict = 2222; tn_conflict = 4444;
    assert(web_ui_save_port(2222, &changed) == ESP_ERR_INVALID_STATE && !changed);
    assert(web_ui_save_port(4444, &changed) == ESP_ERR_INVALID_STATE && !changed);
    assert(web_ui_save_port(41180, &changed) == ESP_ERR_INVALID_STATE && !changed);
    assert(web_ui_save_port(0, &changed) == ESP_ERR_INVALID_ARG && !changed && writes == before);
    httpd_req_t request = {.body = "{\"web_port\":2222}"};
    assert(system_save_handler(&request) == ESP_OK && request.status == 409 && writes == before);
    const char *bad[] = {"0", "-1", "65536", "1e99", "1e999", "1.5", "true", "\"80\"", "null"};
    char body[80];
    for (unsigned i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        snprintf(body, sizeof body, "{\"web_port\":%s}", bad[i]); request.body = body;
        assert(system_save_handler(&request) == ESP_FAIL && request.status == 400 && writes == before);
    }
    request.body = "{\"web_port\":65535}";
    assert(system_save_handler(&request) == ESP_OK && request.status == 200 && configured == 65535);
    assert(web_ui_port_reserved(80) && web_ui_port_reserved(65535) && !web_ui_port_reserved(8080));
    authenticated = false; before = writes;
    assert(system_save_handler(&request) == ESP_FAIL && request.status == 401 && writes == before);
    authenticated = true; write_failed = true; request.body = "{\"web_port\":9090}";
    assert(system_save_handler(&request) == ESP_FAIL && request.status == 500 && configured == 65535);
    web_ui_set_active_port(0); assert(!web_ui_port_reserved(80) && web_ui_port_reserved(65535));
    assert(!transaction && !critical);
    puts("PASS: actual live/next-boot Web UI reservations, transactional AP/Tailnet/PeerAPI conflicts, NVS failure, HTTP auth/type/range/fraction/large-number validation");
}
'''

with tempfile.TemporaryDirectory(prefix='web-port-') as directory:
    path = Path(directory)
    cjson = os.environ.get('CJSON_SOURCE')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('WEB_PORT_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined,float-cast-overflow', '-fno-omit-frame-pointer']
    if cjson:
        flags += ['-I', str(Path(cjson).parent)]
    else:
        flags += ['-I', '/usr/include/cjson']
    (path / 'test.c').write_text(fixture + policy + handler + tests, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    link = [cjson] if cjson else ['-lcjson']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), *link, '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

assert '"web_port.c"' in (ROOT / 'main/CMakeLists.txt').read_text(encoding='utf-8')
startup = web.split('void web_ui_init(void)', 1)[1]
assert startup.index('web_ui_set_active_port(conf.server_port)') < startup.index('httpd_start(&server')
assert 'web_ui_set_active_port(0)' in startup
