"""First-boot setup survives a reboot in the middle of setup (host, actual code).

A real board running 2.0.1-rc.2 rebooted after the wizard's Wi-Fi test: the
tested network had been persisted by the Wi-Fi driver, wifi_init_sta()
migrated it into wifi_nets, and first_boot_init() then marked setup_done on
a device without an admin password. Compiles the actual first_boot_init(),
wifi_first_boot_storage() and wifi_init_sta() against a Wi-Fi driver fixture
that keeps a flash copy and a RAM copy of the STA configuration, as ESP-IDF
does, and boots it repeatedly. No radio, no device. FBREBOOT_SANITIZE=1 adds
ASan/UBSan.
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


main_c = (ROOT / 'main/main.c').read_text(encoding='utf-8')
fb_c = (ROOT / 'main/first_boot.c').read_text(encoding='utf-8')
core_c = (ROOT / 'main/first_boot_core.c').read_text(encoding='utf-8')
functions = '\n'.join([
    c_func(core_c, 'bool fb_should_activate(bool setup_done, bool password_set, int wifi_networks, bool has_auth_key)'),
    c_func(fb_c, 'void first_boot_init(void)'),
    c_func(fb_c, 'bool first_boot_active(void)'),
    c_func(main_c, 'static void wifi_first_boot_storage(void)'),
    c_func(main_c, 'esp_netif_t *wifi_init_sta(void)'),
])

fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERROR_CHECK(x) do { esp_err_t e_ = (x); assert(e_ == ESP_OK); } while (0)
#define ESP_LOGI(tag, ...) ((void)(tag))
#define ESP_LOGW(tag, ...) ((void)(tag))
static const char *TAG = "first_boot", *TAG_STA = "WiFi Sta";
#define EXAMPLE_ESP_WIFI_STA_SSID "otherapssid"
#define EXAMPLE_ESP_WIFI_STA_PASSWD "otherappassword"
typedef enum { WIFI_IF_STA, WIFI_IF_AP } wifi_interface_t;
typedef enum { WIFI_STORAGE_FLASH, WIFI_STORAGE_RAM } wifi_storage_t;
typedef struct { struct { uint8_t ssid[32]; uint8_t password[64]; } sta; } wifi_config_t;
typedef struct { char ssid[33]; char passwd[65]; uint8_t valid; } wifi_network_t;
typedef struct { int unused; } esp_netif_t;
typedef struct { int unused; } fb_ctx_t;
typedef struct { int unused; } fb_crypto_t;
typedef struct { int unused; } StaticSemaphore_t;
typedef void *SemaphoreHandle_t;

/* Our own NVS namespace. */
static bool nvs_setup_done, nvs_has_setup_done, nvs_password, nvs_has_key;
static wifi_network_t nvs_nets[1]; static int nvs_net_count;
/* Wi-Fi driver: flash copy survives reboots, RAM copy is what it uses. */
static wifi_config_t drv_flash, drv_ram; static wifi_storage_t drv_storage;
static int applied_network = -1;

static esp_err_t nvs_param_get_u8(const char *k, uint8_t *v) { assert(!strcmp(k, "setup_done")); if (!nvs_has_setup_done) return ESP_FAIL; *v = nvs_setup_done; return ESP_OK; }
static esp_err_t nvs_param_set_u8(const char *k, uint8_t v) { assert(!strcmp(k, "setup_done")); nvs_has_setup_done = true; nvs_setup_done = v; return ESP_OK; }
static char *nvs_param_get_str(const char *k) { if (!strcmp(k, "ts_authkey") && nvs_has_key) { char *s = malloc(8); strcpy(s, "tskey"); return s; } return NULL; }
static bool is_web_password_set(void) { return nvs_password; }
static int wifi_networks_count(void) { return nvs_net_count; }
static bool wifi_networks_get(int i, wifi_network_t *n) { if (i >= nvs_net_count) return false; *n = nvs_nets[i]; return true; }
static esp_err_t wifi_networks_set_all(const wifi_network_t *a, int n) { assert(n <= 1); nvs_net_count = n; if (n) nvs_nets[0] = a[0]; return ESP_OK; }
static esp_err_t esp_wifi_set_config(wifi_interface_t i, wifi_config_t *c) { assert(i == WIFI_IF_STA); drv_ram = *c; if (drv_storage == WIFI_STORAGE_FLASH) drv_flash = *c; return ESP_OK; }
static esp_err_t esp_wifi_get_config(wifi_interface_t i, wifi_config_t *c) { assert(i == WIFI_IF_STA); *c = drv_ram; return ESP_OK; }
static esp_err_t esp_wifi_set_storage(wifi_storage_t s) { drv_storage = s; return ESP_OK; }
static esp_netif_t sta_netif;
static esp_netif_t *esp_netif_create_default_wifi_sta(void) { return &sta_netif; }
static void esp_netif_set_hostname(esp_netif_t *n, const char *h) { (void)n; (void)h; }
static int s_net_current, s_net_retries;
static void wifi_apply_network(int idx) { applied_network = idx; }
static StaticSemaphore_t s_lock_storage; static SemaphoreHandle_t s_lock;
static SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *s) { return s; }
static fb_ctx_t s_ctx; static fb_crypto_t s_crypto;
static void fb_init(fb_ctx_t *c, const fb_crypto_t *k) { (void)c; (void)k; }
static bool s_active;
static size_t strlcpy(char *d, const char *s, size_t n) { size_t l = strlen(s); if (n) { size_t c = l < n - 1 ? l : n - 1; memcpy(d, s, c); d[c] = 0; } return l; }
'''

tests = r'''
/* Boot order of app_main(): network table, first_boot_init(), esp_wifi_init()
 * (loads the driver's flash copy, FLASH storage), set_mode, the first-boot
 * storage rule, then wifi_init_sta(). */
static void boot(void) {
    s_active = false; applied_network = -1;
    drv_ram = drv_flash; drv_storage = WIFI_STORAGE_FLASH;
    first_boot_init();
    wifi_first_boot_storage();
    (void)wifi_init_sta();
}
/* What wifi_setup_test_start() does through wifi_apply_entry(). */
static void wizard_wifi_test(const char *ssid, const char *pw) {
    wifi_config_t c; memset(&c, 0, sizeof c);
    strcpy((char *)c.sta.ssid, ssid); strcpy((char *)c.sta.password, pw);
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &c));
}
static void factory(void) {
    nvs_has_setup_done = nvs_setup_done = nvs_password = nvs_has_key = false; nvs_net_count = 0;
    memset(&drv_flash, 0, sizeof drv_flash);
}
int main(void) {
    /* Blank board: setup mode, STA idle, driver storage RAM-only. */
    factory(); boot();
    assert(first_boot_active() && drv_storage == WIFI_STORAGE_RAM && !drv_ram.sta.ssid[0] && applied_network < 0);

    /* Wi-Fi test, then power loss or crash before finishing (the regression). */
    wizard_wifi_test("HomeNet", "home-password");
    assert(!strcmp((char *)drv_ram.sta.ssid, "HomeNet") && !drv_flash.sta.ssid[0]);
    for (int reboot = 0; reboot < 3; reboot++) {
        boot();
        assert(first_boot_active());
        assert(nvs_net_count == 0 && !nvs_has_setup_done && !drv_flash.sta.ssid[0] && !drv_ram.sta.ssid[0]);
    }

    /* A network cached in the driver's flash by an older build (or by 2.0.0's
     * Wi-Fi test): purged, never migrated, setup stays open. */
    factory(); strcpy((char *)drv_flash.sta.ssid, "HomeNet"); strcpy((char *)drv_flash.sta.password, "home-password");
    boot();
    assert(first_boot_active() && nvs_net_count == 0 && !nvs_has_setup_done);
    assert(!drv_flash.sta.ssid[0] && !drv_flash.sta.password[0]);
    boot(); assert(first_boot_active());

    /* Configured device: normal mode, driver keeps FLASH storage, network applied. */
    factory(); nvs_password = true; nvs_has_setup_done = nvs_setup_done = true;
    nvs_net_count = 1; strcpy(nvs_nets[0].ssid, "HomeNet"); nvs_nets[0].valid = 1;
    boot();
    assert(!first_boot_active() && drv_storage == WIFI_STORAGE_FLASH && applied_network == 0);

    /* Installation upgraded from 1.x with a password and only a driver-cached
     * network: still migrated as before, and recorded as set up. */
    factory(); nvs_password = true; strcpy((char *)drv_flash.sta.ssid, "OldNet"); strcpy((char *)drv_flash.sta.password, "old-password");
    boot();
    assert(!first_boot_active() && nvs_has_setup_done && nvs_setup_done);
    assert(nvs_net_count == 1 && !strcmp(nvs_nets[0].ssid, "OldNet") && drv_storage == WIFI_STORAGE_FLASH);

    /* The shipped Kconfig placeholder is never migrated, in either mode. */
    factory(); nvs_password = true; strcpy((char *)drv_flash.sta.ssid, EXAMPLE_ESP_WIFI_STA_SSID); strcpy((char *)drv_flash.sta.password, EXAMPLE_ESP_WIFI_STA_PASSWD);
    boot(); assert(!first_boot_active() && nvs_net_count == 0);

    /* Finished setup (the wizard writes wifi_nets, password and setup_done):
     * the next boot is normal mode and keeps the network. */
    factory(); boot(); wizard_wifi_test("HomeNet", "home-password");
    nvs_password = true; nvs_has_setup_done = nvs_setup_done = true;
    nvs_net_count = 1; strcpy(nvs_nets[0].ssid, "HomeNet"); nvs_nets[0].valid = 1;
    boot();
    assert(!first_boot_active() && applied_network == 0 && drv_storage == WIFI_STORAGE_FLASH);
    puts("PASS: actual first-boot init + Wi-Fi driver storage: a reboot after the Wi-Fi test keeps setup open (no migrated network, no setup_done), stale driver networks are purged, configured and 1.x devices unchanged (host)");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='first-boot-reboot-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + functions + tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-Wno-unused-function']
    if os.environ.get('FBREBOOT_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
