"""Socket origin checks of the HTTP server with the address forms lwIP returns.

ESP-IDF's HTTP server listens on PF_INET6 when lwIP IPv6 is enabled, so IPv4
clients appear as IPv4-mapped IPv6 sockaddrs. v2.0.0 compared only AF_INET:
the setup-AP check refused every real request (first-boot setup impossible)
and the login guard keyed every client as 0.0.0.0. Compiles the actual
functions of main/web_ui.c and main/first_boot.c with socket fixtures.
No board or network access. ORIGIN_SANITIZE=1 enables ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def c_func(src, signature):
    body = signature + src.split(signature, 1)[1]
    depth, out = 0, []
    for ch in body:
        out.append(ch)
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return ''.join(out)
    raise AssertionError(signature)


web = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
fb = (ROOT / 'main/first_boot.c').read_text(encoding='utf-8')
functions = '\n'.join([
    c_func(web, 'static uint32_t request_peer_ipv4(httpd_req_t *req)'),
    c_func(web, 'static bool request_arrived_on_ap(httpd_req_t *req)'),
    c_func(fb, 'static uint32_t client_ip(httpd_req_t *req)'),
])

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define AF_INET 2
#define AF_INET6 10
#define ESP_OK 0
typedef unsigned socklen_t;
typedef struct { int unused; } httpd_req_t;
struct sockaddr_storage { uint16_t ss_family; uint8_t data[126]; };
struct sockaddr { uint16_t family; };
struct sockaddr_in { uint16_t sin_family,sin_port; struct { uint32_t s_addr; } sin_addr; };
struct sockaddr_in6 { uint16_t sin6_family,sin6_port; uint32_t flow; struct { uint8_t s6_addr[16]; } sin6_addr; };
static const uint8_t mapped_prefix[12]={0,0,0,0,0,0,0,0,0,0,255,255};
#define IN6_IS_ADDR_V4MAPPED(a) (!memcmp((a)->s6_addr,mapped_prefix,12))
#include "sockaddr_ipv4.h"
typedef struct { int unused; } esp_netif_t;
typedef struct { struct { uint32_t addr; } ip; } esp_netif_ip_info_t;
static struct sockaddr_storage local_address, remote_address;
static bool ap_running = true, no_ap_netif, sock_error, name_error;
static uint32_t ap_ip_nbo;
static esp_netif_t ap_netif;
static bool wifi_ap_runtime_enabled(void) { return ap_running; }
static int httpd_req_to_sockfd(httpd_req_t *r) { (void)r; return sock_error ? -1 : 7; }
static int getsockname(int f, struct sockaddr *a, socklen_t *n) { (void)f; assert(*n >= sizeof local_address); if (name_error) return -1; memcpy(a, &local_address, sizeof local_address); return 0; }
static int getpeername(int f, struct sockaddr *a, socklen_t *n) { (void)f; assert(*n >= sizeof remote_address); if (name_error) return -1; memcpy(a, &remote_address, sizeof remote_address); return 0; }
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *k) { assert(!strcmp(k, "WIFI_AP_DEF")); return no_ap_netif ? NULL : &ap_netif; }
static int esp_netif_get_ip_info(esp_netif_t *n, esp_netif_ip_info_t *i) { (void)n; i->ip.addr = ap_ip_nbo; return ESP_OK; }
static uint32_t nbo(int a, int b, int c, int d) { uint8_t x[4] = {(uint8_t)a, (uint8_t)b, (uint8_t)c, (uint8_t)d}; uint32_t v; memcpy(&v, x, 4); return v; }
static void v4(struct sockaddr_storage *s, uint32_t ip) { memset(s, 0, sizeof *s); struct sockaddr_in a = {.sin_family = AF_INET, .sin_addr = {ip}}; memcpy(s, &a, sizeof a); }
static void mapped(struct sockaddr_storage *s, uint32_t ip) { memset(s, 0, sizeof *s); struct sockaddr_in6 a = {.sin6_family = AF_INET6}; memcpy(a.sin6_addr.s6_addr, mapped_prefix, 12); memcpy(a.sin6_addr.s6_addr + 12, &ip, 4); memcpy(s, &a, sizeof a); }
static void native6(struct sockaddr_storage *s, uint8_t first) { memset(s, 0, sizeof *s); struct sockaddr_in6 a = {.sin6_family = AF_INET6}; a.sin6_addr.s6_addr[0] = first; a.sin6_addr.s6_addr[1] = first ? 0x80 : 0; a.sin6_addr.s6_addr[15] = 1; memcpy(s, &a, sizeof a); }
'''

tests = r'''
int main(void) {
    httpd_req_t req;
    const uint32_t ap = nbo(192, 168, 4, 1), sta = nbo(192, 168, 1, 50);
    const uint32_t phone = nbo(192, 168, 4, 2), laptop = nbo(192, 168, 4, 3);
    ap_ip_nbo = ap;
    /* Setup-AP origin: the dual-stack form real hardware returns (regression). */
    mapped(&local_address, ap); assert(request_arrived_on_ap(&req));
    v4(&local_address, ap); assert(request_arrived_on_ap(&req));
    /* Upstream LAN interface, any form: refused. */
    mapped(&local_address, sta); assert(!request_arrived_on_ap(&req));
    v4(&local_address, sta); assert(!request_arrived_on_ap(&req));
    /* Native IPv6 (link-local, global, ::1) and unknown families: refused. */
    native6(&local_address, 0xfe); assert(!request_arrived_on_ap(&req));
    native6(&local_address, 0x20); assert(!request_arrived_on_ap(&req));
    native6(&local_address, 0); assert(!request_arrived_on_ap(&req));
    memset(&local_address, 0, sizeof local_address); local_address.ss_family = 1; assert(!request_arrived_on_ap(&req));
    /* An address that only matches the last 4 bytes but lacks the mapped prefix. */
    mapped(&local_address, ap); ((struct sockaddr_in6 *)&local_address)->sin6_addr.s6_addr[10] = 0; assert(!request_arrived_on_ap(&req));
    /* AP off, no AP netif, AP without address, socket/name errors: fail closed. */
    mapped(&local_address, ap);
    ap_running = false; assert(!request_arrived_on_ap(&req)); ap_running = true;
    no_ap_netif = true; assert(!request_arrived_on_ap(&req)); no_ap_netif = false;
    ap_ip_nbo = 0; mapped(&local_address, 0); assert(!request_arrived_on_ap(&req)); ap_ip_nbo = ap; mapped(&local_address, ap);
    sock_error = true; assert(!request_arrived_on_ap(&req)); sock_error = false;
    name_error = true; assert(!request_arrived_on_ap(&req)); name_error = false;
    assert(request_arrived_on_ap(&req));

    /* Peer identity for the login guard and the pairing owner: distinct clients
     * stay distinct (v2.0.0 collapsed them all to 0). */
    mapped(&remote_address, phone); assert(request_peer_ipv4(&req) == phone && client_ip(&req) == phone);
    mapped(&remote_address, laptop); assert(request_peer_ipv4(&req) == laptop && client_ip(&req) == laptop);
    v4(&remote_address, phone); assert(request_peer_ipv4(&req) == phone && client_ip(&req) == phone);
    native6(&remote_address, 0xfe); assert(request_peer_ipv4(&req) == 0 && client_ip(&req) == 0);
    sock_error = true; assert(request_peer_ipv4(&req) == 0 && client_ip(&req) == 0); sock_error = false;
    name_error = true; assert(request_peer_ipv4(&req) == 0 && client_ip(&req) == 0); name_error = false;
    puts("PASS: actual setup-AP origin, login-guard peer and pairing client checks accept IPv4/IPv4-mapped, refuse LAN, native IPv6, malformed and error cases");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='socket-origin-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + functions + tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    if os.environ.get('ORIGIN_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
