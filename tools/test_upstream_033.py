"""Actual-C regressions for v0.1.32/v0.1.33 ports. No device access."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
base = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "upstream_validation.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_NO_MEM 1
#define ESP_ERR_INVALID_STATE 2
#define ESP_ERR_TIMEOUT 3
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define pdTRUE 1
#define pdFALSE 0
#define pdMS_TO_TICKS(v) (v)
'''
wifi = (ROOT / 'main/wifi_power_save.c').read_text()
wifi = re.sub(r'^#include[^\n]*\n', '', wifi, flags=re.M)
fixture = r'''
typedef int StaticSemaphore_t;
typedef void *SemaphoreHandle_t;
typedef enum {WIFI_PS_NONE, WIFI_PS_MIN_MODEM} wifi_ps_type_t;
static bool lock_ok=true;
static uint8_t saved;
static wifi_ps_type_t mode;
static int save_error,get_error,set_error,save_calls;
static SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *p){return p;}
static int xSemaphoreTake(SemaphoreHandle_t p,int t){assert(p&&t==1000);return lock_ok;}
static void xSemaphoreGive(SemaphoreHandle_t p){assert(p);}
static int nvs_param_get_u8(const char *k,uint8_t *v){assert(!strcmp(k,"wifi_ps"));*v=saved;return 0;}
static int nvs_param_set_u8(const char *k,uint8_t v){assert(!strcmp(k,"wifi_ps"));save_calls++;if(save_error)return save_error;saved=v;return 0;}
static int esp_wifi_get_ps(wifi_ps_type_t *v){if(get_error)return get_error;*v=mode;return 0;}
static int esp_wifi_set_ps(wifi_ps_type_t v){if(set_error)return set_error;mode=v;return 0;}
'''
tests = r'''
int main(void){
 assert(!wifi_power_save_configured());assert(wifi_power_save_set(true)==ESP_ERR_INVALID_STATE);
 assert(wifi_power_save_init()==ESP_OK&&mode==WIFI_PS_NONE);
 assert(wifi_power_save_set(true)==ESP_OK&&saved==1&&mode==WIFI_PS_MIN_MODEM);
 bool active=false;assert(wifi_power_save_runtime(&active)&&active);assert(!wifi_power_save_runtime(NULL));
 assert(wifi_power_save_init()==ESP_OK&&mode==WIFI_PS_MIN_MODEM);
 save_error=77;assert(wifi_power_save_set(false)==77&&saved==1&&mode==WIFI_PS_MIN_MODEM);
 save_error=0;int previous=save_calls;set_error=88;
 assert(wifi_power_save_set(false)==88&&save_calls==previous&&saved==1);
 set_error=0;get_error=99;assert(wifi_power_save_set(false)==99&&save_calls==previous);
 assert(!wifi_power_save_runtime(&active));get_error=0;lock_ok=false;
 assert(wifi_power_save_set(false)==ESP_ERR_TIMEOUT&&save_calls==previous);lock_ok=true;
 assert(wifi_power_save_set(false)==ESP_OK&&!saved&&mode==WIFI_PS_NONE);
 const char *yes[]={"0.0.0.0/0"," \t0.0.0.0/0 \t","10.0.0.0/8\r\n0.0.0.0/0\r\n","\r\n\t0.0.0.0/0\n"};
 const char *no[]={NULL,"","0.0.0.0/01","10.0.0.0/0","::/0","x0.0.0.0/0","0.0.0.0/0junk","0.0.0.0/0,10.0.0.0/8"};
 for(unsigned i=0;i<sizeof yes/sizeof *yes;i++)assert(route_list_has_default_v4(yes[i]));
 for(unsigned i=0;i<sizeof no/sizeof *no;i++)assert(!route_list_has_default_v4(no[i]));
 puts("PASS: exact manual default-route matching, WiFi low-latency default, persistence, live apply, rollback and driver/lock failures");
}
'''
with tempfile.TemporaryDirectory(prefix='upstream-033-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(base + fixture + wifi + tests)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    if os.environ.get('UPSTREAM_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

wg = (ROOT / 'external/microlink/components/microlink/src/ml_wg_mgr.c').read_text()
assert 'ESP_LOGD(TAG, "WG UDP TX:' in wg and 'ESP_LOGD(TAG, "WG RX:' in wg
assert 'ESP_LOGI(TAG,\n            "[WG_SNAP] peer=' in wg
assert 'ESP_LOGI(TAG,\n        "[WG_SNAP_SUM]' in wg
coord = (ROOT / 'external/microlink/components/microlink/src/ml_coord.c').read_text()
assert 'ML_EVT_DERP_CONNECTED | ML_EVT_SHUTDOWN_REQUEST' in coord
assert 'if (derp_wb & ML_EVT_SHUTDOWN_REQUEST)' in coord
derp = (ROOT / 'external/microlink/components/microlink/src/ml_derp.c').read_text()
assert 'while (ml->derp_tx_queue && xQueueReceive(' in derp
manager = (ROOT / 'main/tailscale_manager.c').read_text()
assert 'route_list_has_default_v4(s_active_advertise_routes)' in manager
assert '!(selected_exit && route_list_has_default_v4(manual))' in manager
web = (ROOT / 'main/web_ui.c').read_text()
assert 'cJSON_IsString(routes) ? route_list_has_default_v4(routes->valuestring)' in web
print('PASS: logging, partial-init/shutdown guards, boot-frozen manual exit mode and client/server exclusion preserved')
