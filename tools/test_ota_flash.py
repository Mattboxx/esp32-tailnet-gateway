"""Actual ota_flash.c with a pthread RTOS/SDK model, NOT a cache/hardware test.

Checks the execution domain, synchronous buffer lifetime, single mailbox,
concurrent callers, errors, admission timeout and consumed-handle cleanup.
OTAFLASH_SANITIZE=1 enables Linux ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'main/ota_flash.c').read_text(encoding='utf-8')
FIXTURE = r'''
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sched.h>
typedef int esp_err_t;
typedef unsigned TickType_t;
typedef unsigned char StackType_t;
typedef void (*TaskFunction_t)(void *);
typedef struct { pthread_t thread; pthread_mutex_t lock; pthread_cond_t changed;
    unsigned notifications; bool stop; TaskFunction_t function; } StaticTask_t;
typedef StaticTask_t *TaskHandle_t;
typedef struct { pthread_mutex_t lock; pthread_cond_t changed; bool valid; unsigned count; } StaticSemaphore_t;
typedef StaticSemaphore_t *SemaphoreHandle_t;
typedef struct { unsigned size; } esp_partition_t;
typedef unsigned esp_ota_handle_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE 1
#define ESP_ERR_INVALID_ARG 2
#define ESP_ERR_NO_MEM 3
#define ESP_ERR_TIMEOUT 4
#define ESP_ERR_NOT_FOUND 5
#define DRAM_ATTR
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY 0xffffffffU
static _Thread_local TaskHandle_t current_task;
static _Thread_local bool reject_admission;
static atomic_bool wrong_stack, hold_write, write_started;
static atomic_uint active, sdk_calls, write_calls, boot_calls, restart_calls;
static atomic_int injected_error;
static bool fail_create, no_partition;
static unsigned creates;
static const esp_partition_t partition = {0x400000};
static SemaphoreHandle_t make_sem(StaticSemaphore_t *s, unsigned count) {
    if (!s->valid) { assert(!pthread_mutex_init(&s->lock,NULL));
        assert(!pthread_cond_init(&s->changed,NULL)); s->valid=true; }
    s->count=count; return s;
}
static SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *s) { return make_sem(s,1); }
static SemaphoreHandle_t xSemaphoreCreateBinaryStatic(StaticSemaphore_t *s) { return make_sem(s,0); }
static int xSemaphoreTake(SemaphoreHandle_t s, TickType_t wait) {
    if (reject_admission && wait!=portMAX_DELAY) return 0;
    assert(!pthread_mutex_lock(&s->lock));
    while (!s->count) assert(!pthread_cond_wait(&s->changed,&s->lock));
    --s->count; assert(!pthread_mutex_unlock(&s->lock)); return pdTRUE;
}
static int xSemaphoreGive(SemaphoreHandle_t s) {
    assert(!pthread_mutex_lock(&s->lock)); assert(s->count==0); s->count=1;
    assert(!pthread_cond_signal(&s->changed)); assert(!pthread_mutex_unlock(&s->lock)); return pdTRUE;
}
static TaskHandle_t xTaskGetCurrentTaskHandle(void) { return current_task; }
static void *esp_cpu_get_sp(void) { return current_task; }
static bool esp_ptr_in_dram(const void *sp) { return sp && !atomic_load(&wrong_stack); }
static void *entry(void *p) { current_task=p; current_task->function(NULL); return NULL; }
static TaskHandle_t xTaskCreateStatic(TaskFunction_t fn, const char *name, unsigned bytes,
    void *arg, unsigned priority, StackType_t *stack, StaticTask_t *tcb) {
    assert(!strcmp(name,"ota_flash") && bytes==4096 && !arg && priority==4);
    assert(stack && !((uintptr_t)stack%16) && tcb); creates++;
    if (fail_create) return NULL;
    memset(tcb,0,sizeof *tcb); tcb->function=fn;
    assert(!pthread_mutex_init(&tcb->lock,NULL)); assert(!pthread_cond_init(&tcb->changed,NULL));
    assert(!pthread_create(&tcb->thread,NULL,entry,tcb)); return tcb;
}
static void xTaskNotifyGive(TaskHandle_t task) {
    assert(!pthread_mutex_lock(&task->lock)); task->notifications++;
    assert(!pthread_cond_signal(&task->changed)); assert(!pthread_mutex_unlock(&task->lock));
}
static unsigned ulTaskNotifyTake(int clear, TickType_t wait) {
    TaskHandle_t t=current_task; assert(t && clear==pdTRUE && wait==portMAX_DELAY);
    assert(!pthread_mutex_lock(&t->lock));
    while (!t->notifications && !t->stop) assert(!pthread_cond_wait(&t->changed,&t->lock));
    if (t->stop) { assert(!pthread_mutex_unlock(&t->lock)); pthread_exit(NULL); }
    unsigned n=t->notifications; t->notifications=0;
    assert(!pthread_mutex_unlock(&t->lock)); return n;
}
static void sdk_enter(void) {
    assert(current_task && esp_ptr_in_dram(esp_cpu_get_sp()));
    assert(atomic_fetch_add(&active,1)==0); atomic_fetch_add(&sdk_calls,1);
}
static esp_err_t sdk_leave(void) { assert(atomic_fetch_sub(&active,1)==1); return atomic_load(&injected_error); }
static const esp_partition_t *esp_ota_get_next_update_partition(const void *p) {
    assert(!p); sdk_enter(); sdk_leave(); return no_partition ? NULL : &partition;
}
static esp_err_t esp_ota_begin(const esp_partition_t *p, size_t size, esp_ota_handle_t *h) {
    sdk_enter(); assert(p==&partition && size==128 && h); esp_err_t e=sdk_leave(); if (!e) *h=42; return e;
}
static esp_err_t esp_ota_write(esp_ota_handle_t h, const void *data, size_t size) {
    sdk_enter(); assert(h==42 && size==4 && !memcmp(data,"OTA!",4));
    atomic_fetch_add(&write_calls,1); atomic_store(&write_started,true);
    while (atomic_load(&hold_write)) sched_yield();
    /* Buffer remains owned and unmodified until the synchronous ACK. */
    assert(!memcmp(data,"OTA!",4)); return sdk_leave();
}
static esp_err_t esp_ota_end(esp_ota_handle_t h) { sdk_enter(); assert(h==42); return sdk_leave(); }
static esp_err_t esp_ota_abort(esp_ota_handle_t h) { sdk_enter(); assert(h==42); return sdk_leave(); }
static esp_err_t esp_ota_set_boot_partition(const esp_partition_t *p) {
    sdk_enter(); assert(p==&partition); atomic_fetch_add(&boot_calls,1); return sdk_leave();
}
static void esp_restart(void) { sdk_enter(); atomic_fetch_add(&restart_calls,1); sdk_leave(); }
'''
TEST = r'''
typedef struct { atomic_bool done; esp_err_t result; } writer_t;
static void *write_thread(void *arg) {
    writer_t *w=arg; char buffer[4]={'O','T','A','!'};
    w->result=ota_flash_write(42,buffer,sizeof buffer);
    memset(buffer,0,sizeof buffer); atomic_store(&w->done,true); return NULL;
}
int main(void) {
    esp_ota_handle_t handle=99;
    assert(!ota_flash_next_partition());
    assert(ota_flash_begin(&partition,128,&handle)==ESP_ERR_INVALID_STATE && !handle);
    assert(!atomic_load(&sdk_calls));
    fail_create=true; assert(ota_flash_init()==ESP_ERR_NO_MEM);
    assert(ota_flash_write(42,"OTA!",4)==ESP_ERR_INVALID_STATE);
    fail_create=false; assert(ota_flash_init()==ESP_OK && creates==2);
    assert(ota_flash_init()==ESP_OK && creates==2);
    assert(ota_flash_next_partition()==&partition);
    no_partition=true; assert(!ota_flash_next_partition()); no_partition=false;
    assert(ota_flash_begin(NULL,128,&handle)==ESP_ERR_INVALID_ARG);
    assert(ota_flash_begin(&partition,128,NULL)==ESP_ERR_INVALID_ARG);
    assert(ota_flash_write(42,NULL,4)==ESP_ERR_INVALID_ARG);
    assert(ota_flash_write(42,"OTA!",0)==ESP_ERR_INVALID_ARG);
    assert(ota_flash_set_boot_partition(NULL)==ESP_ERR_INVALID_ARG);
    assert(ota_flash_begin(&partition,128,&handle)==ESP_OK && handle==42);
    assert(ota_flash_write(handle,"OTA!",4)==ESP_OK);
    assert(ota_flash_end(handle)==ESP_OK);
    assert(ota_flash_abort(handle)==ESP_OK);
    assert(ota_flash_set_boot_partition(&partition)==ESP_OK);
    ota_flash_restart(); assert(atomic_load(&restart_calls)==1);
    atomic_store(&injected_error,77); handle=99;
    assert(ota_flash_begin(&partition,128,&handle)==77 && !handle);
    assert(ota_flash_write(42,"OTA!",4)==77);
    assert(ota_flash_end(42)==77 && ota_flash_abort(42)==77);
    assert(ota_flash_set_boot_partition(&partition)==77);
    atomic_store(&injected_error,0);
    unsigned before=atomic_load(&sdk_calls);
    atomic_store(&wrong_stack,true);
    assert(!ota_flash_next_partition());
    assert(ota_flash_begin(&partition,128,&handle)==ESP_ERR_INVALID_STATE);
    assert(ota_flash_write(42,"OTA!",4)==ESP_ERR_INVALID_STATE);
    assert(ota_flash_end(42)==ESP_ERR_INVALID_STATE && ota_flash_abort(42)==ESP_ERR_INVALID_STATE);
    assert(ota_flash_set_boot_partition(&partition)==ESP_ERR_INVALID_STATE);
    ota_flash_restart(); assert(atomic_load(&sdk_calls)==before); /* never caller fallback */
    atomic_store(&wrong_stack,false);
    reject_admission=true;
    assert(ota_flash_write(42,"OTA!",4)==ESP_ERR_TIMEOUT);
    assert(ota_flash_begin(&partition,128,&handle)==ESP_ERR_TIMEOUT && !handle);
    assert(atomic_load(&sdk_calls)==before);
    assert(ota_flash_end(42)==ESP_OK && ota_flash_abort(42)==ESP_OK); /* cleanup cannot be dropped */
    reject_admission=false;
    TaskHandle_t save=current_task; current_task=s_task;
    assert(ota_flash_end(42)==ESP_ERR_INVALID_STATE); /* no self-dispatch deadlock */
    current_task=save;
    atomic_store(&hold_write,true); atomic_store(&write_started,false);
    writer_t first={0},second={0}; pthread_t a,b;
    assert(!pthread_create(&a,NULL,write_thread,&first));
    while (!atomic_load(&write_started)) sched_yield();
    assert(!atomic_load(&first.done));
    assert(!pthread_create(&b,NULL,write_thread,&second));
    atomic_store(&hold_write,false);
    assert(!pthread_join(a,NULL) && !pthread_join(b,NULL));
    assert(atomic_load(&first.done) && atomic_load(&second.done));
    assert(first.result==ESP_OK && second.result==ESP_OK && !atomic_load(&active));
    assert(!pthread_mutex_lock(&s_task->lock)); s_task->stop=true;
    assert(!pthread_cond_signal(&s_task->changed)); assert(!pthread_mutex_unlock(&s_task->lock));
    assert(!pthread_join(s_task->thread,NULL));
    puts("PASS: actual OTA flash executor domain, lifetime, concurrency, errors and cleanup (host RTOS model)");
}
'''

with tempfile.TemporaryDirectory(prefix='ota-flash-') as directory:
    path = Path(directory)
    (path / 'freertos').mkdir()
    for name in ('esp_ota_ops.h', 'esp_attr.h', 'esp_cpu.h', 'esp_memory_utils.h',
                 'esp_system.h', 'freertos/FreeRTOS.h', 'freertos/task.h', 'freertos/semphr.h'):
        (path / name).write_text('#pragma once\n', encoding='utf-8')
    c = path / 'flash.c'
    c.write_text(FIXTURE + SOURCE + TEST, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(path), '-I', str(ROOT / 'main')]
    if os.environ.get('OTAFLASH_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('flash.exe' if os.name == 'nt' else 'flash')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
