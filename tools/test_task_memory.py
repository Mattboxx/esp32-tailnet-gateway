"""Actual SDK MQTT startup / teardown and project startup-task behavior tests.

Host allocator/RTOS fixtures, NOT hardware fragmentation or full MQTT testing.
MQTT_SOURCE selects the reviewed ESP-IDF 5.5.3 source. TASKMEM_SANITIZE=1 adds
Linux ASan/UBSan. No device access, downloads or SDK modifications.
"""
from pathlib import Path
import hashlib
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK_HASH = '3e558fa88e7bd98d4342bd19fe6d99c56031d04ff7a26405ab1bcd09408cf6f3'
sdk_path = Path(os.environ.get('MQTT_SOURCE', str(Path.home() /
    '.platformio/packages/framework-espidf@3.50503.0/components/mqtt/esp-mqtt/mqtt_client.c')))
sdk_bytes = sdk_path.read_bytes()
assert hashlib.sha256(sdk_bytes).hexdigest() == SDK_HASH, 'Unreviewed MQTT source'
sdk = sdk_bytes.decode('utf-8')
sdk_start = 'esp_err_t esp_mqtt_client_start(' + sdk.split(
    'esp_err_t esp_mqtt_client_start(', 1)[1].split('\nesp_err_t esp_mqtt_client_disconnect', 1)[0]
# Use the actual worker's teardown statements, including the paired delete.
sdk_cleanup = 'static void worker_cleanup(esp_mqtt_client_handle_t client) {\n' + (
    '    client->state = MQTT_STATE_DISCONNECTED;' + sdk.split(
        '\nesp_err_t esp_mqtt_client_start', 1)[0].rsplit(
        '    client->state = MQTT_STATE_DISCONNECTED;', 1)[1])

HEADER = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *);
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define pdPASS 1
#define pdTRUE 1
#define MALLOC_CAP_SPIRAM 0x400
#define MALLOC_CAP_8BIT 0x4
#define portMAX_DELAY 0xffffffffu
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
static int locks, allocations, caps_calls, normal_calls, pinned_calls;
static int deletes, caps_deletes, mutex_calls, config_loads;
static bool oom, mutex_oom;
static unsigned largest_internal = 3456;
static void *s_lock;
static void check_create(TaskFunction_t fn, const char *name, unsigned size,
                         void *arg, unsigned priority, TaskHandle_t *out) {
    (void)arg;(void)priority;assert(fn && name && size >= 4096);
    allocations++; if(out) *out = NULL;
}
static int xTaskCreate(TaskFunction_t fn,const char *name,unsigned size,void *arg,
                       unsigned priority,TaskHandle_t *out) {
    check_create(fn,name,size,arg,priority,out);normal_calls++;
    if(oom || size>largest_internal)return 0;
    if(out)*out=(void*)1;return pdPASS;
}
static int xTaskCreatePinnedToCore(TaskFunction_t fn,const char *name,unsigned size,
                                  void *arg,unsigned priority,TaskHandle_t *out,int core) {
    assert(core==1);pinned_calls++;return xTaskCreate(fn,name,size,arg,priority,out);
}
static int xTaskCreateWithCaps(TaskFunction_t fn,const char *name,unsigned size,void *arg,
                               unsigned priority,TaskHandle_t *out,unsigned caps) {
    check_create(fn,name,size,arg,priority,out);caps_calls++;
    assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if(oom)return 0; /* includes internal TCB or external-stack OOM */
    if(out)*out=(void*)1;return pdPASS;
}
static int xTaskCreatePinnedToCoreWithCaps(TaskFunction_t fn,const char *name,unsigned size,
                   void *arg,unsigned priority,TaskHandle_t *out,int core,unsigned caps) {
    assert(core==1);pinned_calls++;
    return xTaskCreateWithCaps(fn,name,size,arg,priority,out,caps);
}
static void vTaskDelete(void *task){assert(!task);deletes++;}
static void vTaskDeleteWithCaps(void *task){assert(!task);caps_deletes++;}
/* Project reaper: self-deletion without an exit-time internal allocation. */
static int reaper_deletes;
void task_reaper_delete(void *task){assert(!task);reaper_deletes++;}
static void task_reaper_self_delete(void){reaper_deletes++;}
static void *xSemaphoreCreateMutex(void){mutex_calls++;return mutex_oom?NULL:(void*)2;}
static void xSemaphoreTake(void *mutex,unsigned delay){assert(mutex==s_lock&&delay==portMAX_DELAY&&!locks);locks++;}
static void xSemaphoreGive(void *mutex){assert(mutex==s_lock&&locks==1);locks--;}
static void load_config(void){assert(locks==1);config_loads++;}
#define taskENTER_CRITICAL(m) do{(void)(m);assert(!locks);locks++;}while(0)
#define taskEXIT_CRITICAL(m) do{(void)(m);assert(locks==1);locks--;}while(0)
'''

MQTT_FIXTURE = r'''
enum {MQTT_STATE_INIT, MQTT_STATE_DISCONNECTED, MQTT_STATE_CONNECTED};
typedef struct {unsigned task_stack,task_prio;} config_t;
typedef struct {config_t *config;int state,status_bits;TaskHandle_t task_handle;} mqtt_client_t;
typedef mqtt_client_t *esp_mqtt_client_handle_t;
#define MQTT_TASK_CORE 1
#define MQTT_API_LOCK(c) do{assert((c)&&!locks);locks++;}while(0)
#define MQTT_API_UNLOCK(c) do{assert((c)&&locks==1);locks--;}while(0)
#define STOPPED_BIT 1
static void xEventGroupSetBits(int bits,int flag){assert(bits==4&&flag==STOPPED_BIT);}
static void esp_mqtt_task(void *arg){(void)arg;}
'''
MQTT_TEST = r'''
int main(void){
    config_t config={.task_stack=6144,.task_prio=5};
    mqtt_client_t storage={&config,MQTT_STATE_INIT,4,NULL};
    esp_mqtt_client_handle_t client=&storage;
    assert(esp_mqtt_client_start(NULL)==ESP_ERR_INVALID_ARG && !allocations);
    client->state=MQTT_STATE_CONNECTED;
    assert(esp_mqtt_client_start(client)==ESP_FAIL&&!allocations&&!locks);
    client->state=MQTT_STATE_INIT;oom=true;
    assert(esp_mqtt_client_start(client)==ESP_FAIL&&!client->task_handle&&!locks);
    oom=false;
#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    assert(esp_mqtt_client_start(client)==ESP_OK&&client->task_handle&&!locks);
    assert(caps_calls==2&&!normal_calls); /* succeeds with only 3456 internal */
#else
    assert(esp_mqtt_client_start(client)==ESP_FAIL&&!client->task_handle&&!locks);
    largest_internal=8192;
    assert(esp_mqtt_client_start(client)==ESP_OK&&normal_calls==3&&!caps_calls);
#endif
    worker_cleanup(client);
    assert(client->state==MQTT_STATE_DISCONNECTED);
#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    assert(reaper_deletes==1&&!caps_deletes&&!deletes); /* never the SDK self-delete */
#else
    assert(deletes==1&&!caps_deletes);
#endif
    /* The real SDK supports start again after a completed stop. */
    assert(esp_mqtt_client_start(client)==ESP_OK&&!locks);
    assert(pinned_calls==(MQTT_CORE_SELECTION_ENABLED?allocations:0));
    puts("PASS: pinned SDK MQTT start/stop, fragmented internal memory, OOM and core selection (host fixtures)");
}
'''

manager_source = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
manager_budget = next(line for line in manager_source.splitlines()
                      if line.startswith('#define MQTT_MANAGER_STACK_BYTES ')) + '\n'
manager_init = 'void mqtt_integration_init(void)' + manager_source.split(
    'void mqtt_integration_init(void)', 1)[1].split('\nvoid mqtt_integration_get_config', 1)[0]
tail_source = (ROOT / 'main/tailscale_manager.c').read_text(encoding='utf-8')
tail_start = 'esp_err_t tailscale_request_connect(void)' + tail_source.split(
    'esp_err_t tailscale_request_connect(void)', 1)[1].split('\nstatic void tailscale_connect_task(void *pvParameters)\n', 1)[0]
tail_cleanup = 'static void startup_cleanup(void) {\n' + tail_source.rsplit(
    '    taskENTER_CRITICAL(&s_connect_lock);', 1)[1]
tail_cleanup = tail_cleanup.replace('static void startup_cleanup(void) {\n',
    'static void startup_cleanup(void) {\n    taskENTER_CRITICAL(&s_connect_lock);', 1)
PROJECT_FIXTURE = r'''
static bool tailscale_enabled, s_connect_in_flight, s_instance_ready;
static int s_connect_lock;
static TaskHandle_t s_manager_task;
static void tailscale_connect_task(void *arg){(void)arg;}
static void manager_task(void *arg){(void)arg;}
'''
PROJECT_TEST = r'''
int main(void){
    assert(tailscale_request_connect()==ESP_OK&&!allocations);
    tailscale_enabled=true;oom=true;
    assert(tailscale_request_connect()==ESP_ERR_NO_MEM&&!s_connect_in_flight&&!locks);
    oom=false;assert(tailscale_request_connect()==ESP_OK&&s_connect_in_flight);
    int before=allocations;
    for(int i=0;i<1000;i++)assert(tailscale_request_connect()==ESP_OK);
    assert(allocations==before); /* duplicate GOT_IP never allocates */
    startup_cleanup();assert(!s_connect_in_flight&&reaper_deletes==1&&!caps_deletes);
    assert(tailscale_request_connect()==ESP_OK&&s_connect_in_flight); /* retry */
    s_instance_ready=true;startup_cleanup();before=allocations;
    for(int i=0;i<1000;i++)assert(tailscale_request_connect()==ESP_OK);
    assert(allocations==before&&!s_connect_in_flight);
    mutex_oom=true;mqtt_integration_init();assert(!s_manager_task&&!s_lock);
    mutex_oom=false;oom=true;mqtt_integration_init();assert(!s_manager_task&&s_lock&&!locks);
    oom=false;mqtt_integration_init();assert(s_manager_task&&!locks&&config_loads==2);
    before=allocations;mqtt_integration_init();assert(before==allocations);
    assert(!normal_calls&&caps_calls==allocations);
    puts("PASS: actual project task launchers: allocation failure, retry, 2000 coalesced IP events, matching cleanup and manager initialization (host fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='task-memory-') as directory:
    path = Path(directory)
    (path / 'freertos').mkdir()
    for name in ('sdkconfig.h', 'freertos/FreeRTOS.h', 'freertos/task.h',
                 'freertos/idf_additions.h', 'esp_heap_caps.h'):
        (path / name).write_text('#pragma once\n', encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
             '-Wno-unused-variable', '-Wno-misleading-indentation', '-I', str(path), '-I', str(ROOT / 'main')]
    if os.environ.get('TASKMEM_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    cases = [('project', HEADER + PROJECT_FIXTURE + manager_budget + manager_init + tail_start + tail_cleanup + PROJECT_TEST)]
    for external in (0, 1):
        for pinned in (0, 1):
            cases.append((f'mqtt-{external}-{pinned}', HEADER +
                f'\n#define CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY {external}\n#define MQTT_CORE_SELECTION_ENABLED {pinned}\n' +
                '#include "mqtt_task_memory.h"\n' + MQTT_FIXTURE + sdk_start + sdk_cleanup + MQTT_TEST))
    for stem, program in cases:
        c = path / (stem + '.c'); c.write_text(program, encoding='utf-8')
        binary = path / (stem + ('.exe' if os.name == 'nt' else ''))
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
