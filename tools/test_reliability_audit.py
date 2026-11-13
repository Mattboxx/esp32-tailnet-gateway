"""Exercise firmware startup, restart, monitor, ntfy and mDNS with host fakes."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / 'main' / name).read_text(encoding='utf-8')


def extract(src, signature):
    start = src.index(signature + '\n{')
    begin = src.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (src[end] == '{') - (src[end] == '}')
        end += 1
    return src[start:end]


core = source('main.c')
web = source('web_ui.c')
ops = source('homelab_ops.c')
ntfy = source('ntfy_integration.c')
mdns = source('lan_name.c')

program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM -2
#define ESP_ERR_INVALID_RESPONSE -3
#define ESP_OTA_IMG_PENDING_VERIFY 1
#define ESP_LOGE(tag, ...) do { if (false) printf(__VA_ARGS__); } while (0)
#define ESP_LOGI(tag, ...) ((void)0)
#define ESP_LOGW(tag, ...) ((void)0)
#define esp_err_to_name(error) ((void)(error), "error")
#define pdMS_TO_TICKS(ms) (ms)
#define LOCK() ((void)0)
#define UNLOCK() ((void)0)
#define portMAX_DELAY 0
#define eSetValueWithOverwrite 0
#define pdPASS 1
typedef int esp_err_t;
typedef int esp_ota_img_states_t;
typedef int esp_partition_t;
static bool partition = true, state_ok = true, can_rollback = true;
static int state = ESP_OTA_IMG_PENDING_VERIFY;
static unsigned elapsed, confirmed, rolled_back;
static const esp_partition_t slot;
static const esp_partition_t *esp_ota_get_running_partition(void) { return partition ? &slot : NULL; }
static int esp_ota_get_state_partition(const esp_partition_t *p, int *out) {
    assert(p == &slot); *out = state; return state_ok ? ESP_OK : ESP_FAIL;
}
static bool esp_ota_check_rollback_is_possible(void) { return can_rollback; }
static int esp_ota_mark_app_invalid_rollback_and_reboot(void) { rolled_back++; return ESP_FAIL; }
static int esp_ota_mark_app_valid_cancel_rollback(void) { confirmed++; return ESP_OK; }
static void vTaskDelay(unsigned ms) { elapsed += ms; }

typedef int httpd_req_t;
typedef int *TaskHandle_t;
enum { WEB_RESTART_CANCEL = 1, WEB_RESTART_COMMIT };
static bool authed = true, can_reserve = true;
static int last_command, writes, status, ota_result;
static int require_password_session(httpd_req_t *req) { (void)req; return authed ? ESP_OK : ESP_FAIL; }
static int ota_upload_handler(httpd_req_t *req) { (void)req; writes++; return ota_result; }
static void httpd_resp_set_status(httpd_req_t *req, const char *text) { (void)req; status = !strncmp(text, "503", 3); }
static void httpd_resp_sendstr(httpd_req_t *req, const char *text) { (void)req; (void)text; }
static void delayed_restart_task(void *arg) { (void)arg; }
static int xTaskCreate(void (*fn)(void *), const char *name, unsigned bytes, void *arg, unsigned priority, TaskHandle_t *out) {
    (void)name; (void)bytes; (void)arg; (void)priority;
    assert(fn == delayed_restart_task);
    if (!can_reserve) return 0;
    *out = &last_command;
    return pdPASS;
}
static void xTaskNotify(TaskHandle_t task, int value, int mode) { (void)mode; *task = value; }

enum { J_PRECHECK=1, J_CANCELLED, J_UNKNOWN, J_TIMEOUT, J_SERVICE, J_REACHABLE, J_WAKE, J_WAIT };
typedef struct { uint8_t mac[6]; bool monitor; int interval_s, timeout_s, service_port; } ops_device_t;
typedef struct { uint8_t mac[6]; } wol_device_t;
typedef struct { bool monitoring; int interval_s; } ops_settings_t;
typedef struct {
    unsigned id; int index, state, origin, checks; uint64_t started, deadline, next;
    bool cancel, probe_valid, host_seen, service_seen, wake, manual, packet_sent;
    wol_device_t device; ops_device_t profile;
} job_t;
typedef struct { uint8_t mac[6]; uint64_t observed_ms; uint32_t latency_ms; } result_t;
static struct { ops_settings_t settings; } store = {{true, 60}};
static unsigned job_seq, monitor_index;
static uint64_t next_monitor;
static job_t job;
static result_t results[12];
static unsigned enabled = 1 << 11;
static bool admit = true;
static int wol_count(void) { return 12; }
static bool homelab_ops_device(int i, ops_device_t *out) {
    *out = (ops_device_t){.mac={(uint8_t)i}, .monitor=(enabled & (1u << i)) != 0, .interval_s=60, .timeout_s=5};
    return true;
}
static bool wol_get(int i, wol_device_t *out) { *out = (wol_device_t){{(uint8_t)i}}; return true; }
static bool homelab_ops_admit(void) { return admit; }
static uint64_t clock_ms;
static uint64_t now_ms(void) { return clock_ms; }
static void finish_locked(int state) { job.state=state; }
static bool recovery_allowed_locked(int origin) { (void)origin; return true; }
static bool active(int state) { return state != 0; }
static void finish(void) {
    results[job.index].observed_ms = job.started;
    memcpy(results[job.index].mac, job.device.mac, sizeof job.device.mac);
    job.state = 0;
}

#define EXT_RAM_BSS_ATTR
#define NTFY_NOINLINE
#define HIST_EV_SERVICE 0
#define HIST_INFO 0
#define xSemaphoreTake(lock, time) ((void)0)
#define xSemaphoreGive(lock) ((void)0)
typedef struct { bool enabled; } ntfy_integration_config_t;
static ntfy_integration_config_t s_config = {true};
static struct { unsigned operational_dropped; } s_status;
static uint64_t s_config_generation, time_ms;
static bool s_lock = true;
static unsigned history_count, attempts;
static int send_result;
static char sent[160];
static uint64_t esp_timer_get_time(void) { return time_ms * 1000; }
static void history_event(int event, int level, const char *fmt, const char *message) {
    (void)event; (void)level; (void)fmt; (void)message; history_count++;
}
static void strlcpy(char *out, const char *in, size_t size) { snprintf(out, size, "%s", in); }
static int publish_message(const ntfy_integration_config_t *config, const char *title, const char *tags, const char *text) {
    assert(config->enabled); (void)title; (void)tags; attempts++;
    strlcpy(sent, text, sizeof sent); return send_result;
}

typedef uint32_t ip4_addr_t;
struct netif { ip4_addr_t ip; bool up; };
typedef struct netif esp_netif_t;
static struct netif sta = {1, true}, ap = {2, true};
static struct netif *s_advertising;
static ip4_addr_t s_advertised_ipv4;
static bool s_initialized;
static char s_name[] = "test-node";
static unsigned probes, added, removed;
#define ERR_OK 0
#define netif_is_up(nif) ((nif)->up)
#define netif_ip4_addr(nif) (&(nif)->ip)
#define ip4_addr_isany(ip) (*(ip) == 0)
#define ip4_addr_cmp(left, right) (*(left) == *(right))
#define ip4_addr_copy(dst, src) ((dst) = (src))
static esp_netif_t *eth_uplink_service_netif(void) { return &sta; }
static struct netif *esp_netif_get_netif_impl(esp_netif_t *nif) { return nif; }
static esp_netif_t *esp_netif_get_handle_from_ifkey(const char *key) { (void)key; return &ap; }
static void mdns_resp_restart(struct netif *nif) { assert(nif == s_advertising); probes++; }
static void mdns_resp_remove_netif(struct netif *nif) { assert(nif == s_advertising); removed++; }
static void mdns_resp_init(void) { assert(!s_initialized); }
static void name_result(void) {}
static void mdns_resp_register_name_result_cb(void (*fn)(void)) { assert(fn == name_result); }
static int mdns_resp_add_netif(struct netif *nif, const char *name) {
    assert(nif && name == s_name); added++; return ERR_OK;
}
'''
program += '\n'.join([
    extract(core, 'static void confirm_ota_startup(esp_err_t admin_start)'),
    extract(web, 'static esp_err_t reserve_restart(httpd_req_t *req, TaskHandle_t *task)'),
    extract(web, 'static esp_err_t system_ota_upload_handler(httpd_req_t *req)'),
    extract(ops, 'static void apply_probe_locked(const job_t *local, int result, uint32_t latency)'),
    extract(ops, 'static void schedule_monitor(uint64_t now, const ops_settings_t *settings)'),
    ntfy[ntfy.index('#define NTFY_OPERATIONAL_CAPACITY'):ntfy.index('/* TLS certificate verification')],
    extract(ntfy, 'static NTFY_NOINLINE void operational_tick(const ntfy_integration_config_t *c,\n'
                  '                                            uint64_t generation, bool online)'),
    extract(mdns, 'static void mdns_on_uplink(void *arg)'),
])
program += r'''
int main(void)
{
    partition = false;
    confirm_ota_startup(ESP_FAIL);
    partition = true;
    state_ok = false;
    confirm_ota_startup(ESP_OK);
    state_ok = true;
    can_rollback = false;
    confirm_ota_startup(ESP_FAIL);
    assert(!rolled_back && !elapsed && !confirmed);
    can_rollback = true;
    confirm_ota_startup(ESP_FAIL);
    assert(rolled_back == 1 && !elapsed && !confirmed);
    state = 2;
    confirm_ota_startup(ESP_OK);
    assert(!elapsed && !confirmed);
    state = ESP_OTA_IMG_PENDING_VERIFY;
    confirm_ota_startup(ESP_OK);
    assert(elapsed == 20000 && confirmed == 1);

    httpd_req_t req = 0;
    authed = false;
    assert(system_ota_upload_handler(&req) == ESP_FAIL && !writes && !status);
    authed = true;
    can_reserve = false;
    assert(system_ota_upload_handler(&req) == ESP_FAIL && !writes && status);
    can_reserve = true;
    ota_result = ESP_FAIL;
    assert(system_ota_upload_handler(&req) == ESP_FAIL && writes == 1 && last_command == WEB_RESTART_CANCEL);
    ota_result = ESP_OK;
    assert(system_ota_upload_handler(&req) == ESP_OK && writes == 2 && last_command == WEB_RESTART_COMMIT);

    schedule_monitor(1000, &store.settings);
    assert(job.id == 1 && job.index == 11);
    finish();
    schedule_monitor(60999, &store.settings);
    assert(job.id == 1);
    schedule_monitor(61000, &store.settings);
    assert(job.id == 2 && job.index == 11);
    finish();
    enabled |= 1u;
    admit = false;
    schedule_monitor(121000, &store.settings);
    assert(job.id == 2);
    admit = true;
    schedule_monitor(122000, &store.settings);
    assert(job.id == 3 && job.index == 0);
    finish();
    schedule_monitor(182000, &store.settings);
    assert(job.id == 4 && job.index == 11);

    clock_ms = 3000;
    job = (job_t){.id=1,.deadline=3000,.state=J_PRECHECK};
    job_t local = job;
    apply_probe_locked(&local, 1, 1);
    assert(job.state == J_REACHABLE && job.host_seen);
    job = (job_t){.id=1,.deadline=3000,.state=J_SERVICE,.host_seen=true};
    local = job;
    apply_probe_locked(&local, 0, 1);
    assert(job.state == J_TIMEOUT && job.host_seen && !job.service_seen);
    job = local;
    apply_probe_locked(&local, -1, 1);
    assert(job.state == J_UNKNOWN);
    job = local;
    job.cancel = true;
    apply_probe_locked(&local, 1, 1);
    assert(job.state == J_CANCELLED);
    assert(ntfy_integration_queue_event("one"));
    assert(ntfy_integration_queue_event("two"));
    send_result = ESP_FAIL;
    operational_tick(&s_config, 0, false);
    assert(!attempts);
    operational_tick(&s_config, 0, true);
    assert(attempts == 1 && !strcmp(sent, "one"));
    time_ms = 4999;
    operational_tick(&s_config, 0, true);
    assert(attempts == 1);
    time_ms = 5000;
    send_result = ESP_OK;
    operational_tick(&s_config, 0, true);
    assert(attempts == 2 && !strcmp(sent, "one") && s_operational_count == 1);
    operational_tick(&s_config, 0, true);
    assert(attempts == 3 && !strcmp(sent, "two") && !s_operational_count && history_count == 2);
    assert(ntfy_integration_queue_event("permanent"));
    send_result = ESP_ERR_INVALID_RESPONSE;
    operational_tick(&s_config, 0, true);
    assert(attempts == 4 && !s_operational_count && s_status.operational_dropped == 1);
    for (int i = 0; i < NTFY_OPERATIONAL_CAPACITY; i++) assert(ntfy_integration_queue_event("offline"));
    assert(!ntfy_integration_queue_event("full"));
    time_ms += NTFY_OPERATIONAL_TTL_MS;
    operational_tick(&s_config, 0, false);
    assert(!s_operational_count && s_status.operational_dropped == NTFY_OPERATIONAL_CAPACITY + 2);
    assert(ntfy_integration_queue_event("new settings"));
    s_config_generation++;
    operational_tick(&s_config, 0, true);
    assert(attempts == 4);

    mdns_on_uplink(NULL);
    mdns_on_uplink(NULL);
    assert(added == 1 && !probes && !removed);
    sta.ip = 3;
    mdns_on_uplink(NULL);
    mdns_on_uplink(NULL);
    assert(added == 1 && probes == 1 && !removed);
    sta.up = false;
    mdns_on_uplink(NULL);
    assert(added == 2 && probes == 1 && removed == 1 && s_advertising == &ap);
    sta.up = true;
    mdns_on_uplink(NULL);
    assert(added == 3 && probes == 1 && removed == 2 && s_advertising == &sta);
    puts("PASS: OTA reservation and health gate, fair Recovery cadence, ntfy queue and mDNS transition");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='reliability-') as work:
    source_file = Path(work) / 'test.c'
    executable = Path(work) / ('test.exe' if os.name == 'nt' else 'test')
    source_file.write_text(program, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('RELIABILITY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(source_file), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
