"""Actual components/task_reaper/task_reaper.c against a host FreeRTOS fixture.

Covers init (PSRAM stack, internal fallback, failure, idempotence), self-delete
through the reaper, queue-full and no-reaper fallbacks to the SDK path, direct
deletion of another task, the reaper refusing to delete itself and the
pending/fallback counters. Host fixture, NOT a hardware scheduler test.
REAPER_SANITIZE=1 adds ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'components/task_reaper/task_reaper.c').read_text(encoding='utf-8')

FIXTURE = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
typedef int BaseType_t;
typedef void *TaskHandle_t;
typedef void *QueueHandle_t;
typedef struct {int dummy;} StaticQueue_t;
typedef struct {int dummy;} portMUX_TYPE;
typedef void (*TaskFunction_t)(void *);
#define ESP_OK 0
#define ESP_ERR_NO_MEM 0x101
#define pdPASS 1
#define pdFAIL 0
#define pdTRUE 1
#define portMAX_DELAY 0xffffffffu
#define portMUX_INITIALIZER_UNLOCKED {0}
#define MALLOC_CAP_SPIRAM 0x400
#define MALLOC_CAP_8BIT 0x4
#define ESP_LOGE(tag, ...) ((void)(tag))
static int critical;
#define taskENTER_CRITICAL(m) do{(void)(m);assert(!critical);critical++;}while(0)
#define taskEXIT_CRITICAL(m) do{(void)(m);assert(critical==1);critical--;}while(0)
/* Scheduler model: one current task; suspension of the current task jumps
 * back to the test (it would never run again on the real kernel). */
static TaskHandle_t current = (void *)0x10;
static jmp_buf suspended_jump;
static int caps_create_ok = 1, plain_create_ok = 1, caps_creates, plain_creates;
static int queue_capacity = 8, queued, sdk_self_deletes, sdk_deletes;
static TaskHandle_t queue[8], deleted[16]; static int deleted_count;
static TaskFunction_t reaper_fn; static TaskHandle_t reaper_handle = (void *)0x99;
static QueueHandle_t xQueueCreateStatic(unsigned len, unsigned size, uint8_t *buf, StaticQueue_t *s)
{ assert(len==8 && size==sizeof(TaskHandle_t) && buf && s); return (void *)0x55; }
static BaseType_t xQueueSend(QueueHandle_t q, const void *item, unsigned wait)
{ assert(q==(void*)0x55 && !wait && !critical); if (queued>=queue_capacity) return pdFAIL;
  memcpy(&queue[queued++], item, sizeof(TaskHandle_t)); return pdTRUE; }
static int stop_reaper;
static BaseType_t xQueueReceive(QueueHandle_t q, void *item, unsigned wait)
{ assert(q==(void*)0x55 && wait==portMAX_DELAY);
  if (!queued) { stop_reaper = 1; longjmp(suspended_jump, 2); }
  memcpy(item, &queue[0], sizeof(TaskHandle_t)); memmove(queue, queue+1, (size_t)(--queued)*sizeof(TaskHandle_t)); return pdTRUE; }
static BaseType_t xTaskCreateWithCaps(TaskFunction_t fn, const char *name, unsigned size, void *arg,
                                      unsigned prio, TaskHandle_t *out, unsigned caps)
{ (void)arg; assert(fn && !strcmp(name,"task_reaper") && size>=2048 && prio==6);
  assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)); caps_creates++;
  if (!caps_create_ok) return pdFAIL; reaper_fn=fn; *out=reaper_handle; return pdPASS; }
static BaseType_t xTaskCreate(TaskFunction_t fn, const char *name, unsigned size, void *arg,
                              unsigned prio, TaskHandle_t *out)
{ (void)arg; assert(fn && !strcmp(name,"task_reaper") && size>=2048 && prio==6); plain_creates++;
  if (!plain_create_ok) return pdFAIL; reaper_fn=fn; *out=reaper_handle; return pdPASS; }
static TaskHandle_t xTaskGetCurrentTaskHandle(void){return current;}
static void vTaskSuspend(TaskHandle_t t){assert(!t && !critical); longjmp(suspended_jump, 1);}
static void vTaskDeleteWithCaps(TaskHandle_t t)
{ assert(!critical);
  if (!t || t==current) { sdk_self_deletes++; longjmp(suspended_jump, 3); }
  assert(t!=reaper_handle); sdk_deletes++; deleted[deleted_count++]=t; }
'''

TEST = r'''
static int run_self_delete(TaskHandle_t self)
{ current=self; int r=setjmp(suspended_jump); if(!r) task_reaper_self_delete(); return r; }
static void run_reaper(void)
{ TaskHandle_t saved=current; current=reaper_handle; stop_reaper=0;
  if(!setjmp(suspended_jump)) reaper_fn(NULL); assert(stop_reaper); current=saved; }
int main(void){
#if !CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    caps_create_ok=0;
#endif
    /* No reaper yet: SDK self-delete fallback, counted. */
    assert(run_self_delete((void*)0x20)==3 && sdk_self_deletes==1 && task_reaper_fallbacks()==1);
    /* Initialization failure is reported and stays retryable. */
    caps_create_ok=0; plain_create_ok=0;
    assert(task_reaper_init()==ESP_ERR_NO_MEM && !critical);
    assert(run_self_delete((void*)0x21)==3 && sdk_self_deletes==2);
    plain_create_ok=1;
#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    caps_create_ok=1;
#endif
    int caps_before=caps_creates, plain_before=plain_creates;
    assert(task_reaper_init()==ESP_OK);
#if CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY
    assert(caps_creates==caps_before+1 && plain_creates==plain_before); /* PSRAM stack first */
#else
    assert(caps_creates==caps_before && plain_creates==plain_before+1);
#endif
    assert(task_reaper_init()==ESP_OK && caps_creates+plain_creates==caps_before+plain_before+1);
    /* Self-delete through the reaper: no SDK self-delete, pending until reaped. */
    assert(run_self_delete((void*)0x30)==1 && sdk_self_deletes==2 && task_reaper_pending()==1);
    assert(run_self_delete((void*)0x31)==1 && task_reaper_pending()==2);
    run_reaper();
    assert(deleted_count==2 && deleted[0]==(void*)0x30 && deleted[1]==(void*)0x31);
    assert(!task_reaper_pending() && !queued && sdk_deletes==2 && task_reaper_reaped()==2);
    /* task_reaper_delete(NULL) and (self) both self-delete via the reaper. */
    current=(void*)0x40; if(!setjmp(suspended_jump)) task_reaper_delete(NULL);
    current=(void*)0x41; if(!setjmp(suspended_jump)) task_reaper_delete((void*)0x41);
    assert(task_reaper_pending()==2); run_reaper(); assert(deleted_count==4 && !task_reaper_pending());
    /* Another task is deleted directly, synchronously, without the queue. */
    current=(void*)0x50; task_reaper_delete((void*)0x51);
    assert(deleted_count==5 && deleted[4]==(void*)0x51 && !queued);
    /* Queue full: bounded, falls back to the SDK path and keeps counts exact. */
    for(int i=0;i<8;i++) assert(run_self_delete((void*)(uintptr_t)(0x60+i))==1);
    assert(task_reaper_pending()==8);
    unsigned fb=task_reaper_fallbacks();
    assert(run_self_delete((void*)0x70)==3 && task_reaper_fallbacks()==fb+1 && task_reaper_pending()==8);
    run_reaper(); assert(!task_reaper_pending() && deleted_count==13 && task_reaper_reaped()==12);
    /* The reaper never queues itself: it uses the SDK path. */
    assert(run_self_delete(reaper_handle)==3 && !queued);
    assert(!critical);
    puts("PASS: actual task reaper init/fallback/self-delete/direct delete/queue bound (host fixture)");
}
'''

with tempfile.TemporaryDirectory(prefix='task-reaper-') as directory:
    path = Path(directory)
    (path / 'freertos').mkdir()
    for name in ('task_reaper.h', 'esp_heap_caps.h', 'esp_log.h', 'freertos/idf_additions.h',
                 'freertos/queue.h', 'esp_err.h', 'freertos/FreeRTOS.h', 'freertos/task.h'):
        (path / name).write_text('#pragma once\n', encoding='utf-8')
    proto = ('esp_err_t task_reaper_init(void);void task_reaper_self_delete(void);'
             'void task_reaper_delete(TaskHandle_t handle);unsigned task_reaper_pending(void);'
             'unsigned task_reaper_fallbacks(void);\n')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-misleading-indentation', '-Wno-clobbered', '-I', str(path)]
    if os.environ.get('REAPER_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    for external in (1, 0):
        program = (f'#define CONFIG_SPIRAM_ALLOW_STACK_EXTERNAL_MEMORY {external}\n' + FIXTURE + proto
                   + SOURCE.replace('__attribute__((noreturn))', '') + TEST)
        c = path / f'reaper{external}.c'; c.write_text(program, encoding='utf-8')
        binary = path / (f'reaper{external}' + ('.exe' if os.name == 'nt' else ''))
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
