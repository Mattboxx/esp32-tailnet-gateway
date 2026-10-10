"""Run actual Tailnet rule loading/saving with synthetic NVS and task services.

No device/network access. TAILNET_SANITIZE=1 enables ASan/UBSan in CI.
The fake resolver accepts documentation-only literal addresses and a synthetic
peer name; it does not model the SDK address parser or live MagicDNS.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'main/tailnet_forward.c').read_text(encoding='utf-8').split('static bool packet_fields',1)[0]
source='\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
fixture=r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#include "tailnet_forward.h"
#include "control_validation.h"
#define NVS_NAMESPACE "tsr"
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define portMAX_DELAY 0
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
typedef unsigned nvs_handle_t;
typedef struct { int unused; } StaticSemaphore_t;
typedef StaticSemaphore_t *SemaphoreHandle_t;
static StaticSemaphore_t fake_lock;
static int lock_depth;
static SemaphoreHandle_t xSemaphoreCreateMutex(void) { return &fake_lock; }
static SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *s) { return s; }
static void xSemaphoreTake(SemaphoreHandle_t h,int wait) { (void)wait; assert(h && !lock_depth); ++lock_depth; }
static void xSemaphoreGive(SemaphoreHandle_t h) { assert(h && lock_depth==1); --lock_depth; }
static unsigned task_creations, installs;
static int task_result=pdPASS;
static int xTaskCreate(void (*fn)(void*),const char *name,unsigned stack,void *arg,unsigned prio,void *handle) {
    assert(fn && !strcmp(name,"tn_forward") && stack==4096 && !arg && prio==4 && !handle);
    ++task_creations; return task_result;
}
static void vTaskDelay(unsigned t) { (void)t; abort(); }
static void netif_hooks_refresh(void) { assert(!lock_depth); }
static void portmap_install_all(void) { assert(!lock_depth); ++installs; }
static uint16_t ap_conflict;
static bool portmap_listen_conflicts(uint8_t proto,uint16_t port) { (void)proto; return port==ap_conflict; }
static uint16_t web_ui_configured_port(void) { return 8080; }
static bool tailscale_exit_server_active(void) { return true; }
static uint16_t tailscale_peerapi_port(void) { return 41180; }
static void log_stub(const char *tag,const char *fmt,...) { (void)tag; (void)fmt; }
#define ESP_LOGE(...) log_stub(__VA_ARGS__)
#define ESP_LOGW(...) log_stub(__VA_ARGS__)
typedef struct { uint32_t addr; } ip4_addr_t;
static uint32_t swap32(uint32_t x) { return ((x&255)<<24)|((x&0xff00)<<8)|((x>>8)&0xff00)|(x>>24); }
#define lwip_ntohl swap32
#define lwip_htonl swap32
static size_t strlcpy(char *d,const char *s,size_t z) {
    size_t n=strlen(s); if(z) { size_t copy=n<z-1?n:z-1; memcpy(d,s,copy); d[copy]=0; } return n;
}
static bool ip4addr_aton(const char *s,ip4_addr_t *a) {
    unsigned b[4]; char extra;
    if(sscanf(s,"%u.%u.%u.%u%c",&b[0],&b[1],&b[2],&b[3],&extra)!=4) return false;
    for(unsigned i=0;i<4;i++) if(b[i]>255) return false;
    a->addr=swap32((b[0]<<24)|(b[1]<<16)|(b[2]<<8)|b[3]); return true;
}
typedef struct { int unused; } microlink_t;
static microlink_t ml;
static bool tailscale_connected=true;
static microlink_t *tailscale_get_microlink(void) { return &ml; }
static uint32_t microlink_resolve(microlink_t *m,const char *s) { assert(m==&ml); return !strcmp(s,"test-peer")?0x64400002:0; }
static uint8_t persisted[2048], pending[2048];
static size_t persisted_size, pending_size;
static bool have_blob;
static unsigned fail_phase, writes;
static esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h) { assert(!strcmp(ns,NVS_NAMESPACE)); *h=1; return mode==NVS_READWRITE&&fail_phase==1?ESP_FAIL:ESP_OK; }
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *data,size_t *size) {
    (void)h; assert(!strcmp(key,"tn_fwd")); if(!have_blob||*size<persisted_size)return ESP_FAIL;
    memcpy(data,persisted,persisted_size); *size=persisted_size; return ESP_OK;
}
static esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t size) {
    (void)h; assert(!strcmp(key,"tn_fwd") && size<=sizeof pending); ++writes;
    memcpy(pending,data,size); pending_size=size; return fail_phase==2?ESP_FAIL:ESP_OK;
}
static esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h; if(fail_phase==3)return ESP_FAIL;
    memcpy(persisted,pending,pending_size); persisted_size=pending_size; have_blob=true; return ESP_OK;
}
static void nvs_close(nvs_handle_t h) { (void)h; }
'''
tests=r'''
static void load(const store_t *st) {
    assert(sizeof *st<=sizeof persisted); memcpy(persisted,st,sizeof *st); persisted_size=sizeof *st; have_blob=true;
    s_loaded=false; s_count=0; tailnet_forward_init();
}
int main(void) {
    tailnet_forward_rule_t rule={.valid=1,.enabled=1,.proto=6,.listen_port=2222,.destination_port=22,.source_network=0xc0000200,.source_prefix=24,.name="Synthetic SSH",.destination="100.64.0.2"};
    store_t st={.magic=STORE_MAGIC}; st.rules[3]=rule; load(&st);
    tailnet_forward_rule_t out;
    assert(tailnet_forward_count()==1 && tailnet_forward_get(0,&out,NULL) && out.listen_port==2222);
    st.magic^=1; load(&st); assert(tailnet_forward_count()==0); st.magic^=1;
    memcpy(persisted,&st,sizeof st); persisted_size=sizeof st-1;
    s_loaded=false; tailnet_forward_init(); assert(tailnet_forward_count()==0);
    /* Structurally corrupt active records must not enter packet/runtime code. */
    for(unsigned kind=0;kind<9;kind++) {
        memset(&st,0,sizeof st); st.magic=STORE_MAGIC; st.rules[0]=rule; st.rules[1]=rule;
        st.rules[1].listen_port=3333;
        switch(kind) {
        case 0: st.rules[1].source_prefix=33; break;
        case 1: memset(st.rules[1].name,'x',sizeof st.rules[1].name); break;
        case 2: memset(st.rules[1].destination,'x',sizeof st.rules[1].destination); break;
        case 3: st.rules[1].enabled=2; break;
        case 4: st.rules[1].valid=2; break;
        case 5: st.rules[1].source_network|=1; break;
        case 6: st.rules[1].proto=1; break;
        case 7: strcpy(st.rules[1].destination,"192.0.2.2"); break;
        case 8: st.rules[1].listen_port=2222; break;
        }
        load(&st); assert(tailnet_forward_count()==0 && !tailnet_forward_get(0,&out,NULL));
    }
    memset(&st,0,sizeof st); st.magic=STORE_MAGIC; st.rules[0]=rule; load(&st);
    char why[128]; tailnet_forward_rule_t changed=rule; changed.listen_port=3333;
    for(fail_phase=1;fail_phase<=3;fail_phase++) {
        assert(tailnet_forward_set_all(&changed,1,why,sizeof why)==ESP_FAIL);
        assert(tailnet_forward_get(0,&out,NULL) && out.listen_port==2222);
    }
    fail_phase=0;
    unsigned before=writes;
    changed.enabled=2; assert(tailnet_forward_set_all(&changed,1,why,sizeof why)==ESP_ERR_INVALID_ARG);
    changed=rule; memset(changed.name,'x',sizeof changed.name); assert(tailnet_forward_set_all(&changed,1,why,sizeof why)==ESP_ERR_INVALID_ARG);
    /* A nonterminated destination at the end of an allocated record. */
    tailnet_forward_rule_t *bad=malloc(sizeof *bad); assert(bad); memset(bad,'x',sizeof *bad);
    bad->valid=bad->enabled=1; bad->proto=6; bad->source_prefix=0; bad->source_network=0;
    bad->name[0]=0; /* reach the destination guard, not the earlier name guard */
    assert(tailnet_forward_set_all(bad,1,why,sizeof why)==ESP_ERR_INVALID_ARG); free(bad);
    assert(writes==before);
    changed=rule; strcpy(changed.destination,"test-peer"); assert(tailnet_forward_set_all(&changed,1,why,sizeof why)==ESP_OK);
    assert(tailnet_forward_set_enabled(0,false)==ESP_OK);
    tailnet_forward_runtime_t rt; assert(tailnet_forward_get(0,&out,&rt) && !out.enabled && !rt.installed);
    assert(!tailnet_forward_listen_conflicts(6,2222));
    assert(task_creations>=10 && installs>=2 && !lock_depth);
    puts("PASS: actual Tailnet NVS hole compaction, invalid prefix/strings/flags/protocol/network/destination/duplicates fail closed, bounded setter validation, NVS failure preservation, hostname and enable control");
}
'''
with tempfile.TemporaryDirectory(prefix='tailnet-state-') as directory:
    path=Path(directory); (path/'lwip').mkdir()
    (path/'lwip/pbuf.h').write_text('#pragma once\nstruct pbuf;\n',encoding='utf-8')
    (path/'lwip/netif.h').write_text('#pragma once\nstruct netif;\n',encoding='utf-8')
    (path/'esp_err.h').write_text('/* fixture supplies esp_err_t */\n',encoding='utf-8')
    # These APIs are mutually exclusive in the source. Mark fixture adapters
    # unused so both old and fixed firmware can reproduce/run under -Werror.
    fixture=fixture.replace('static SemaphoreHandle_t xSemaphoreCreateMutex', 'static __attribute__((unused)) SemaphoreHandle_t xSemaphoreCreateMutex')
    fixture=fixture.replace('static void log_stub', 'static __attribute__((unused)) void log_stub')
    (path/'test.c').write_text(fixture+source+tests,encoding='utf-8')
    flags=['-std=c11','-Wall','-Wextra','-Werror']
    if os.environ.get('TAILNET_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=path/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,'-I',str(path),'-I',str(ROOT/'main'),str(path/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
