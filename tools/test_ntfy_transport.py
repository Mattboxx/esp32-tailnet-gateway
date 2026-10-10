"""Exercise actual ntfy publish/poll code with deterministic HTTP failures.

No external traffic or device access. NTFY_SANITIZE=1 enables ASan/UBSan.
Use SDK cJSON via CJSON_SOURCE, or system libcjson in Linux CI.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/ntfy_integration.c').read_text()
header = (ROOT / 'main/ntfy_integration.h').read_text()
config_type = 'typedef struct {' + header.split('typedef struct {', 1)[1].split('} ntfy_integration_config_t;', 1)[0] + '} ntfy_integration_config_t;\n'
buffer_type = 'typedef struct {' + source.split('typedef struct {', 1)[1].split('} response_buffer_t;', 1)[0] + '} response_buffer_t;\n'
callback = 'static esp_err_t http_event' + source.split('static esp_err_t http_event', 1)[1].split('static void defaults', 1)[0]
validation = 'static bool topic_valid' + source.split('static bool topic_valid', 1)[1].split('static void snapshot', 1)[0]
transport = 'static void build_url' + source.split('static void build_url', 1)[1].split('static void appendf', 1)[0]
poll = 'static bool response_is_ours' + source.split('static bool response_is_ours', 1)[1].split('static bool uplink_connected', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include "cJSON.h"
#define NTFY_NOINLINE
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 2
#define ESP_ERR_INVALID_ARG 3
#define HTTP_EVENT_ON_DATA 1
#define HTTP_METHOD_GET 0
#define HTTP_METHOD_POST 1
#define portMAX_DELAY 0
typedef int esp_err_t;
typedef struct { int event_id, data_len; void *data, *user_data; } esp_http_client_event_t;
typedef struct {
    const char *url; int method, timeout_ms; bool disable_auto_redirect;
    void *crt_bundle_attach;
    esp_err_t (*event_handler)(esp_http_client_event_t *);
    void *user_data;
} esp_http_client_config_t;
static void *esp_crt_bundle_attach;
static const char *TAG = "fixture";
static int log_calls;
static void log_failure(const char *tag,const char *format,...) {(void)tag;(void)format;log_calls++;}
#define ESP_LOGW(...) log_failure(__VA_ARGS__)
static int s_lock;
#define xSemaphoreTake(a,b) ((void)(a),(void)(b))
#define xSemaphoreGive(a) ((void)(a))
static struct { bool last_publish_ok; } s_status;
static char s_last_event_id[48];
static size_t strlcpy(char *d,const char *s,size_t cap) { size_t n=strlen(s); if(cap) {size_t k=n<cap-1?n:cap-1;memcpy(d,s,k);d[k]=0;}return n; }
typedef struct { esp_http_client_config_t config; char authorization[176]; } fake_client_t;
typedef fake_client_t *esp_http_client_handle_t;
static fake_client_t client;
static int response_code=200, auth_failure, network_calls, foreign_requests, cleanups, commands, cursor_writes;
static const char *response = "{\"id\":\"fixture-id\",\"event\":\"message\",\"message\":\"info\"}\n";
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *c) {
    memset(&client,0,sizeof client); client.config=*c; return &client;
}
static esp_err_t esp_http_client_set_header(esp_http_client_handle_t c,const char *k,const char *v) {
    if(!strcmp(k,"Authorization")) {
        if(auth_failure) return ESP_ERR_NO_MEM;
        assert(!strchr(v,'\r') && !strchr(v,'\n'));
        strlcpy(c->authorization,v,sizeof c->authorization);
    }
    return ESP_OK;
}
static esp_err_t esp_http_client_set_post_field(esp_http_client_handle_t c,const char *v,int n) { (void)c;assert(v&&n>0);return ESP_OK; }
static esp_err_t esp_http_client_perform(esp_http_client_handle_t c) {
    network_calls++;
    /* Model SDK's redirect behavior: a foreign redirect keeps the manually
     * installed Authorization header and replays POST data unless disabled. */
    if(response_code>=300 && response_code<400 && !c->config.disable_auto_redirect) {
        network_calls++; foreign_requests++; assert(c->authorization[0]); response_code=200;
    }
    if(c->config.event_handler) {
        esp_http_client_event_t e={.event_id=HTTP_EVENT_ON_DATA,.data_len=(int)strlen(response),.data=(void *)response,.user_data=c->config.user_data};
        c->config.event_handler(&e);
    }
    return ESP_OK;
}
static int esp_http_client_get_status_code(esp_http_client_handle_t c) { (void)c;return response_code; }
static void esp_http_client_cleanup(esp_http_client_handle_t c) { (void)c;cleanups++; }
static const char *esp_err_to_name(esp_err_t e) { (void)e;return "fixture error"; }
static esp_err_t nvs_param_set_str(const char *k,const char *v) {assert(!strcmp(k,"ntfy_last")&&v[0]);cursor_writes++;return ESP_OK;}
'''
command_stub = 'static void handle_command(const ntfy_integration_config_t *c,const char *s) {(void)c;assert(!strcmp(s,"info"));commands++;}\n'
tests = r'''
static void reset(int code) {
    response_code=code; auth_failure=network_calls=foreign_requests=cleanups=commands=cursor_writes=0;
    s_last_event_id[0]=0;
}
int main(void) {
    ntfy_integration_config_t c={.enabled=true,.failure_delay_seconds=120,.poll_interval_seconds=15};
    strcpy(c.server,"https://notify.example");strcpy(c.topic,"fixture");strcpy(c.token,"tk_fixture");
    assert(config_valid(&c));
    reset(200); assert(publish_message(&c,"Fixture","fixture","Synthetic data")==ESP_OK);
    assert(network_calls==1&&cleanups==1&&s_status.last_publish_ok);
    assert(!strcmp(client.authorization,"Bearer tk_fixture"));
    reset(200); poll_commands(&c); assert(network_calls==1&&cleanups==1&&commands==1&&cursor_writes==1);
    int codes[]={301,302,303,307,308,401,403,500};
    for(unsigned i=0;i<sizeof codes/sizeof codes[0];i++) {
        reset(codes[i]); assert(publish_message(&c,"Fixture","fixture","Synthetic data")!=ESP_OK);
        assert(network_calls==1&&foreign_requests==0&&cleanups==1&&!s_status.last_publish_ok);
        reset(codes[i]); poll_commands(&c);
        assert(network_calls==1&&foreign_requests==0&&cleanups==1&&commands==0&&cursor_writes==0&&!s_last_event_id[0]);
    }
    reset(200); auth_failure=1; assert(publish_message(&c,"Fixture","fixture","Synthetic data")==ESP_ERR_NO_MEM);
    assert(network_calls==0&&cleanups==1&&!s_status.last_publish_ok);
    reset(200); auth_failure=1; poll_commands(&c); assert(network_calls==0&&cleanups==1&&commands==0);
    const char *bad[]={"tk_fixture\r\nInjected: value","token with space","token\tvalue","token\177"};
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++) {
        strcpy(c.token,bad[i]);assert(!config_valid(&c));
        reset(200); assert(publish_message(&c,NULL,NULL,"Synthetic data")==ESP_ERR_INVALID_ARG);
        assert(network_calls==0&&cleanups==1&&!s_status.last_publish_ok);
        reset(200); poll_commands(&c); assert(network_calls==0&&cleanups==1&&commands==0);
    }
    c.token[0]=0; assert(config_valid(&c));
    reset(200); assert(publish_message(&c,NULL,NULL,"Synthetic data")==ESP_OK);
    assert(network_calls==1&&!client.authorization[0]);
    strcpy(c.server,"http://notify.example:8080"); assert(config_valid(&c));
    const char *bad_urls[]={"https://user:password@notify.example","https://notify.example/\v","https://notify.example/\\path"};
    for(unsigned i=0;i<sizeof bad_urls/sizeof bad_urls[0];i++) {strcpy(c.server,bad_urls[i]);assert(!config_valid(&c));}
    strcpy(c.server,"https://notify.example");
    ntfy_integration_config_t invalid=c;
    memset(invalid.server,'x',sizeof invalid.server);assert(!config_valid(&invalid));
    invalid=c;memset(invalid.topic,'x',sizeof invalid.topic);assert(!config_valid(&invalid));
    invalid=c;memset(invalid.token,'x',sizeof invalid.token);assert(!config_valid(&invalid));
    puts("PASS: actual ntfy publish/poll: no redirect credential/body replay, HTTP failure cleanup, fail-closed auth allocation and token header validation");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-transport-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + config_type + buffer_type + callback + validation + transport + command_stub + poll + tests)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    libs = []
    cjson = os.environ.get('CJSON_SOURCE')
    if cjson:
        flags += ['-I', str(Path(cjson).parent), cjson]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True)
