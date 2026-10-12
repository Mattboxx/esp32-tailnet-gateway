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
typedef int StaticTimer_t;
typedef void *TimerHandle_t;
static int64_t clock_us;
static unsigned allocations, mode_calls, mode_failures, deletes;
static bool fail_alloc, last_target, request_during_apply;
static void (*spawned)(void *), (*timer_callback)(TimerHandle_t), (*shutdown_callback)(void);
static int64_t esp_timer_get_time(void) {return clock_us;}
static TimerHandle_t xTimerCreateStatic(const char *n,unsigned t,int repeat,void *a,
    void(*cb)(TimerHandle_t),StaticTimer_t *storage) {
    (void)n;(void)a;assert(t==100 && repeat);timer_callback=cb;return storage;
}
static int xTimerStart(TimerHandle_t timer,unsigned delay){assert(timer && delay==portMAX_DELAY);return pdPASS;}
static int esp_register_shutdown_handler(void (*cb)(void)){shutdown_callback=cb;return ESP_OK;}
static int xTaskCreate(void(*fn)(void*),const char*n,unsigned stack,void*a,int priority,void*h) {
    (void)n;(void)a;(void)h;assert(!locks && stack==8192 && priority==5);allocations++;
    if(fail_alloc)return 0;
    assert(!spawned);spawned=fn;return pdPASS;
}
static void vTaskDelete(void *task){assert(!task && !locks);deletes++;}
'''
ap_tests = r'''
static bool apply(bool target) {
    assert(!locks);mode_calls++;last_target=target;
    if(request_during_apply){request_during_apply=false;ap_policy_request(!target);}
    if(mode_failures){mode_failures--;return false;}return true;
}
static void execute(void) {
    assert(spawned);void (*fn)(void*)=spawned;spawned=NULL;fn(NULL);
    assert(!s_active && !locks);
}
static void tick(unsigned ms){clock_us+=(int64_t)ms*1000;timer_callback(s_timer);}
int main(void) {
    assert(ap_policy_init(NULL)==ESP_ERR_INVALID_ARG);
    assert(ap_policy_init(apply)==ESP_OK);
    ap_policy_request(false);
    for(unsigned i=0;i<1000;i++)ap_policy_request(false);
    assert(!allocations && s_pending); /* never reserve 8KB during the grace period */
    tick(1499);assert(!allocations);tick(1);assert(allocations==1);
    timer_callback(s_timer);assert(allocations==1);execute();assert(!last_target && mode_calls==1);

    fail_alloc=true;ap_policy_request(true);tick(100);
    assert(allocations==2 && s_pending && !s_active);
    tick(999);assert(allocations==2);fail_alloc=false;tick(1);execute();
    assert(last_target && mode_calls==2 && !s_pending);

    mode_failures=1;ap_policy_request(false);tick(1500);execute();
    assert(s_pending);tick(1000);execute();assert(!s_pending && !last_target);

    /* A new request arriving during apply must survive the older completion. */
    request_during_apply=true;ap_policy_request(true);tick(100);execute();
    assert(s_pending && last_target);tick(1500);execute();assert(!last_target && !s_pending);
    /* Replace an already queued transition before the worker gets CPU time. */
    ap_policy_request(true);tick(100);ap_policy_request(false);execute();
    assert(s_pending);tick(1500);execute();assert(!last_target);

    ap_policy_request(true);tick(100);unsigned before=mode_calls;
    shutdown_callback();ap_policy_request(true);execute();tick(10000);
    assert(ap_policy_is_shutdown() && mode_calls==before && !s_pending && !spawned);
    puts("AP recovery: grace/coalescing, allocation and mode-failure retries, latest-generation races and shutdown suppression");
}
'''
run('AP allocation-failure recovery without duplicate/delayed worker stacks', headers + ap_fixture + ap_source + ap_tests)

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
static const char *expected[]={"ml_wg_mgr","ml_net_io","ml_derp_tx","ml_derp_rx","ml_coord"};
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
    puts("Microlink startup: WG stack reserved first, coord last, ready barrier and rollback at all five allocation points; incomplete cleanup is not retryable");
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
