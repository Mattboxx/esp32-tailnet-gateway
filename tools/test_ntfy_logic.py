"""Exercise the actual ntfy command accounting and alert builder.

Synthetic HTTP/log/allocator tripwires; no board access or external traffic.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/ntfy_integration.c').read_text()
command = 'static NTFY_NOINLINE void handle_command' + source.split('static NTFY_NOINLINE void handle_command', 1)[1].split('static void collect_line', 1)[0]
reset_builder = source[source.index('static void appendf('):source.index('static NTFY_NOINLINE esp_err_t send_info(')]
assert 'append_reset_reason(text, 8192, c);' in source
boot = 'static NTFY_NOINLINE esp_err_t send_system_event' + source.split('static NTFY_NOINLINE esp_err_t send_system_event',1)[1].split('static void task_main',1)[0]
alert = 'static NTFY_NOINLINE esp_err_t send_tailscale_alert' + source.split('static NTFY_NOINLINE esp_err_t send_tailscale_alert', 1)[1].split('static NTFY_NOINLINE uint32_t available_update_id', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <stdarg.h>
#define NTFY_NOINLINE
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 2
#define ESP_ERR_INVALID_ARG 3
#define HTTP_EVENT_ON_DATA 1
#define portMAX_DELAY 0
typedef int esp_err_t;
typedef struct { bool info_enabled, info_include_details, poweron_events; } ntfy_integration_config_t;
typedef struct { int event_id, data_len; void *data, *user_data; } esp_http_client_event_t;
static int s_lock;
static struct { unsigned alerts_sent, commands_received, command_errors; } s_status;
static void xSemaphoreTake(int a,int b) { (void)a; (void)b; }
static void xSemaphoreGive(int a) { (void)a; }
static int publish_result, info_result, allocations, fail_at, live, log_reads;
static char published[2300];
void *checked_malloc(size_t n) {
    if (++allocations == fail_at) return NULL;
    void *p = malloc(n); if(p) live++; return p;
}
void checked_free(void *p) { if(p) live--; free(p); }
#define malloc checked_malloc
#define free checked_free
static esp_err_t publish_message(const ntfy_integration_config_t *c,const char *title,const char *tags,const char *msg) {
    (void)c; (void)title; (void)tags;
    assert(strlen(msg)<sizeof published); strcpy(published,msg); return publish_result;
}
size_t log_capture_read(char *out,size_t capacity) {
    log_reads++;
    const char *marker="PRIVATE_LOCAL_LOG_FIXTURE";
    memset(out,'x',capacity-1);memcpy(out+capacity-1-strlen(marker),marker,strlen(marker));
    out[capacity-1]=0;return capacity-1;
}
static esp_err_t send_info(const ntfy_integration_config_t *c) { (void)c; return info_result; }
static esp_err_t wake_argument(const ntfy_integration_config_t *c,const char *s) { (void)c; (void)s; return ESP_FAIL; }
typedef struct {char name[32];uint8_t mac[6];} wol_device_t;
static bool wol_parse_mac(const char *s,uint8_t out[6]){(void)s;(void)out;return false;}
static int wol_count(void){return 0;}
static bool wol_get(int i,wol_device_t *d){(void)i;(void)d;return false;}
static void wol_format_mac(const uint8_t mac[6],char out[18]){(void)mac;strcpy(out,"00:00:00:00:00:01");}
static int homelab_ops_command(const char *s,bool wake){(void)s;(void)wake;return ESP_FAIL;}
static const char *esp_err_to_name(esp_err_t e) { (void)e; return "fixture error"; }
'''
boot_fixture = r'''
#include "ntfy_events.h"
/* ESP-IDF 5.5.3 esp_system.h order, including every reset cause. */
typedef enum {ESP_RST_UNKNOWN,ESP_RST_POWERON,ESP_RST_EXT,ESP_RST_SW,ESP_RST_PANIC,ESP_RST_INT_WDT,ESP_RST_TASK_WDT,ESP_RST_WDT,ESP_RST_DEEPSLEEP,ESP_RST_BROWNOUT,ESP_RST_SDIO,ESP_RST_USB,ESP_RST_JTAG,ESP_RST_EFUSE,ESP_RST_PWR_GLITCH,ESP_RST_CPU_LOCKUP} esp_reset_reason_t;
typedef struct {const char *version;} esp_app_desc_t;
typedef struct {char latest_version[32];} ota_remote_state_t;
static esp_reset_reason_t reset_reason;
static esp_reset_reason_t esp_reset_reason(void){return reset_reason;}
static const esp_app_desc_t *esp_app_get_description(void){static const esp_app_desc_t app={"fixture"};return &app;}
static void ota_remote_get_state(ota_remote_state_t *s){strcpy(s->latest_version,"fixture-next");}
'''
tests = r'''
int main(void) {
    ntfy_integration_config_t c={.info_enabled=true};
    info_result=ESP_FAIL; handle_command(&c," info\n");
    assert(s_status.command_errors==1 && s_status.commands_received==0);
    info_result=ESP_OK; handle_command(&c,"INFO");
    assert(s_status.command_errors==1 && s_status.commands_received==1);
    handle_command(&c,"unknown"); assert(s_status.command_errors==1);
    for(int details=0;details<=1;details++) {
        c.info_include_details=details!=0;
        publish_result=ESP_OK;assert(send_tailscale_alert(&c)==ESP_OK);
        assert(s_status.alerts_sent==(unsigned)details+1&&live==0&&strlen(published)<2300);
        assert(!strstr(published,"PRIVATE_LOCAL_LOG_FIXTURE"));
        assert(!strstr(published,"Recent local log tail:"));
        assert(strstr(published,"Tailscale has remained disconnected"));
        assert(log_reads==0&&allocations==0);
    }
    publish_result=ESP_FAIL; assert(send_tailscale_alert(&c)==ESP_FAIL);
    assert(s_status.alerts_sent==2 && live==0);
    publish_result=ESP_ERR_NO_MEM;assert(send_tailscale_alert(&c)==ESP_ERR_NO_MEM);
    assert(s_status.alerts_sent==2&&live==0&&log_reads==0&&allocations==0);
    publish_result=ESP_OK;fail_at=1;assert(send_tailscale_alert(&c)==ESP_OK);
    assert(s_status.alerts_sent==3&&live==0&&log_reads==0&&allocations==0);
    fail_at=0;publish_result=ESP_OK;
    const char *descriptions[]={"unknown reset cause","power restored or first power-up","external reset pin","software-requested restart","firmware crash (panic/exception)","interrupt watchdog timeout","task watchdog timeout","watchdog timeout","wake from deep sleep","supply voltage drop (brownout)","SDIO reset","USB peripheral reset","JTAG/debugger reset","eFuse error","power glitch detected","CPU lockup (double exception)"};
    for(unsigned enabled=0;enabled<2;enabled++){
      c.poweron_events=enabled!=0;
      for(unsigned reason=0;reason<sizeof descriptions/sizeof *descriptions;reason++){
        reset_reason=(esp_reset_reason_t)reason;
        assert(send_system_event(&c,NTFY_EVENT_BOOT,0)==ESP_OK&&strstr(published,descriptions[reason]));
        assert((strstr(published,"(possible blackout)")!=NULL)==(enabled&&reason==ESP_RST_POWERON));
        assert(!strstr(published,"reset reason ")&&!strstr(published,"outage lasted")&&!strstr(published,"PRIVATE_LOCAL_LOG_FIXTURE"));
        assert(strlen(published)<192&&live==0&&log_reads==0&&allocations==0);
        char info_line[192]="";
        append_reset_reason(info_line,sizeof info_line,&c);
        assert(strstr(info_line,descriptions[reason]));
        assert((strstr(info_line,"(possible blackout)")!=NULL)==(enabled&&reason==ESP_RST_POWERON));
        assert(strstr(published,info_line));
        char tiny[8]="";append_reset_reason(tiny,sizeof tiny,&c);assert(tiny[7]==0);
      }
    }
    reset_reason=(esp_reset_reason_t)255;
    assert(send_system_event(&c,NTFY_EVENT_BOOT,0)==ESP_OK&&strstr(published,"unknown reset cause")&&!strstr(published,"possible blackout"));
    puts("PASS: ntfy info/transport accounting and alert privacy; boot/info:16 explicit reset causes with power-on option ON/OFF, unknown-cause fallback, no allocations or blackout labels on faults");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-logic-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + boot_fixture + reset_builder + command + alert + boot + tests)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'main')]
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# Actual opt-in system-event scheduler (main/ntfy_events.h).
EVENTS = r'''
#include <assert.h>
#include <stdio.h>
#include "ntfy_events.h"
int main(void){
    bool other,power;
    for(unsigned v=0;v<256;v++){
      ntfy_events_decode((uint8_t)v,&other,&power);
      assert(other==(v==1||v==3)&&power==(v==1||v==2));
      if(v<4)assert(ntfy_events_options(other,power)==v);
    }
    for(int boot=0;boot<2;boot++)for(int rest=0;rest<2;rest++){
      ntfy_events_t selected;ntfy_events_init(&selected);
      ntfy_events_select(&selected,true,boot,rest);assert(ntfy_events_due(&selected)==(boot?NTFY_EVENT_BOOT:0));
      ntfy_events_tick(&selected,true,rest,rest?123:0);
      ntfy_events_select(&selected,false,boot,rest);assert(!ntfy_events_due(&selected));
    }
    ntfy_events_t s;ntfy_events_init(&s);
    assert(ntfy_events_due(&s)==NTFY_EVENT_BOOT);
    ntfy_events_tick(&s,true,false,0);assert(ntfy_events_due(&s)==NTFY_EVENT_BOOT);
    ntfy_events_result(&s,NTFY_EVENT_BOOT,false);assert(!ntfy_events_due(&s)&&s.retry_s==60); /* bounded retry */
    for(int i=0;i<59;i++)ntfy_events_tick(&s,true,false,0);
    assert(!ntfy_events_due(&s));ntfy_events_tick(&s,true,false,0);assert(ntfy_events_due(&s)==NTFY_EVENT_BOOT);
    ntfy_events_result(&s,NTFY_EVENT_BOOT,true);assert(!ntfy_events_due(&s));
    /* Restored and update both pending: one message per call, boot-restored-update order. */
    ntfy_events_tick(&s,true,true,0xabc);assert(ntfy_events_due(&s)==NTFY_EVENT_RESTORED);
    ntfy_events_result(&s,NTFY_EVENT_RESTORED,true);assert(ntfy_events_due(&s)==NTFY_EVENT_UPDATE);
    ntfy_events_result(&s,NTFY_EVENT_UPDATE,true);assert(!ntfy_events_due(&s));
    ntfy_events_tick(&s,true,false,0xabc);assert(!ntfy_events_due(&s)); /* same version announced once */
    ntfy_events_tick(&s,true,false,0);ntfy_events_tick(&s,true,false,0xabc);assert(!ntfy_events_due(&s)); /* vanished+returned: still once */
    ntfy_events_tick(&s,true,false,0xdef);assert(ntfy_events_due(&s)==NTFY_EVENT_UPDATE);
    /* Disabled: nothing queued, versions seen while off are not replayed later. */
    ntfy_events_init(&s);ntfy_events_tick(&s,false,true,0x111);assert(!s.pending&&!ntfy_events_due(&s));
    ntfy_events_tick(&s,true,false,0x111);assert(!ntfy_events_due(&s));
    ntfy_events_result(&s,NTFY_EVENT_UPDATE,false);ntfy_events_tick(&s,false,false,0);assert(!s.retry_s); /* disable clears retry */
    puts("PASS: actual ntfy system events: boot once, bounded 60 s retry, ordering, update announced once per version, no backlog while disabled");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-events-') as directory:
    path = Path(directory); (path / 'events.c').write_text(EVENTS)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('events.exe' if os.name == 'nt' else 'events')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'events.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
