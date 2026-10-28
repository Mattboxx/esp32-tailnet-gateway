"""Actual notification queue/worker and outage coalescer with deterministic SDK/transport fixtures.

No Telegram, email, board, real TLS or scheduler is exercised. Time, allocation
failure and producer interleavings are injected into the actual C functions.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'main/notify_channels.c').read_text(encoding='utf-8')
types=src[src.index('typedef struct {uint8_t kind, level, channels, attempts;'):src.index('/* --- notify store (begin) --- */')]
code=src[src.index('/* --- delivery worker:'):src.index('void notify_channels_enabled')]
wanted=src[src.index('bool notify_wanted('):src.index('typedef struct {',src.index('bool notify_wanted('))]
history=(ROOT/'main/history.c').read_text(encoding='utf-8')
boot=history[history.index('    reset_history_entry_t entry = {0};'):history.index('\n}',history.index('    reset_history_entry_t entry = {0};'))]
fixture=r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "notify_channels.h"
#include "history.h"
#define QUEUE_MAX 8
#define MAX_ATTEMPTS 10
#define RETRY_S 30
#define CH_TG 1
#define CH_MAIL 2
#define EXT_RAM_BSS_ATTR
#define MALLOC_CAP_SPIRAM 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY 0
#define ESP_LOGW(...) ((void)0)
typedef int SemaphoreHandle_t;
typedef int StaticSemaphore_t;
static uint32_t clock_s;
static int task_ok=1, creates, tg_result, mail_result, sends;
static bool tailnet_up;
static jmp_buf exit_worker;
static char last_text[256];
static void (*during_send)(void);
static void (*registered_poll)(void);
static int64_t esp_timer_get_time(void){return (int64_t)clock_s*1000000;}
static int tailscale_is_connected(void){return tailnet_up;}
static void xSemaphoreTake(int x,int y){(void)x;(void)y;}
static void xSemaphoreGive(int x){(void)x;}
static void task_reaper_self_delete(void){longjmp(exit_worker,1);}
static void vTaskDelay(int ms){clock_s+=(uint32_t)ms/1000;}
static int xTaskCreateWithCaps(void (*fn)(void*),const char*n,int a,void*b,int c,void*d,int e){(void)fn;(void)n;(void)a;(void)b;(void)c;(void)d;(void)e;creates++;return task_ok;}
static const char *esp_err_to_name(int e){(void)e;return "fixture error";}
static void *heap_caps_calloc(size_t n,size_t size,int cap){(void)cap;return calloc(n,size);}
void history_set_sink_poller(history_sink_t sink,history_sink_poll_t poll){(void)sink;registered_poll=poll;}
bool notify_wanted(uint8_t setting,unsigned kind,unsigned level){return kind==HIST_EV_SERVICE||setting==NOTIFY_ALL||level>=HIST_WARN;}
static void when_text(uint32_t t,char *s,size_t n){(void)t;if(n)s[0]=0;}
static int telegram(const notify_config_t*c,const char*t,char*w,size_t n){(void)c;(void)w;(void)n;sends++;snprintf(last_text,sizeof last_text,"%s",t);if(during_send){void(*f)(void)=during_send;during_send=NULL;f();}return tg_result;}
static int email(const notify_config_t*c,const char*t,char*w,size_t n){(void)c;(void)t;(void)w;(void)n;return mail_result;}
'''+types+code+r'''
volatile int ap_connect;
static void reset(void){free(s_queue);s_queue=calloc(QUEUE_MAX,sizeof *s_queue);s_head=s_count=s_dropped=0;s_worker=false;
 memset(&s_cfg,0,sizeof s_cfg);s_cfg.tg_enabled=true;s_cfg.level=NOTIFY_PROBLEMS;s_mail_level=NOTIFY_PROBLEMS;s_startup_channels=0;s_link_grace_s=60;
 memset(s_links,0,sizeof s_links);memset(&s_tg,0,sizeof s_tg);memset(&s_mail,0,sizeof s_mail);
 s_tokens=6;s_refill=0;s_worker_retry=0;s_worker_backoff=30;clock_s=0;creates=sends=0;task_ok=1;tg_result=mail_result=0;ap_connect=0;tailnet_up=false;during_send=NULL;}
static void drain(void){if(!setjmp(exit_worker))worker(NULL);}
static void lost(void){offer(HIST_EV_UPLINK,HIST_WARN,0,"Wi-Fi uplink lost (reason 200)");}
static void up(void){ap_connect=1;offer(HIST_EV_UPLINK,HIST_INFO,0,"Wi-Fi uplink connected, 192.0.2.1");}
static void fill_while_sending(void){for(int i=0;i<QUEUE_MAX;i++)enqueue_locked(HIST_EV_SERVICE,HIST_INFO,CH_TG,0,"new result");}
static void recover_while_sending(void){clock_s=65;up();}
int main(void){
 /* The queue retains the entire maximum producer message. */
 reset();char complete[HIST_TEXT_MAX+1];memset(complete,'X',HIST_TEXT_MAX);complete[HIST_TEXT_MAX]=0;
 offer(HIST_EV_SERVICE,HIST_INFO,0,complete);assert(s_count==1&&!strcmp(s_queue[s_head].text,complete));
 drain();assert(!strcmp(last_text,complete));
 /* Startup is immediate and independently selected even in Problems mode. */
 for(unsigned enabled=0;enabled<4;enabled++)for(unsigned startup=0;startup<16;startup++){
  for(unsigned power=0;power<2;power++){
  reset();s_cfg.tg_enabled=enabled&CH_TG;s_cfg.mail_enabled=enabled&CH_MAIL;s_startup_channels=startup;
  offer(HIST_EV_BOOT,HIST_INFO,0,power?"Power-on start fixture, reset POWERON":"Started fixture, reset SW");
  unsigned expected=enabled&(power?startup>>2:startup);assert(s_count==(expected?1:0));
  if(expected)assert(s_queue[s_head].channels==expected&&clock_s==0);
 }}
 reset();s_cfg.level=NOTIFY_ALL;offer(HIST_EV_BOOT,HIST_INFO,0,"Started fixture");assert(!s_count);
 reset();offer(HIST_EV_BOOT,HIST_ERROR,0,"Started fixture, reset WDT");assert(s_count==1);
 reset();offer(HIST_EV_CRASH,HIST_ERROR,0,"Crash fixture");assert(s_count==1);
 reset();s_startup_channels=CH_TG;lost();clock_s=1;offer(HIST_EV_BOOT,HIST_INFO,0,"Started fixture");
 assert(s_count==1&&s_queue[s_head].kind==HIST_EV_BOOT&&!s_links[LINK_WIFI].announced);
 reset();s_link_grace_s=300;lost();clock_s=299;notify_poll();assert(!s_count);clock_s=300;notify_poll();assert(s_count==1);
 s_link_grace_s=600;clock_s=310;up();assert(s_count==1&&strstr(s_queue[s_head].text,"recovered after 310"));
 reset();s_link_grace_s=15;lost();clock_s=14;notify_poll();assert(!s_count);clock_s=15;notify_poll();assert(s_count==1);
 reset();lost();clock_s=59;notify_poll();assert(!s_count&&!creates);up();notify_poll();assert(!s_count&&!sends);
 reset();for(int day=0;day<10;day++){clock_s=(uint32_t)day*86400;ap_connect=0;lost();clock_s+=3;up();notify_poll();}assert(!s_count&&!creates);
 reset();lost();clock_s=60;notify_poll();assert(s_count==1&&s_links[LINK_WIFI].announced);notify_poll();lost();notify_poll();assert(s_count==1);drain();assert(s_tg.sent==1);clock_s=300;notify_poll();assert(!s_count);
 reset();lost();clock_s=60;notify_poll();clock_s=70;up();assert(s_count==1&&strstr(s_queue[s_head].text,"recovered after 70 seconds"));drain();assert(strstr(last_text,"recovered")&&sends==1);
 reset();lost();clock_s=60;notify_poll();tg_result=ESP_FAIL;drain();assert(s_tg.failed==MAX_ATTEMPTS&&!s_count);clock_s=600;up();assert(s_count==1&&strstr(s_queue[s_head].text,"recovered after 600"));tg_result=ESP_OK;drain();assert(s_tg.sent==1);
 reset();lost();clock_s=3;ap_connect=1;notify_poll();assert(!s_links[LINK_WIFI].down&&!s_count);up();assert(!s_count);
 reset();lost();clock_s=30;offer(HIST_EV_UPLINK,HIST_INFO,0,"Dynamic DNS updated");assert(s_links[LINK_WIFI].down);clock_s=60;notify_poll();assert(s_count==1);
 reset();offer(HIST_EV_UPLINK,HIST_WARN,0,"Dynamic DNS not updated: fixture");assert(s_count==1);assert(!s_links[LINK_WIFI].down);
 reset();offer(HIST_EV_TAILNET,HIST_WARN,0,"Tailnet connection lost");clock_s=59;notify_poll();assert(!s_count);tailnet_up=true;notify_poll();offer(HIST_EV_TAILNET,HIST_INFO,0,"Tailnet connected");assert(!s_count);
 reset();offer(HIST_EV_TAILNET,HIST_WARN,0,"Tailnet connection lost");clock_s=60;notify_poll();assert(s_count==1&&s_queue[s_head].link==LINK_TAILNET);
 reset();s_cfg.level=NOTIFY_ALL;lost();clock_s=1;up();assert(!s_count);offer(HIST_EV_UPLINK,HIST_INFO,0,"Dynamic DNS updated");assert(s_count==1);
 reset();offer(HIST_EV_SECURITY,HIST_ERROR,0,"Security fixture");assert(s_count==1);drain();assert(s_tg.sent==1);
 reset();task_ok=0;enqueue_locked(HIST_EV_SERVICE,HIST_INFO,CH_TG,0,"result");assert(s_count==1&&!s_worker&&creates==1);clock_s=29;notify_poll();assert(creates==1);clock_s=30;task_ok=1;notify_poll();assert(s_worker&&creates==2);drain();
 reset();enqueue_locked(HIST_EV_SERVICE,HIST_INFO,CH_TG,0,"old head");during_send=fill_while_sending;drain();assert(s_tg.sent==QUEUE_MAX+1&&s_count==0&&s_dropped==1);
 reset();lost();clock_s=60;notify_poll();during_send=recover_while_sending;drain();assert(strstr(last_text,"recovered after 65")&&s_count==0);
 reset();lost();clock_s=10;s_cfg.tg_enabled=false;apply_locked();assert(!s_queue&&!registered_poll&&!s_links[LINK_WIFI].down);
 free(s_queue);puts("PASS actual notify delivery: independent boot masks, crash bypass, short/daily drops, long outage/recovery, expired retries, lost recovery event, DDNS separation, independent Tailnet grace, critical bypass, task OOM retry, queue overflow and in-flight recovery");
}
'''
producer = r'''
#include <stdarg.h>
typedef enum {ESP_RST_POWERON,ESP_RST_SW,ESP_RST_PANIC,ESP_RST_INT_WDT,ESP_RST_TASK_WDT,ESP_RST_WDT,ESP_RST_BROWNOUT} esp_reset_reason_t;
typedef struct {char reason[16],who[32],crash[128];} reset_history_entry_t;
typedef struct {const char *version;} esp_app_desc_t;
typedef struct {const char *label;} esp_partition_t;
typedef int esp_ota_img_states_t;
#define ESP_OTA_IMG_PENDING_VERIFY 1
static esp_reset_reason_t raw_cause;
static const char *recorded_cause="FLASH";
static esp_reset_reason_t esp_reset_reason(void){return raw_cause;}
static int reset_history_load(reset_history_entry_t *entry,int n){assert(n==1);snprintf(entry->reason,sizeof entry->reason,"%s",recorded_cause);return 1;}
static const esp_app_desc_t *esp_app_get_description(void){static const esp_app_desc_t app={"fixture"};return &app;}
static const esp_partition_t *esp_ota_get_running_partition(void){static const esp_partition_t p={"ota_0"};return &p;}
static int esp_ota_get_state_partition(const esp_partition_t *p,esp_ota_img_states_t *s){(void)p;(void)s;return ESP_FAIL;}
void history_event(history_kind_t kind,history_level_t level,const char *format,...){
 char text[HIST_TEXT_MAX+1];va_list ap;va_start(ap,format);vsnprintf(text,sizeof text,format,ap);va_end(ap);offer(kind,level,0,text);
}
static void emit_actual_boot(void){
''' + boot + r'''
}
'''
boot_cases=r'''
 /* Actual history producer -> actual sink -> channel selection. History's
  * FLASH label must not hide a power-on or fault from the hardware reason. */
 for(unsigned raw=ESP_RST_POWERON;raw<=ESP_RST_BROWNOUT;raw++){
  reset();raw_cause=(esp_reset_reason_t)raw;recorded_cause="FLASH";s_startup_channels=CH_TG<<2;
  emit_actual_boot();
  if(raw==ESP_RST_SW)assert(!s_count);
  else {assert(s_count==1);assert(s_queue[s_head].level==(raw==ESP_RST_POWERON?HIST_INFO:HIST_ERROR));}
 }
 reset();raw_cause=ESP_RST_SW;recorded_cause="POWERON";s_startup_channels=CH_TG<<2;
 emit_actual_boot();assert(!s_count);
'''
fixture=fixture.replace('int main(void){',producer+'\nint main(void){'+boot_cases,1)
with tempfile.TemporaryDirectory(prefix='notify-delivery-') as directory:
    p=Path(directory)
    (p/'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n')
    (p/'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n')
    fixture=fixture.replace('bool notify_wanted(uint8_t setting,unsigned kind,unsigned level){return kind==HIST_EV_SERVICE||setting==NOTIFY_ALL||level>=HIST_WARN;}',wanted)
    (p/'case.c').write_text(fixture,encoding='utf-8')
    binary=p/('case.exe' if os.name=='nt' else 'case')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-I',str(p),'-I',str(ROOT/'main')]
    if os.environ.get('NOTIFY_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'case.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=20)
