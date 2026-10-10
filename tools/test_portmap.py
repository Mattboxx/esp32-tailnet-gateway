"""Exercise actual AP-side portmap persistence/install with failed NVS writes.

No device/network access. PORTMAP_SANITIZE=1 enables ASan/UBSan in CI.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/portmap.c').read_text(encoding='utf-8')
if os.environ.get('PORTMAP_BASELINE') == '1':
    source = subprocess.check_output(['git','show','2ad033009ed28da46ce51ea04d704a10fc159ae6:main/portmap.c'],cwd=ROOT,text=True)
source = '\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_ERR_INVALID_STATE -3
#include "portmap.h"
#include "tailnet_forward.h"
#define NVS_NAMESPACE "tsr"
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define TAILNET_FORWARD_MAX 8
#define ERR_OK 0
#define IPSTR "%u"
#define IP2STR(a) ((unsigned)(a)->addr)
typedef int err_t;
typedef unsigned nvs_handle_t;
typedef struct { int unused; } esp_netif_t;
typedef struct { struct { uint32_t addr; } ip; } esp_netif_ip_info_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
static int critical_depth;
static int transaction_depth;
static void forwarding_config_lock(void) { assert(!critical_depth && !transaction_depth); transaction_depth=1; }
static void forwarding_config_unlock(void) { assert(!critical_depth && transaction_depth==1); transaction_depth=0; }
#define portENTER_CRITICAL(m) do { (void)(m); assert(critical_depth==0); critical_depth=1; } while(0)
#define portEXIT_CRITICAL(m) do { (void)(m); assert(critical_depth==1); critical_depth=0; } while(0)
static void log_stub(const char *tag,const char *fmt,...) { (void)tag; (void)fmt; assert(!critical_depth); }
#define ESP_LOGI(...) log_stub(__VA_ARGS__)
#define ESP_LOGE(...) log_stub(__VA_ARGS__)
static const char *esp_err_to_name(esp_err_t err) { (void)err; return "fixture failure"; }
static portmap_entry_t persisted[PORTMAP_MAX], pending[PORTMAP_MAX];
static bool have_blob, queue_failure, sta_down, tailnet_available, tailnet_installed;
static unsigned fail_phase, writes, commits, closes, prepares;
static uint16_t expected_visible, tailnet_conflict;
static void (*queued_callback)(void *);
static esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h) {
    assert(!critical_depth && !strcmp(ns,NVS_NAMESPACE)); *h=1;
    return mode==NVS_READWRITE && fail_phase==1 ? ESP_FAIL : ESP_OK;
}
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *n) {
    (void)h; assert(!critical_depth && !strcmp(key,"portmap") && *n==sizeof persisted);
    if(!have_blob) return ESP_FAIL;
    memcpy(out,persisted,sizeof persisted); return ESP_OK;
}
static void assert_visible(void) {
    if(!expected_visible) return;
    portmap_entry_t out;
    assert(portmap_count()==1 && portmap_get(0,&out) && out.ext_port==expected_visible);
    assert(portmap_listen_conflicts(PORTMAP_PROTO_TCP,expected_visible));
}
static esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t n) {
    (void)h; assert(!critical_depth && !strcmp(key,"portmap") && n==sizeof pending);
    ++writes; assert_visible(); memcpy(pending,data,n); return fail_phase==2?ESP_FAIL:ESP_OK;
}
static esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h; assert(!critical_depth); ++commits; assert_visible();
    if(fail_phase==3) return ESP_FAIL;
    memcpy(persisted,pending,sizeof persisted); have_blob=true; return ESP_OK;
}
static void nvs_close(nvs_handle_t h) { (void)h; assert(!critical_depth); ++closes; }
bool tailnet_forward_listen_conflicts(uint8_t proto,uint16_t port) { (void)proto; assert(!critical_depth); return port==tailnet_conflict; }
static uint16_t web_ui_configured_port(void) { return 8080; }
static bool web_ui_port_reserved(uint16_t port) { return port==web_ui_configured_port()||port==80; }
static bool tailscale_exit_server_active(void) { return true; }
static uint16_t tailscale_peerapi_port(void) { return 41180; }
static esp_netif_t sta;
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) { assert(!strcmp(key,"WIFI_STA_DEF")); return &sta; }
static esp_err_t esp_netif_get_ip_info(esp_netif_t *n,esp_netif_ip_info_t *ip) { (void)n; ip->ip.addr=sta_down?0:0xc0000201; return ESP_OK; }
static struct { uint8_t proto; uint16_t port; uint32_t dest; } bindings[PORTMAP_MAX+TAILNET_FORWARD_MAX];
static int binding_count;
static bool ip_portmap_add(uint8_t proto,uint32_t bind,uint16_t port,uint32_t dest,uint16_t dp) {
    assert(!critical_depth && bind && dp && binding_count<PORTMAP_MAX+TAILNET_FORWARD_MAX);
    bindings[binding_count].proto=proto; bindings[binding_count].port=port;
    bindings[binding_count++].dest=dest; return true;
}
static void ip_portmap_remove(uint8_t proto,uint16_t port) {
    assert(!critical_depth);
    for(int i=0;i<binding_count;i++) if(bindings[i].proto==proto && bindings[i].port==port) {
        bindings[i]=bindings[--binding_count]; return;
    }
    assert(false);
}
void tailnet_forward_prepare_install(void) { assert(!critical_depth); ++prepares; tailnet_installed=false; }
int tailnet_forward_snapshot_mappings(tailnet_forward_mapping_t *out,int capacity) {
    assert(!critical_depth && capacity==TAILNET_FORWARD_MAX); if(!tailnet_available)return 0;
    out[0]=(tailnet_forward_mapping_t){.rule={.valid=1,.enabled=1,.proto=6,.listen_port=4444,.destination_port=22},.destination_nbo=0x64500001,.slot=0};return 1;
}
void tailnet_forward_mark_installed(const tailnet_forward_mapping_t *m,bool ok,const char *err) { assert(m->slot==0 && m->binding_ip_nbo==0xc0000201 && !err); tailnet_installed=ok; }
static err_t tcpip_callback_with_block(void (*cb)(void *),void *arg,int block) {
    assert(!critical_depth && !transaction_depth && !arg && block==1); if(queue_failure) return ESP_FAIL;
    queued_callback=cb; return ERR_OK;
}
static void drain(void) { if(queued_callback) { void (*cb)(void*)=queued_callback; queued_callback=NULL; cb(NULL); } }
'''
tests = r'''
int main(void) {
    assert(web_ui_port_reserved(80));
    /* A valid legacy blob may contain occupied nonconsecutive slots. */
    persisted[3]=(portmap_entry_t){.valid=1,.proto=6,.ext_port=2222,.int_port=22,.int_ip=0xc0000202,.name="legacy"};
    have_blob=true;portmap_init();portmap_entry_t loaded;
    assert(portmap_count()==1&&portmap_get(0,&loaded)&&loaded.ext_port==2222);
    for(unsigned kind=0;kind<5;kind++) {
        memset(persisted,0,sizeof persisted);persisted[0]=loaded;persisted[1]=loaded;
        persisted[1].ext_port=3333;
        switch(kind) {
        case 0:persisted[1].valid=2;break;
        case 1:persisted[1].proto=1;break;
        case 2:persisted[1].int_port=0;break;
        case 3:memset(persisted[1].name,'x',sizeof persisted[1].name);break;
        case 4:persisted[1].ext_port=2222;break;
        }
        s_loaded=false;portmap_init();assert(!portmap_count());
    }
    s_loaded=false;have_blob=false;
    portmap_init(); assert(portmap_count()==0 && !portmap_get(0,NULL));
    portmap_entry_t old={.proto=6,.ext_port=2222,.int_port=22,.int_ip=0xc0000202,.name="old"};
    assert(portmap_set_all(&old,1)==ESP_OK); drain();
    assert(binding_count==1 && bindings[0].port==2222 && portmap_count()==1);
    expected_visible=2222;
    portmap_entry_t changed=old; changed.ext_port=3333; changed.int_ip=0xc0000203;
    for(fail_phase=1;fail_phase<=3;fail_phase++) {
        unsigned before_writes=writes, before_commits=commits;
        assert(portmap_set_all(&changed,1)==ESP_FAIL);
        assert_visible(); assert(!portmap_listen_conflicts(6,3333));
        assert(persisted[0].ext_port==2222 && binding_count==1 && bindings[0].port==2222);
        assert(writes==before_writes+(fail_phase!=1) && commits==before_commits+(fail_phase==3));
        portmap_install_all(); drain(); /* a later DHCP refresh must not install the failed save */
        assert(binding_count==1 && bindings[0].port==2222 && bindings[0].dest==old.int_ip);
    }
    fail_phase=0;
    unsigned before_writes=writes;
    changed.ext_port=8080; assert(portmap_set_all(&changed,1)==ESP_ERR_INVALID_STATE);
    changed.ext_port=80; assert(portmap_set_all(&changed,1)==ESP_ERR_INVALID_STATE);
    changed.ext_port=3333;memset(changed.name,'x',sizeof changed.name);
    assert(portmap_set_all(&changed,1)==ESP_ERR_INVALID_ARG);memset(changed.name,0,sizeof changed.name);
    changed.ext_port=41180; assert(portmap_set_all(&changed,1)==ESP_ERR_INVALID_STATE);
    changed.ext_port=4444; tailnet_conflict=4444; assert(portmap_set_all(&changed,1)==ESP_ERR_INVALID_STATE);
    tailnet_conflict=0; assert(writes==before_writes); assert_visible();
    changed.ext_port=3333;
    assert(portmap_set_all(&changed,1)==ESP_OK); expected_visible=3333; assert_visible();
    assert(persisted[0].ext_port==3333); drain();
    assert(binding_count==1 && bindings[0].port==3333 && bindings[0].dest==changed.int_ip);
    tailnet_available=true; portmap_install_all(); drain();
    assert(binding_count==2 && tailnet_installed);
    sta_down=true; portmap_install_all(); drain();
    assert(binding_count==0 && portmap_count()==1 && !tailnet_installed);
    sta_down=false; portmap_install_all(); drain();
    assert(binding_count==2 && bindings[0].port==3333 && bindings[1].port==4444 && tailnet_installed);
    tailnet_available=false;
    expected_visible=0; assert(portmap_set_all(&changed,0)==ESP_OK); drain();
    assert(portmap_count()==0 && binding_count==0 && prepares>=5 && closes>0);
    puts("PASS: actual portmap preserves published/persisted/NAPT rules on NVS open/write/commit failure and later refresh; in-flight visibility, port conflicts, save, uplink loss/recovery and deletion");
}
'''
with tempfile.TemporaryDirectory(prefix='portmap-') as directory:
    path = Path(directory)
    (path/'lwip').mkdir()
    (path/'lwip/pbuf.h').write_text('#pragma once\nstruct pbuf;\n',encoding='utf-8')
    (path/'lwip/netif.h').write_text('#pragma once\nstruct netif;\n',encoding='utf-8')
    (path / 'esp_err.h').write_text('/* fixture supplies esp_err_t */\n', encoding='utf-8')
    (path / 'test.c').write_text(fixture + source + tests, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('PORTMAP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, '-I', str(path), '-I', str(ROOT/'main'), str(path/'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
