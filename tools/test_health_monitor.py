"""Actual health validation/observation/persistence functions with NVS sinks.
No live DNS/TCP, SDK/FreeRTOS concurrency, interface or hardware claim.
"""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/health_monitor.c').read_text(encoding='utf-8')
header=(ROOT/'main/health_monitor.h').read_text(encoding='utf-8')
def function(signature):
    at=source.index(signature);return source[at:source.index('\n}',at)+2]+'\n'
types=header[header.index('typedef struct'):header.index('void health_monitor_init')]
types+=source[source.index('#define HEALTH_MAGIC'):source.index('static SemaphoreHandle_t health_lock;')]
fixture=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#endif
#define HLOCK() ((void)0)
#define HUNLOCK() ((void)0)
#define ESP_OK 0
#define ESP_ERR_INVALID_ARG -2
#define NVS_NAMESPACE "fixture"
#define NVS_READWRITE 1
typedef int esp_err_t,nvs_handle_t;
static bool worker_fail;
static unsigned fault,stage;
static uint64_t health_next;
static uint32_t health_generation;
static unsigned health_cursor,probe_calls,notifications,publishes;
static uint64_t fixture_now=1000;
static bool admit=true,race_generation;
static int probe_result=1;
static uint64_t health_now(void){return fixture_now;}
typedef struct {struct {uint32_t addr;} ip;} esp_netif_ip_info_t;
typedef int wifi_ap_record_t;
typedef struct {bool authority_ready;} ml_policy_status_t;
static bool health_uplink(esp_netif_ip_info_t *info){(void)info;return true;}
static int esp_wifi_sta_get_ap_info(wifi_ap_record_t *ap){(void)ap;return ESP_OK;}
static void ml_policy_get_status(ml_policy_status_t *p){p->authority_ready=false;}
static bool tailscale_is_connected(void){return true;}
static bool homelab_ops_admit(void){return admit;}
static int ntfy_integration_queue_event(const char *s){assert(s);notifications++;return 0;}
static void mqtt_integration_publish_now(void){publishes++;}
static int nvs_open(const char *s,int mode,int *h){(void)s;(void)mode;*h=1;return ++stage==fault?-1:0;}
static int nvs_set_blob(int h,const char *k,const void *p,size_t n){(void)h;(void)k;assert(p&&n);return ++stage==fault?-1:0;}
static int nvs_commit(int h){(void)h;return ++stage==fault?-1:0;}
static void nvs_close(int h){(void)h;}
static void health_monitor_init(void){}
static int homelab_ops_start_optional_worker(void){return worker_fail?-3:0;}
'''
adapters=r'''
static int health_probe(const health_config_t *c,unsigned role){assert(c&&role<4);probe_calls++;if(race_generation)health_generation++;return probe_result;}
'''
tests=r'''
int main(void){
    health_config_t c={.interval_s=60,.failure_threshold=3};assert(health_valid(&c));
    c.enabled=2;assert(!health_valid(&c));c.enabled=0;c.interval_s=29;assert(!health_valid(&c));c.interval_s=60;
    c.failure_threshold=0;assert(!health_valid(&c));c.failure_threshold=3;
    strcpy(c.internet_ip,"192.168.1.1");c.internet_port=443;assert(!health_valid(&c));
    strcpy(c.internet_ip,"1.1.1.1");assert(health_valid(&c));c.internet_port=0;assert(!health_valid(&c));c.internet_port=443;
    strcpy(c.tailnet_target,"192.0.2.1");c.tailnet_port=22;assert(!health_valid(&c));
    strcpy(c.tailnet_target,"100.64.0.1");assert(health_valid(&c));strcpy(c.tailnet_target,"peer.example");assert(health_valid(&c));
    strcpy(c.dns_name,"https://example.invalid");assert(!health_valid(&c));strcpy(c.dns_name,"fixture.invalid");assert(health_valid(&c));
    for(unsigned f=1;f<=3;f++){configuration=(health_config_t){0};fault=f;stage=0;assert(health_monitor_set(&c)!=0);assert(!configuration.interval_s);}
    fault=0;stage=0;assert(health_monitor_set(&c)==0);assert(configuration.interval_s==60);
    c.enabled=1;worker_fail=true;assert(health_monitor_set(&c)!=0&&!configuration.enabled);worker_fail=false;
    assert(health_monitor_set(&c)==0&&configuration.enabled);assert(health_configured(&c,1)&&!health_configured(&c,0));
    health_result r={0};health_observe(&r,0,3,1000,1,60);assert(r.state==H_DEGRADED&&r.failures==1&&r.due==121000);
    health_observe(&r,0,3,2000,1,60);assert(r.state==H_DEGRADED);
    health_observe(&r,0,3,3000,1,60);assert(r.state==H_DOWN&&r.failures==3);
    health_observe(&r,-1,3,4000,0,60);assert(r.state==H_UNKNOWN&&!r.failures);
    health_observe(&r,-2,3,5000,0,60);assert(r.state==H_RESOURCE);
    health_observe(&r,1,3,6000,1,60);assert(r.state==H_OK&&!r.failures&&r.due==66000);
    health_monitor_poll();assert(probe_calls==1);health_monitor_poll();assert(probe_calls==1);
    fixture_now+=60000;admit=false;health_monitor_poll();assert(probe_calls==1);admit=true;
    c.enabled=0;assert(health_monitor_set(&c)==0);fixture_now+=60000;health_monitor_poll();assert(probe_calls==1);
    c.enabled=1;assert(health_monitor_set(&c)==0);race_generation=true;health_monitor_poll();race_generation=false;
    for(unsigned i=0;i<4;i++)assert(!observations[i].observed); /* No stale-config publication. */
    strcpy(c.dns_name,"operator-private.example");strcpy(c.tailnet_target,"private-peer.example");assert(health_monitor_set(&c)==0);
    cJSON *safe=health_monitor_snapshot(false),*detail=health_monitor_snapshot(true);assert(safe&&detail);
    char *plain=cJSON_PrintUnformatted(safe),*private=cJSON_PrintUnformatted(detail);assert(plain&&private);
    assert(!strstr(plain,c.dns_name)&&!strstr(plain,c.internet_ip)&&!strstr(plain,c.tailnet_target));
    assert(strstr(private,c.dns_name)&&strstr(private,c.internet_ip)&&strstr(private,c.tailnet_target));
    free(plain);free(private);cJSON_Delete(safe);cJSON_Delete(detail);
    puts("PASS: actual health bounds/persistence faults, worker refusal, cadence/admission/generation, failure/backoff evidence and sanitized snapshot (mock probes/platform)");
}
'''
with tempfile.TemporaryDirectory(prefix='health-monitor-') as folder:
    p=Path(folder);(p/'test.c').write_text(fixture+types+adapters+''.join(function(s) for s in (
        'static uint32_t health_checksum(','static bool health_name(','static bool health_public(',
        'static bool health_valid(','static esp_err_t health_save_locked(','esp_err_t health_monitor_set(',
        'esp_err_t health_monitor_set_enabled(','static bool health_configured(','static void health_observe(',
        'static const char *health_reason(','static const char *health_next_step(','void health_monitor_poll(','cJSON *health_monitor_snapshot('))+tests)
    binary=p/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-O1','-g']
    libs=['-lws2_32'] if os.name=='nt' else []
    cjson=os.environ.get('CJSON_SOURCE')
    if cjson:flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('HEALTH_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
