"""Actual manifest builder: observed/unknown states, private-input exclusion, OOM."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'main/homelab_ops.c').read_text();src=src[src.index('static bool capability_add'):]
PROGRAM=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#define CONFIG_LWIP_IPV6 1
#define CHIP_FEATURE_WIFI_BGN 1
#define ESP_OK 0
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
typedef struct {const char *version;} esp_app_desc_t;
typedef struct {int features,model,cores;} esp_chip_info_t;
typedef struct {bool monitoring,guard;} ops_settings_t;
typedef struct {bool enabled,home_assistant_discovery;char uri[160],password[96];} mqtt_integration_config_t;
typedef struct {bool enabled;char token[160],topic[96];} ntfy_integration_config_t;
typedef struct {bool enabled;} fourvia6_status_t;
typedef struct {bool authority_ready;} ml_policy_status_t;
typedef struct {struct {uint32_t addr;} ip;} esp_netif_ip_info_t;
typedef int esp_netif_t;
static bool connected=true,broker=true,worker=true,healthy=true;
static unsigned psram=8388608,features=1;
static void *task=(void*)1;
static struct {int state;} job;
static int tailscale_enabled=1,tailscale_advertise_ap=1,tailscale_advertise_exit_node=1;
static char *tailscale_login_server="PRIVATE_CONTROL_URL",*tailscale_advertise_routes="PRIVATE_ROUTE";
static const esp_app_desc_t *esp_app_get_description(void){static esp_app_desc_t d={"fixture"};return &d;}
static void esp_chip_info(esp_chip_info_t *c){*c=(esp_chip_info_t){features,1,2};}
static size_t esp_psram_get_size(void){return psram;}
static int esp_flash_get_size(void *p,uint32_t *n){(void)p;*n=16777216;return 0;}
static void homelab_ops_settings(ops_settings_t *s){*s=(ops_settings_t){worker,true};}
static void mqtt_integration_get_config(mqtt_integration_config_t *c){*c=(mqtt_integration_config_t){.enabled=true,.home_assistant_discovery=true,.uri="PRIVATE_MQTT",.password="PRIVATE_PASS"};}
static void ntfy_integration_get_config(ntfy_integration_config_t *c){*c=(ntfy_integration_config_t){.enabled=true,.token="PRIVATE_TOKEN",.topic="PRIVATE_TOPIC"};}
static void fourvia6_get_status(fourvia6_status_t *v){v->enabled=true;}
static void ml_policy_get_status(ml_policy_status_t *p){p->authority_ready=false;}
static void tailnet_forward_totals(uint32_t *e,uint32_t *i,void *a,void *b){(void)a;(void)b;*e=2;*i=0;}
static int tailnet_forward_count(void){return 2;}
static bool active(int state){(void)state;return false;}
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *s){(void)s;static int n;return &n;}
static int esp_netif_get_ip_info(void *n,esp_netif_ip_info_t *ip){(void)n;ip->ip.addr=1;return 0;}
static bool tailscale_is_connected(void){return connected;}
static bool tailscale_exit_server_active(void){return false;}
static bool wifi_ap_runtime_enabled(void){return false;}
static bool dns_relay_is_enabled(void){return true;}
static bool dns_relay_is_healthy(void){return healthy;}
static int wol_count(void){return 2;}
static bool health_monitor_enabled(void){return true;}
static bool mqtt_integration_connected(void){return broker;}
static bool snmp_agent_is_enabled(void){return false;}
static bool snmp_agent_is_running(void){return false;}
static unsigned allocations,fail_at,live;
static void *allocate(size_t n){if(++allocations==fail_at)return NULL;void *p=malloc(n);if(p)live++;return p;}
static void release(void *p){if(p)live--;free(p);}
'''
TAIL=r'''
static cJSON *feature(cJSON *root,const char *id){cJSON *a=cJSON_GetObjectItem(root,"features");cJSON *f; cJSON_ArrayForEach(f,a)if(!strcmp(cJSON_GetObjectItem(f,"id")->valuestring,id))return f;assert(false);return NULL;}
int main(void){
    cJSON_Hooks hooks={allocate,release};cJSON_InitHooks(&hooks);
    cJSON *r=homelab_ops_capabilities();assert(r);unsigned total=allocations;
    assert(cJSON_GetArraySize(cJSON_GetObjectItem(r,"features"))==27);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(feature(r,"tailscale"),"active")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(r,"authority_ready")));
    assert(cJSON_IsNull(cJSON_GetObjectItem(feature(r,"direct"),"active")));
    assert(cJSON_IsNull(cJSON_GetObjectItem(feature(r,"subnet-routing"),"active")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"exit-node"),"active")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"lan-tailnet-forwarding"),"active")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"ethernet"),"compiled")));
    assert(cJSON_IsNull(cJSON_GetObjectItem(feature(r,"ethernet"),"hardware_supported")));
    char *s=cJSON_PrintUnformatted(r);assert(s&&!strstr(s,"PRIVATE_"));cJSON_free(s);cJSON_Delete(r);assert(!live);
    for(unsigned i=1;i<=total;i++){allocations=0;fail_at=i;r=homelab_ops_capabilities();assert(!r);assert(!live);}
    fail_at=0;psram=features=0;broker=healthy=connected=false;r=homelab_ops_capabilities();assert(r);
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"smart-recovery"),"hardware_supported")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"wifi-uplink"),"hardware_supported")));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(feature(r,"mqtt"),"active")));
    cJSON_Delete(r);assert(!live);cJSON_InitHooks(NULL);
    puts("PASS: actual 27-capability manifest, unknown/runtime distinctions, private input exclusion and every JSON-allocation failure (mock platform)");
}
'''
with tempfile.TemporaryDirectory(prefix='capabilities-') as folder:
    p=Path(folder);(p/'test.c').write_text(PROGRAM+src+TAIL);binary=p/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-Werror'];libs=[]
    cjson=os.environ.get('CJSON_SOURCE')
    if cjson:flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('CAP_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
