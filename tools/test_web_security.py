"""Actual administration request screening, host trust and login budget.

Compiles the real browser_request_refused() from main/web_ui.c against a
header-table HTTP fixture, the real web_origin.h/login_budget.h helpers and
the existing control/DHCP validation assertions. No device or HTTP server.
Set WEB_SANITIZE=1 on Linux to add ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
start = '/* Browser-request screening'
screening = start + source.split(start, 1)[1].split('static esp_err_t require_auth(httpd_req_t *req)', 1)[0]
console = (ROOT / 'components/remote_console/remote_console.c').read_text(encoding='utf-8')
tunnel = 'static bool rc_tunnel_destination' + console.split('static bool rc_tunnel_destination', 1)[1].split('static uint32_t netif_ip_by_key', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "web_origin.h"
#include "login_budget.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
enum {HTTP_GET=1, HTTP_POST=3};
typedef enum {HTTPD_400_BAD_REQUEST=400, HTTPD_403_FORBIDDEN=403} httpd_err_code_t;
typedef struct {int method; const char *hdr[4][2];} httpd_req_t;
static int last_error;
static const char *find(httpd_req_t *r, const char *name) {
    for (int i = 0; i < 4; i++) if (r->hdr[i][0] && !strcmp(r->hdr[i][0], name)) return r->hdr[i][1];
    return NULL;
}
static size_t httpd_req_get_hdr_value_len(httpd_req_t *r, const char *name) {
    const char *v = find(r, name); return v ? strlen(v) : 0;
}
static esp_err_t httpd_req_get_hdr_value_str(httpd_req_t *r, const char *name, char *out, size_t cap) {
    const char *v = find(r, name);
    if (!v) return 0x105;
    if (strlen(v) >= cap) {snprintf(out, cap, "%s", v); return 0x10b;}
    strcpy(out, v); return ESP_OK;
}
static esp_err_t httpd_resp_send_err(httpd_req_t *r, httpd_err_code_t code, const char *msg) {
    (void)r; (void)msg; last_error = code; return ESP_OK;
}
''' + screening + tunnel + r'''
static bool refused(int method, bool open, const char *host, const char *origin, const char *site) {
    httpd_req_t r = {.method = method}; int n = 0;
    if (host) {r.hdr[n][0] = "Host"; r.hdr[n++][1] = host;}
    if (origin) {r.hdr[n][0] = "Origin"; r.hdr[n++][1] = origin;}
    if (site) {r.hdr[n][0] = "Sec-Fetch-Site"; r.hdr[n++][1] = site;}
    last_error = 0;
    bool result = browser_request_refused(&r, open);
    assert(result == (last_error != 0));
    return result;
}
int main(void) {
    const char *trusted[] = {"192.168.4.1", "100.64.0.7:8080", "[fd7a:115c:a1e0::1]", "[::1]:80",
        "gateway", "gateway.local", "GATEWAY.LOCAL.", "router.lan", "nas.home.arpa", "x.internal",
        "esp.localdomain", "esp.tail1234.ts.net", "dev.localhost", "esp_router.home"};
    const char *untrusted[] = {"", "evil.example", "gateway.local.evil.example", "192.168.4.1.nip.io",
        "999.1.1.1", "01.2.3.4", "1.2.3", "gateway..local", ".local", "x.ts.net.evil",
        "[]", "[::1", "[::1]x", "[g::1]", "[1.2.3.4]", "host:0", "host:65536", "host:", "host:12a",
        "a b.local", "evil.example:80"};
    for (unsigned i = 0; i < sizeof trusted / sizeof *trusted; i++) assert(web_host_trusted(trusted[i]));
    for (unsigned i = 0; i < sizeof untrusted / sizeof *untrusted; i++) assert(!web_host_trusted(untrusted[i]));
    assert(!web_host_trusted(NULL));
    char longest[300]; memset(longest, 'a', sizeof longest - 1); longest[sizeof longest - 1] = 0;
    assert(!web_host_trusted(longest)); /* single label but over DNS length */
    assert(web_origin_matches("192.0.2.1:8080","http://192.0.2.1:8080"));
    assert(!web_origin_matches("router.example","https://router.example@evil"));

    /* Password configured: reads unaffected, writes need same origin. */
    assert(!refused(HTTP_GET, false, "evil.example", NULL, "cross-site"));
    assert(!refused(HTTP_POST, false, "evil.example", "http://evil.example", NULL)); /* cookie still required */
    assert(refused(HTTP_POST, false, "192.168.1.5", "http://evil.example", NULL) && last_error == 403);
    assert(refused(HTTP_POST, false, "192.168.1.5", NULL, "cross-site"));
    assert(refused(HTTP_POST, false, NULL, "http://192.168.1.5", NULL)); /* Origin without Host */
    assert(!refused(HTTP_POST, false, NULL, NULL, NULL)); /* native client */
    assert(!refused(HTTP_POST, false, "192.168.1.5", "http://192.168.1.5", "same-origin"));
    /* No password / initial setup: DNS rebinding and cross-site reads refused. */
    assert(refused(HTTP_GET, true, "evil.example", NULL, NULL) && last_error == 403);
    assert(refused(HTTP_POST, true, "evil.example", "http://evil.example", "same-origin"));
    assert(refused(HTTP_GET, true, "192.168.4.1", NULL, "cross-site"));
    assert(!refused(HTTP_GET, true, "192.168.4.1", NULL, "none"));
    assert(!refused(HTTP_POST, true, "gateway.local", "http://gateway.local", "same-origin"));
    assert(!refused(HTTP_GET, true, NULL, NULL, NULL));
    char big[400]; memset(big, 'h', sizeof big - 1); big[sizeof big - 1] = 0;
    assert(refused(HTTP_GET, false, big, NULL, NULL) && last_error == 400);
    char origin[300] = "http://"; memset(origin + 7, 'o', 280); origin[287] = 0;
    assert(refused(HTTP_POST, false, "o", origin, NULL));

    login_budget_t b = {0}; uint64_t t = 5000000;
    for (unsigned i = 0; i < LOGIN_BUDGET_BURST; i++) {assert(!login_budget_wait_us(&b, t)); login_budget_failed(&b, t);}
    assert(login_budget_wait_us(&b, t) == LOGIN_BUDGET_REFILL_US);
    assert(login_budget_wait_us(&b, t + LOGIN_BUDGET_REFILL_US - 1) == 1);
    assert(!login_budget_wait_us(&b, t + LOGIN_BUDGET_REFILL_US));
    login_budget_failed(&b, t + LOGIN_BUDGET_REFILL_US);
    assert(login_budget_wait_us(&b, t + LOGIN_BUDGET_REFILL_US) == LOGIN_BUDGET_REFILL_US);
    for (unsigned i = 0; i < 100; i++) login_budget_failed(&b, t + LOGIN_BUDGET_REFILL_US);
    assert(b.used == LOGIN_BUDGET_BURST); /* saturates, no overflow or growing lockout */
    assert(!login_budget_wait_us(&b, t + 12 * LOGIN_BUDGET_REFILL_US) && b.used == 0);
    login_budget_t c = {.used = LOGIN_BUDGET_BURST, .since_us = 9000000};
    assert(login_budget_wait_us(&c, 1000) == LOGIN_BUDGET_REFILL_US); /* clock regression rebases */
    login_budget_t d = {.used = 3, .since_us = 0};
    assert(!login_budget_wait_us(&d, UINT64_MAX / 2) && d.used == 0);
    /* Remote console VPN binding: tunnel address only, not a CGNAT-looking LAN. */
    assert(rc_tunnel_destination(0x64400005u,false));
    assert(!rc_tunnel_destination(0x64500005u,true)); /* STA on a CGNAT LAN (LTE/Starlink) */
    assert(!rc_tunnel_destination(0xc0a80105u,false)&&!rc_tunnel_destination(0x647fffffu+1u,false));
    assert(rc_tunnel_destination(0x647fffffu,false)&&!rc_tunnel_destination(0x643fffffu,false));
    puts("PASS: actual request screening (CSRF/cross-site/DNS rebinding, header limits), host trust, login budget saturation/refill/clock, console tunnel-address binding");
}
'''

with tempfile.TemporaryDirectory(prefix='web-security-') as folder:
    path = Path(folder)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(ROOT / 'main'),
             '-I', str(ROOT / 'components/web_password/include')]
    if os.environ.get('WEB_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    (path / 'screen.c').write_text(PROGRAM, encoding='utf-8')
    for stem, src in (('screen', path / 'screen.c'), ('control', ROOT / 'tools/test_control_validation.c')):
        binary = path / (stem + ('.exe' if os.name == 'nt' else ''))
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(src), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
