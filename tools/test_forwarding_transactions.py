"""Actual AP/Tailnet writers under deterministic, concurrent NVS completion.

Compiles the real implementation with pthread-backed FreeRTOS adapters. NVS,
resolution and lwIP are fixtures; no device, packets or network are accessed.
FORWARDING_SANITIZE=1 enables ASan/UBSan. Not a hardware timing proof.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def implementation(name):
    return '\n'.join(line for line in (ROOT/'main'/name).read_text().splitlines()
                     if not line.startswith('#include'))


fixture = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <pthread.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#include "portmap.h"
#include "tailnet_forward.h"
/* Actual lease persistence has its own driver; existing transactions use none. */
static void service_lease_init(void){}
static bool service_lease_tick(void){return false;}
static bool service_lease_allowed(int i,const tailnet_forward_rule_t *r){(void)i;(void)r;return true;}
static uint32_t service_lease_token(const tailnet_forward_rule_t *r){return r->listen_port;}
static void mqtt_integration_tailnet_forward_changed(void){}
static bool service_lease_delete_requested(const tailnet_forward_rule_t *r){(void)r;return false;}
static int64_t esp_timer_get_time(void){return 0;}
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
static void *heap_caps_malloc(size_t n,int caps){(void)caps;return malloc(n);}
#include "control_validation.h"
#include "web_ui.h"
#define NVS_NAMESPACE "tsr"
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define portMAX_DELAY 0
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define configASSERT(x) assert(x)
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(m) assert(!pthread_mutex_lock(m))
#define portEXIT_CRITICAL(m) assert(!pthread_mutex_unlock(m))
typedef pthread_mutex_t StaticSemaphore_t;
typedef StaticSemaphore_t *SemaphoreHandle_t;
static pthread_mutex_t gate_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t gate_cv=PTHREAD_COND_INITIALIZER;
static bool first_committed, release_first, second_observed, second_done;
static _Thread_local unsigned actor;
static SemaphoreHandle_t transaction_lock;
static _Thread_local bool owns_transaction;
static __attribute__((unused)) SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *s) {
    assert(!pthread_mutex_init(s,NULL)); return s;
}
static void xSemaphoreTake(SemaphoreHandle_t h,int wait) {
    (void)wait; assert(h);
    if(h==transaction_lock && actor==2) {
        assert(!pthread_mutex_lock(&gate_lock)); second_observed=true;
        assert(!pthread_cond_broadcast(&gate_cv)); assert(!pthread_mutex_unlock(&gate_lock));
    }
    assert(!pthread_mutex_lock(h));
    if(h==transaction_lock) { assert(!owns_transaction); owns_transaction=true; }
}
static void xSemaphoreGive(SemaphoreHandle_t h) {
    if(h==transaction_lock) { assert(owns_transaction); owns_transaction=false; }
    assert(!pthread_mutex_unlock(h));
}
static int xTaskCreate(void (*fn)(void*),const char *name,unsigned stack,void *arg,unsigned prio,void *handle) {
    assert(fn && !strcmp(name,"tn_forward") && stack==4096 && !arg && prio==4 && !handle); return pdPASS;
}
static void vTaskDelay(unsigned t) { (void)t; abort(); }
static void tailnet_reassembly_refresh(void) {}
static void netif_hooks_refresh(void) {}
typedef struct { uint32_t addr; } ip4_addr_t;
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define lwip_htonl swap32
static size_t strlcpy(char *d,const char *s,size_t z) {
    size_t n=strlen(s); if(z) { size_t c=n<z-1?n:z-1; memcpy(d,s,c); d[c]=0; } return n;
}
static bool ip4addr_aton(const char *s,ip4_addr_t *a) {
    unsigned b[4]; char extra;
    if(sscanf(s,"%u.%u.%u.%u%c",&b[0],&b[1],&b[2],&b[3],&extra)!=4)return false;
    for(unsigned i=0;i<4;i++)if(b[i]>255)return false;
    a->addr=swap32((b[0]<<24)|(b[1]<<16)|(b[2]<<8)|b[3]);return true;
}
typedef struct { int unused; } microlink_t;
static microlink_t ml;
static bool tailscale_connected=true;
static microlink_t *tailscale_get_microlink(void) { return &ml; }
static uint32_t microlink_resolve(microlink_t *m,const char *s) { (void)m; (void)s; return 0; }
static bool tailscale_exit_server_active(void) { return false; }
static uint16_t tailscale_peerapi_port(void) { return 41180; }
static void log_stub(const char *tag,const char *fmt,...) { (void)tag; (void)fmt; }
#define ESP_LOGI(...) log_stub(__VA_ARGS__)
#define ESP_LOGE(...) log_stub(__VA_ARGS__)
static const char *esp_err_to_name(esp_err_t err) { (void)err; return "fixture failure"; }
typedef unsigned nvs_handle_t;
typedef struct { uint8_t data[2048]; size_t size; } blob_t;
static blob_t persisted[2];
static _Thread_local blob_t pending;
static _Thread_local unsigned pending_key;
static pthread_mutex_t nvs_lock=PTHREAD_MUTEX_INITIALIZER;
static unsigned key_index(const char *key) {
    if(!strcmp(key,"tn_fwd"))return 0;
    assert(!strcmp(key,"portmap"));return 1;
}
static esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h) {
    (void)mode;assert(!strcmp(ns,NVS_NAMESPACE));*h=1;return ESP_OK;
}
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *n) {
    (void)h;unsigned k=key_index(key);assert(!pthread_mutex_lock(&nvs_lock));
    esp_err_t result=persisted[k].size && *n>=persisted[k].size ? ESP_OK : ESP_FAIL;
    if(result==ESP_OK) { *n=persisted[k].size;memcpy(out,persisted[k].data,*n); }
    assert(!pthread_mutex_unlock(&nvs_lock));return result;
}
static esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t n) {
    (void)h;assert(n<=sizeof pending.data);pending_key=key_index(key);
    pending.size=n;memcpy(pending.data,data,n);return ESP_OK;
}
static esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h;assert(!pthread_mutex_lock(&nvs_lock));persisted[pending_key]=pending;
    assert(!pthread_mutex_unlock(&nvs_lock));return ESP_OK;
}
static void nvs_close(nvs_handle_t h) {
    (void)h;if(actor!=1)return;
    assert(!pthread_mutex_lock(&gate_lock));first_committed=true;
    assert(!pthread_cond_broadcast(&gate_cv));
    while(!release_first)assert(!pthread_cond_wait(&gate_cv,&gate_lock));
    assert(!pthread_mutex_unlock(&gate_lock));
}
static uint16_t port_nvs=8080;
static esp_err_t nvs_param_get_u16(const char *key,uint16_t *port) {
    assert(!strcmp(key,"web_port"));assert(!pthread_mutex_lock(&nvs_lock));
    *port=port_nvs;assert(!pthread_mutex_unlock(&nvs_lock));return ESP_OK;
}
static esp_err_t nvs_param_set_u16(const char *key,uint16_t port) {
    assert(owns_transaction&&!strcmp(key,"web_port"));assert(!pthread_mutex_lock(&nvs_lock));
    port_nvs=port;assert(!pthread_mutex_unlock(&nvs_lock));nvs_close(1);return ESP_OK;
}
typedef int err_t;
#define ERR_OK 0
#define IPSTR "%u"
#define IP2STR(a) ((unsigned)(a)->addr)
typedef struct { int unused; } esp_netif_t;
typedef struct { struct { uint32_t addr; } ip; } esp_netif_ip_info_t;
static esp_netif_t sta;
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) { assert(!strcmp(key,"WIFI_STA_DEF"));return &sta; }
static esp_err_t esp_netif_get_ip_info(esp_netif_t *n,esp_netif_ip_info_t *ip) { (void)n;ip->ip.addr=0xc0000201;return ESP_OK; }
static unsigned binding_count;
static bool ip_portmap_add(uint8_t p,uint32_t b,uint16_t l,uint32_t d,uint16_t dp) {
    assert(p&&b&&l&&d&&dp&&!owns_transaction);++binding_count;return true;
}
static void ip_portmap_remove(uint8_t p,uint16_t l) { assert(p&&l&&binding_count&&!owns_transaction);--binding_count; }
static err_t tcpip_callback_with_block(void (*cb)(void*),void *arg,int block) {
    assert(cb && !arg && block==1 && !owns_transaction);return ERR_OK;
}
'''

tests = r'''
typedef struct { unsigned id,operation; esp_err_t result; tailnet_forward_rule_t rules[2]; portmap_entry_t ap; } job_t;
static void *run(void *data) {
    job_t *job=data;actor=job->id;char why[128];
    if(job->operation==0)job->result=tailnet_forward_set_all(job->rules,2,why,sizeof why);
    else if(job->operation==1)job->result=tailnet_forward_set_enabled((int)job->id-1,false);
    else if(job->operation==2)job->result=portmap_set_all(&job->ap,1);
    else if(job->operation==3)job->result=portmap_set_all(&job->ap,0);
    else if(job->operation==4){portmap_install_cb(NULL);job->result=ESP_OK;}
    else {assert(job->operation==5);job->result=web_ui_save_port(job->ap.ext_port,NULL);}
    if(actor==2) {
        assert(!pthread_mutex_lock(&gate_lock));second_done=true;
        assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));
    }
    return NULL;
}
static void parallel(job_t *first,job_t *second) {
    first_committed=release_first=second_observed=second_done=false;
    pthread_t one,two;assert(!pthread_create(&one,NULL,run,first));
    assert(!pthread_mutex_lock(&gate_lock));
    while(!first_committed)assert(!pthread_cond_wait(&gate_cv,&gate_lock));
    assert(!pthread_mutex_unlock(&gate_lock));assert(!pthread_create(&two,NULL,run,second));
    assert(!pthread_mutex_lock(&gate_lock));
    /* Fixed code reaches the transaction lock; old code completes writer 2. */
    while(!second_observed&&!second_done)assert(!pthread_cond_wait(&gate_cv,&gate_lock));
    release_first=true;assert(!pthread_cond_broadcast(&gate_cv));assert(!pthread_mutex_unlock(&gate_lock));
    assert(!pthread_join(one,NULL));assert(!pthread_join(two,NULL));
}
int main(int argc,char **argv) {
    assert(argc==2);portmap_init();tailnet_forward_init();
    INIT_TRANSACTION_HANDLE
    tailnet_forward_rule_t rule={.valid=1,.enabled=1,.proto=6,.listen_port=2222,.destination_port=22,.source_network=0xc0000200,.source_prefix=24,.name="Synthetic service",.destination="100.64.0.2"};
    job_t first={.id=1},second={.id=2};first.rules[0]=second.rules[0]=rule;
    first.rules[1]=second.rules[1]=rule;first.rules[1].listen_port=second.rules[1].listen_port=3333;
    if(!strcmp(argv[1],"persist")) {
        second.rules[0].destination_port=222;parallel(&first,&second);
        assert(first.result==ESP_OK&&second.result==ESP_OK);
        store_t disk;assert(persisted[0].size==sizeof disk);memcpy(&disk,persisted[0].data,sizeof disk);
        tailnet_forward_rule_t live;assert(tailnet_forward_get(0,&live,NULL));
        assert(live.destination_port==disk.rules[0].destination_port && live.destination_port==222);
    } else if(!strcmp(argv[1],"toggle")) {
        char why[128];assert(tailnet_forward_set_all(first.rules,2,why,sizeof why)==ESP_OK);
        first.operation=second.operation=1;parallel(&first,&second);
        assert(first.result==ESP_OK&&second.result==ESP_OK);
        for(int i=0;i<2;i++) { tailnet_forward_rule_t live;assert(tailnet_forward_get(i,&live,NULL)&&!live.enabled); }
    } else if(!strcmp(argv[1],"install")) {
        first.ap=(portmap_entry_t){.proto=6,.ext_port=2222,.int_port=22,.int_ip=0xc0000202};
        assert(portmap_set_all(&first.ap,1)==ESP_OK);portmap_install_cb(NULL);assert(binding_count==1);
        first.operation=3;second.operation=4;parallel(&first,&second);
        assert(first.result==ESP_OK&&second.result==ESP_OK&&portmap_count()==0&&binding_count==0);
    } else if(!strcmp(argv[1],"web-after-ap")||!strcmp(argv[1],"ap-after-web")||!strcmp(argv[1],"web-after-tailnet")) {
        first.ap=second.ap=(portmap_entry_t){.proto=6,.ext_port=2222,.int_port=22,.int_ip=0xc0000202};
        first.operation=!strcmp(argv[1],"web-after-tailnet")?0:2;second.operation=5;
        if(!strcmp(argv[1],"ap-after-web")){first.operation=5;second.operation=2;}
        parallel(&first,&second);
        assert(first.result==ESP_OK&&second.result==ESP_ERR_INVALID_STATE);
        if(first.operation==5)assert(port_nvs==2222&&!portmap_count());
        else assert(port_nvs==8080);
    } else if(!strcmp(argv[1],"live-port")) {
        web_ui_set_active_port(80);assert(web_ui_port_reserved(80));
        first.ap=(portmap_entry_t){.proto=6,.ext_port=80,.int_port=22,.int_ip=0xc0000202};
        assert(portmap_set_all(&first.ap,1)==ESP_ERR_INVALID_STATE);
        char why[128];first.rules[0].listen_port=80;
        assert(tailnet_forward_set_all(first.rules,1,why,sizeof why)==ESP_ERR_INVALID_STATE);
        /* Legacy records remain saved but cannot install over the admin port. */
        s_table[0]=first.ap;s_table[0].valid=1;s_count=1;
        portmap_install_cb(NULL);assert(!binding_count&&portmap_count()==1);
    } else {
        assert(!strcmp(argv[1],"conflict"));first.operation=2;
        first.ap=(portmap_entry_t){.proto=6,.ext_port=2222,.int_port=22,.int_ip=0xc0000202};
        parallel(&first,&second);
        assert(first.result==ESP_OK&&second.result==ESP_ERR_INVALID_STATE);
        assert(portmap_listen_conflicts(6,2222)&&!tailnet_forward_listen_conflicts(6,2222));
    }
    printf("PASS: real forwarding transaction concurrency - %s\n",argv[1]);
}
'''

shared = ROOT/'main/forwarding_config.c'
if shared.exists():
    assert '"forwarding_config.c"' in (ROOT/'main/CMakeLists.txt').read_text(), 'Shared transaction implementation must be compiled'
shared_source = implementation('forwarding_config.c') if shared.exists() else ''
init = 'forwarding_config_lock();forwarding_config_unlock();transaction_lock=s_config_lock;' if shared.exists() else '(void)transaction_lock;'
tailnet = implementation('tailnet_forward.c').split('static bool packet_fields',1)[0]
ap = implementation('portmap.c')
# Separate translation-unit private variables without changing their behavior.
tailnet = '#define s_count tn_count\n#define s_loaded tn_loaded\n#define set_all_locked tn_set_all_locked\n' + tailnet + '\n#undef s_count\n#undef s_loaded\n#undef set_all_locked\n#undef NVS_KEY\n'
with tempfile.TemporaryDirectory(prefix='forwarding-transactions-') as directory:
    path=Path(directory);(path/'lwip').mkdir()
    for name in ('pbuf','netif'):
        (path/f'lwip/{name}.h').write_text(f'#pragma once\nstruct {name};\n')
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n')
    web_port=implementation('web_port.c')
    (path/'test.c').write_text('\n'.join((fixture,shared_source,tailnet,ap,web_port,tests.replace('INIT_TRANSACTION_HANDLE',init))))
    flags=['-std=c11','-Wall','-Wextra','-Werror','-pthread']
    if os.environ.get('FORWARDING_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,'-I',str(path),'-I',str(ROOT/'main'),str(path/'test.c'),'-o',str(binary)],check=True)
    failed=[]
    for scenario in ('persist','toggle','conflict','install','web-after-ap','ap-after-web','web-after-tailnet','live-port'):
        try:
            subprocess.run([str(binary),scenario],check=True,timeout=15)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            failed.append(scenario)
    assert not failed, f'Concurrent forwarding failures: {failed}'
