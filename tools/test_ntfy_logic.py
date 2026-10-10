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
alert = 'static NTFY_NOINLINE esp_err_t send_tailscale_alert' + source.split('static NTFY_NOINLINE esp_err_t send_tailscale_alert', 1)[1].split('static void task_main', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#define NTFY_NOINLINE
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 2
#define ESP_ERR_INVALID_ARG 3
#define HTTP_EVENT_ON_DATA 1
#define portMAX_DELAY 0
typedef int esp_err_t;
typedef struct { bool info_enabled, info_include_details; } ntfy_integration_config_t;
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
static const char *esp_err_to_name(esp_err_t e) { (void)e; return "fixture error"; }
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
    puts("PASS: ntfy info failure accounting, alert privacy (no local-log reads/uploads), allocation-free builder and transport failure accounting");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-logic-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + command + alert + tests)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
