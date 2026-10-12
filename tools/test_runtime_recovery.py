"""Actual-C AP scheduler, Microlink startup rollback and bounded retry tests.

No device access. RUNTIME_SANITIZE=1 enables ASan/UBSan on CI.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(name, program):
    with tempfile.TemporaryDirectory(prefix='runtime-recovery-') as directory:
        path = Path(directory)
        source = path / 'test.c'
        source.write_text(program, encoding='utf-8')
        binary = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-Wno-unused-function']
        if os.environ.get('RUNTIME_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
        print('PASS:', name, flush=True)


headers = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <stdlib.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define pdPASS 1
#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY 0xffffffffu
#define pdMS_TO_TICKS(x) (x)
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
static int locks;
#define taskENTER_CRITICAL(x) do {(void)(x);assert(!locks);locks++;}while(0)
#define taskEXIT_CRITICAL(x) do {(void)(x);assert(locks==1);locks--;}while(0)
'''
ap_source = re.sub(r'^#include.*\n', '', (ROOT / 'main/ap_policy.c').read_text(), flags=re.M)
ap_fixture = r'''
typedef uint8_t StackType_t;
typedef unsigned TickType_t;
typedef int StaticTask_t;
typedef void *TaskHandle_t;
static int64_t clock_us;
static unsigned allocations, mode_calls, mode_failures, notifications;
static bool last_target, request_during_apply;
static void (*spawned)(void *), (*shutdown_callback)(void);
static jmp_buf blocked;
static int64_t esp_timer_get_time(void) {return clock_us;}
static int esp_register_shutdown_handler(void (*cb)(void)){shutdown_callback=cb;return ESP_OK;}
static TaskHandle_t xTaskCreateStatic(void(*fn)(void*),const char*n,unsigned stack,
    void*a,int priority,StackType_t *buffer,StaticTask_t *tcb) {
    (void)n;(void)a;assert(!locks && stack==8192 && priority==5 && buffer && tcb);
    assert(((uintptr_t)buffer&15)==0);allocations++;spawned=fn;return tcb;
}
static void xTaskNotifyGive(TaskHandle_t task){assert(task && !locks);notifications++;}
static unsigned ulTaskNotifyTake(int clear,unsigned ticks);
'''
ap_tests = r'''
static bool apply(bool target) {
    assert(!locks);mode_calls++;last_target=target;
    if(request_during_apply){request_during_apply=false;ap_policy_request(!target);}
    if(mode_failures){mode_failures--;return false;}return true;
}
static unsigned ulTaskNotifyTake(int clear,unsigned ticks) {
    assert(clear && !locks);
    if(ticks==portMAX_DELAY && (!s_pending || s_shutdown))longjmp(blocked,1);
    if(ticks!=portMAX_DELAY)clock_us+=(int64_t)ticks*1000;
    return 0;
}
static void execute(void) {
    assert(spawned);
    if(!setjmp(blocked))spawned(NULL);
    assert(!locks);
}
int main(void) {
    assert(ap_policy_init(NULL)==ESP_ERR_INVALID_ARG);
    assert(ap_policy_init(apply)==ESP_OK);
    assert(allocations==1 && ap_policy_init(apply)==ESP_OK && allocations==1);
    ap_policy_request(false);
    for(unsigned i=0;i<1000;i++)ap_policy_request(false);
    assert(allocations==1 && s_pending);
    execute();assert(!last_target && mode_calls==1 && clock_us==1500000);
    ap_policy_request(true);execute();assert(last_target && mode_calls==2);
    mode_failures=1;ap_policy_request(false);int64_t before_time=clock_us;execute();
    assert(!s_pending && !last_target && clock_us==before_time+2500000);
    /* A new request arriving during apply must survive the older completion. */
    request_during_apply=true;mode_failures=1;ap_policy_request(true);execute();
    assert(!last_target && !s_pending);
    /* Replace an already queued transition before the worker gets CPU time. */
    ap_policy_request(true);ap_policy_request(false);execute();assert(!last_target);
    ap_policy_request(true);unsigned before=mode_calls;
    shutdown_callback();ap_policy_request(true);execute();
    assert(ap_policy_is_shutdown() && mode_calls==before && !s_pending && allocations==1);
    puts("AP recovery: one reserved stack, 1000 coalesced requests without allocation, grace/retry timing, latest-generation races and shutdown suppression");
}
'''
run('AP recovery remains allocation-free under runtime fragmentation', headers + ap_fixture + ap_source + ap_tests)

ml = (ROOT / 'external/microlink/components/microlink/src/microlink.c').read_text()
start = ml.split('    /* Create tasks */', 1)[1].split('\nesp_err_t microlink_stop', 1)[0]
ml_fixture = r'''
typedef int BaseType_t;
typedef struct {int events,coord_cmd_queue,tasks_alive;bool stop_incomplete;void *config_httpd;
    void *wg_mgr_task,*net_io_task,*derp_tx_task,*derp_rx_task,*coord_task;} microlink_t;
#define ML_TASK_WG_MGR_STACK 8192
#define ML_TASK_NET_IO_STACK 6144
#define ML_TASK_DERP_TX_STACK 10240
#define ML_TASK_COORD_STACK 12288
#define ML_TASK_WG_MGR_PRIO 7
#define ML_TASK_NET_IO_PRIO 7
#define ML_TASK_DERP_TX_PRIO 5
#define ML_TASK_COORD_PRIO 5
#define ML_TASK_WG_MGR_CORE 1
#define ML_TASK_NET_IO_CORE 0
#define ML_TASK_DERP_TX_CORE 0
#define ML_TASK_COORD_CORE 1
#define ML_EVT_WIFI_CONNECTED 1
#define ML_EVT_TASKS_READY 512
#define ML_CMD_CONNECT 1
typedef int ml_coord_cmd_t;
static void ml_wg_mgr_task(void *a){(void)a;}
static void ml_net_io_task(void *a){(void)a;}
static void ml_derp_tx_task(void *a){(void)a;}
static void ml_derp_rx_task(void *a){(void)a;}
static void ml_coord_task(void *a){(void)a;}
static int calls,fail_at,stops;static bool ready,incomplete;
static const char *expected[]={"ml_coord","ml_derp_tx","ml_derp_rx","ml_wg_mgr","ml_net_io"};
static int xTaskCreatePinnedToCore(void(*fn)(void*),const char*n,unsigned s,void*a,int p,void**h,int c) {
    (void)fn;(void)s;(void)a;(void)p;(void)c;
    assert(!ready && !strcmp(n,expected[calls]));int index=calls++;
    if(index==fail_at)return 0;
    *h=(void*)(uintptr_t)(index+1);return pdPASS;
}
static void xEventGroupSetBits(int e,int bits){(void)e;assert(calls==5 && (bits&ML_EVT_TASKS_READY));ready=true;}
static void xQueueSend(int q,const void*c,unsigned t){(void)q;(void)c;(void)t;assert(ready);}
static void ml_config_httpd_start(void*h,microlink_t*m){(void)h;(void)m;assert(ready);}
static void microlink_stop(microlink_t*m){stops++;m->tasks_alive=0;m->stop_incomplete=incomplete;
    m->wg_mgr_task=m->net_io_task=m->derp_tx_task=m->derp_rx_task=m->coord_task=NULL;}
'''
ml_tests = r'''
int main(void) {
    for(int failure=-1;failure<5;failure++) {
        calls=stops=0;ready=false;fail_at=failure;microlink_t node={0};
        int result=test_start(&node);
        if(failure<0){assert(result==ESP_OK && ready && node.tasks_alive==5 && !stops);}
        else {assert(result==ESP_ERR_NO_MEM && !ready && node.tasks_alive==0 && stops==1);}
    }
    calls=stops=0;ready=false;fail_at=2;incomplete=true;microlink_t node={0};
    assert(test_start(&node)==ESP_ERR_INVALID_STATE && !ready);
    puts("Microlink startup: descending stack sizes, ready barrier and rollback at all five allocation points; incomplete cleanup is not retryable");
}
'''
run('Microlink startup allocation rollback and registration barrier', headers + ml_fixture + 'static int test_start(microlink_t *ml) {\n' + start + ml_tests)

manager = (ROOT / 'main/tailscale_manager.c').read_text()
retry = 'for (unsigned attempt = 0;' + manager.split('for (unsigned attempt = 0;', 1)[1].split(
    '\n    taskENTER_CRITICAL(&s_connect_lock);\n    s_connect_in_flight = false;', 1)[0]
retry_fixture = r'''
static portMUX_TYPE s_connect_lock;
static bool s_start_retrying;static unsigned attempts,delayed,shortages;static int terminal;
static int tailscale_connect(void){assert(!locks);return attempts++<shortages?ESP_ERR_NO_MEM:terminal;}
static void vTaskDelay(unsigned ms){assert(!locks);delayed+=ms;}
'''
retry_tests = r'''
int main(void){
    shortages=3;terminal=ESP_OK;test_retry();assert(attempts==4 && delayed==14000 && !s_start_retrying);
    attempts=delayed=0;shortages=10;test_retry();assert(attempts==5 && delayed==30000 && !s_start_retrying);
    attempts=delayed=shortages=0;terminal=ESP_ERR_INVALID_ARG;test_retry();assert(attempts==1 && !delayed);
    attempts=0;terminal=ESP_ERR_INVALID_STATE;test_retry();assert(attempts==1 && !delayed);
    puts("Tailscale startup: bounded transient retries, success recovery, no auth/config/incomplete-cleanup retries or reboot loop");
}
'''
run('Tailscale transient retry limits', headers + retry_fixture + 'static void test_retry(void){' + retry + '}\n' + retry_tests)

for name in ('ml_coord.c', 'ml_wg_mgr.c'):
    source = (ROOT / 'external/microlink/components/microlink/src' / name).read_text()
    entry = source.split('void ' + name[:-2] + '_task(void *arg)', 1)[1]
    assert entry.index('ML_EVT_TASKS_READY') < entry.index('ESP_LOGI'), name
    assert 'ml_task_exiting(ml);' in entry.split('ESP_LOGI', 1)[0], name
assert 'ml->stun_public_ip == 0 || ml->stun_public_port == 0' in (ROOT / 'external/microlink/components/microlink/src/ml_coord.c').read_text()
assert 's_snapshot = heap_caps_malloc(cnt + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)' in (ROOT / 'main/log_capture.c').read_text()
print('PASS: coordinator/WG entry gates, missing STUN baseline and external-RAM boot-log snapshot guards')

coord = (ROOT / 'external/microlink/components/microlink/src/ml_coord.c').read_text()
nat = 'if (ml->stun_public_ip == 0 || ml->stun_public_port == 0)' + coord.split(
    'if (ml->stun_public_ip == 0 || ml->stun_public_port == 0)', 1)[1].split('                        parsed = true;', 1)[0]
nat_fixture = r'''
typedef struct {uint32_t stun_public_ip,stun_fallback_ip;uint16_t stun_public_port,stun_secondary_port;
    unsigned stun_retry_count;bool stun_nat_checked,nat_mapping_varies;} nat_t;
#define ML_STUN_FALLBACK_PORT 19302
static void ml_stun_send_probe_to(nat_t*m,uint32_t ip,unsigned port){(void)m;(void)ip;(void)port;}
'''
nat_tests = r'''
int main(void){
    nat_t n={.stun_public_ip=0xc0000201};
    sample(&n,0xc0000201,51820);assert(n.stun_public_port==51820 && !n.stun_nat_checked && !n.nat_mapping_varies);
    sample(&n,0xc0000201,51820);assert(n.stun_nat_checked && !n.nat_mapping_varies);
    n=(nat_t){0};sample(&n,0xc0000201,51820);sample(&n,0xc0000201,51821);
    assert(n.stun_nat_checked && n.nat_mapping_varies);
}
'''
run('Actual STUN comparison rejects zero baseline but retains valid equal/different-port detection',
    headers + nat_fixture + 'static void sample(nat_t *ml,uint32_t pub_ip,uint16_t pub_port){' + nat + '}\n' + nat_tests)

internal = (ROOT / 'external/microlink/components/microlink/include/microlink_internal.h').read_text()
allocate = 'static inline void *ml_psram_malloc' + internal.split('static inline void *ml_psram_malloc', 1)[1].split('static inline void *ml_psram_calloc', 1)[0]
allocator = 'static void *cjson_psram_malloc' + ml.split('static void *cjson_psram_malloc', 1)[1].split('/* ============================================================================', 1)[0]
json_fixture = r'''
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
typedef struct {void *(*malloc_fn)(size_t);void (*free_fn)(void*);} cJSON_Hooks;
static cJSON_Hooks installed;static unsigned hook_changes,external_attempts;static bool external_ok=true;
static void *heap_caps_malloc(size_t n,int caps){assert(caps==3 && !locks);external_attempts++;return external_ok?malloc(n):NULL;}
static void cJSON_InitHooks(cJSON_Hooks *h){assert(locks==1);installed=*h;hook_changes++;}
'''
json_tests = r'''
int main(void){
    microlink_json_memory_init();microlink_json_memory_init();assert(hook_changes==1);
    void *p=installed.malloc_fn(24);assert(p && external_attempts==1);installed.free_fn(p);
    external_ok=false;p=installed.malloc_fn(24);assert(p && external_attempts==2);installed.free_fn(p);
}
'''
run('One-time JSON allocator initialization, external allocation and internal fallback', headers + json_fixture + allocate + allocator + json_tests)
boot = (ROOT / 'main/main.c').read_text()
assert boot.index('microlink_json_memory_init();') < boot.index('ota_remote_init();') < boot.index('web_ui_init();')

wg_backend = (ROOT / 'external/microlink/components/microlink/components/wireguard_lwip/src/wireguardif.c').read_text()
endpoint = 'static void update_peer_addr' + wg_backend.split('static void update_peer_addr', 1)[1].split('/* Count contiguous', 1)[0]
endpoint_fixture = r'''
typedef uint32_t ip_addr_t;
typedef uint16_t u16_t;
struct wireguard_peer {ip_addr_t ip;u16_t port;uint32_t last_direct_rx;};
static uint32_t now;
static uint32_t wireguard_sys_now(void){return now;}
static bool ip_addr_isany(const ip_addr_t *ip){return *ip==0;}
static void ip_addr_set_any(bool ipv6,ip_addr_t *ip){(void)ipv6;*ip=0;}
#define WG_DEBUG(...) ((void)0)
'''
endpoint_tests = r'''
int main(void){
    ip_addr_t direct=0xc0000201,relay=0;struct wireguard_peer p={.ip=direct,.port=41641};
    now=1000;update_peer_addr(&p,&relay,0,false);assert(p.ip==0 && p.port==0);
    now=2000;update_peer_addr(&p,&direct,41642,false);assert(p.ip==direct && p.port==41642 && p.last_direct_rx==2000);
    now=2100;update_peer_addr(&p,&relay,0,true);assert(!p.ip && !p.port);
    now=2200;update_peer_addr(&p,&direct,41642,true);
    now=31999;update_peer_addr(&p,&relay,0,false);assert(p.ip==direct && p.port==41642);
    now=32200;update_peer_addr(&p,&relay,0,false);assert(!p.ip && !p.port && p.last_direct_rx==2200);
    now=40000;update_peer_addr(&p,&direct,41643,false);assert(p.ip==direct && p.port==41643);
    now=0xfffffff0;update_peer_addr(&p,&direct,41644,false);
    now=100;update_peer_addr(&p,&relay,0,false);assert(p.ip==direct && p.port==41644);
    now=30000;update_peer_addr(&p,&relay,0,false);assert(!p.ip && !p.port);
}
'''
run('Actual authenticated endpoint selection: relay recovery, healthy direct retention, upgrade and clock wrap',
    headers + endpoint_fixture + endpoint + endpoint_tests)
assert 'update_peer_addr(peer, addr, port, pbuf->tot_len > 0);' in wg_backend
assert 'uint32_t age = now_wg - wp->last_direct_rx;' in (
    ROOT / 'external/microlink/components/microlink/src/ml_wg_mgr.c').read_text()
