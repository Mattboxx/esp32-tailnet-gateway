"""Exercise actual ntfy publish/poll code with deterministic HTTP failures.

No external traffic or device access. NTFY_SANITIZE=1 enables ASan/UBSan.
Compiles the actual bounded stream parser alongside the transport functions.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/ntfy_integration.c').read_text()
header = (ROOT / 'main/ntfy_integration.h').read_text()
config_type = 'typedef struct {' + header.split('typedef struct {', 1)[1].split('} ntfy_integration_config_t;', 1)[0] + '} ntfy_integration_config_t;\n'
config_type += '_Static_assert(sizeof(ntfy_integration_config_t)==428,"configuration RAM size changed");\n'
buffer_type = '#define NTFY_POLL_BATCH' + source.split('#define NTFY_POLL_BATCH', 1)[1].split('static void defaults', 1)[0]
validation = 'static bool topic_valid' + source.split('static bool topic_valid', 1)[1].split('static void snapshot', 1)[0]
loading = 'static void defaults' + source.split('static void defaults', 1)[1].split('static bool topic_valid', 1)[0]
setter = 'esp_err_t ntfy_integration_set_config' + source.split('esp_err_t ntfy_integration_set_config', 1)[1].split('esp_err_t ntfy_integration_send_test', 1)[0]
transport = 'static void build_url' + source.split('static void build_url', 1)[1].split('static void appendf', 1)[0]
poll = 'static void collect_line' + source.split('static void collect_line', 1)[1].split('static bool uplink_connected', 1)[0]
fixture = r'''
#define _POSIX_C_SOURCE 200809L
#include "ntfy_events.h"
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include "ntfy_json_stream.h"
#define NTFY_NOINLINE
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 2
#define ESP_ERR_INVALID_ARG 3
#define ESP_ERR_NVS_NOT_FOUND 4
#define ESP_ERR_INVALID_STATE 5
/* Resource guard is OFF in this existing transport-boundary fixture. */
static bool homelab_ops_admit(void){return true;}
#define ESP_ERR_TIMEOUT 6
#define NVS_NAMESPACE "tsr"
#define NVS_READONLY 0
#define NVS_READWRITE 1
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
static int s_lock=1;
#define xSemaphoreTake(a,b) ((void)(a),(void)(b))
#define xSemaphoreGive(a) ((void)(a))
static struct { bool last_publish_ok; } s_status;
static char s_last_event_id[48];
static uint64_t s_config_generation;
static int s_task=1;
static void (*during_request)(void);
static void (*after_command)(void);
static size_t strlcpy(char *d,const char *s,size_t cap) { size_t n=strlen(s); if(cap) {size_t k=n<cap-1?n:cap-1;memcpy(d,s,k);d[k]=0;}return n; }
typedef struct { esp_http_client_config_t config; char authorization[176]; } fake_client_t;
typedef fake_client_t *esp_http_client_handle_t;
static fake_client_t client;
static int response_code=200, auth_failure, network_calls, foreign_requests, cleanups, commands, cursor_writes;
static const char *response = "{\"id\":\"fixture-id\",\"event\":\"message\",\"message\":\"info\"}\n";
static size_t read_position, read_chunk=512;
static int read_failure, open_failure_http, headers_failure;
static bool body_complete=true;
static int64_t esp_timer_get_time(void) { return 0; }
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
    if(during_request) during_request();
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
static esp_err_t esp_http_client_open(esp_http_client_handle_t c,int length) {
    (void)length;assert(c->config.method==HTTP_METHOD_GET);network_calls++;
    if(during_request)during_request();
    read_position=0;
    const char *since=strstr(c->config.url,"since=msg-");
    if(since) {
        unsigned index;assert(sscanf(since,"since=msg-%u",&index)==1);
        char match[64];snprintf(match,sizeof match,"\"id\":\"msg-%u\"",index);
        const char *at=strstr(response,match);assert(at);
        const char *end=strchr(at,'\n');assert(end);read_position=(size_t)(end-response)+1;
    }
    return open_failure_http?ESP_FAIL:ESP_OK;
}
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c) { (void)c;return headers_failure?-1:0; }
static int esp_http_client_read(esp_http_client_handle_t c,char *out,int size) {
    (void)c;if(read_failure)return -1;
    size_t left=strlen(response)-read_position;
    if(left>(size_t)size)left=(size_t)size;
    if(left>read_chunk)left=read_chunk;
    memcpy(out,response+read_position,left);read_position+=left;return (int)left;
}
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c) { (void)c;return body_complete; }
static void esp_http_client_cleanup(esp_http_client_handle_t c) { (void)c;cleanups++; }
static const char *esp_err_to_name(esp_err_t e) { (void)e;return "fixture error"; }
'''
storage_fixture = r'''
static ntfy_integration_config_t s_config, legacy_config;
static bool tailscale_enabled=true, connected, legacy_present;
static bool tailscale_is_connected(void) { return connected; }
typedef int nvs_handle_t;
static unsigned char stored[1024], pending[1024];
static size_t stored_size, pending_size;
static int open_failure, write_failure, commit_failure, nvs_closes;
static const char *legacy_token_override, *legacy_cursor_override;
static esp_err_t nvs_open(const char *name,int mode,nvs_handle_t *out) {
    assert(!strcmp(name,NVS_NAMESPACE));(void)mode;*out=1;
    return open_failure ? ESP_FAIL : ESP_OK;
}
static esp_err_t nvs_get_blob(nvs_handle_t n,const char *k,void *out,size_t *size) {
    (void)n;assert(!strcmp(k,"ntfy_state_v1"));
    if(!stored_size)return ESP_ERR_NVS_NOT_FOUND;
    if(*size<stored_size)return ESP_FAIL;
    memcpy(out,stored,stored_size);*size=stored_size;return ESP_OK;
}
static esp_err_t nvs_set_blob(nvs_handle_t n,const char *k,const void *data,size_t size) {
    (void)n;assert(!strcmp(k,"ntfy_state_v1")&&size<=sizeof stored);
    cursor_writes++;
    if(write_failure)return ESP_FAIL;
    memcpy(pending,data,size);pending_size=size;return ESP_OK;
}
static esp_err_t nvs_commit(nvs_handle_t n) {
    (void)n;if(commit_failure)return ESP_FAIL;
    memcpy(stored,pending,pending_size);stored_size=pending_size;return ESP_OK;
}
static void nvs_close(nvs_handle_t n) {(void)n;nvs_closes++;pending_size=0;}
static uint8_t sysev_value=0xff;static int sysev_failure;
static esp_err_t nvs_param_set_u8(const char *k,uint8_t v){assert(!strcmp(k,"ntfy_sysev")&&v<=3);if(sysev_failure)return ESP_FAIL;sysev_value=v;return ESP_OK;}
static esp_err_t nvs_param_get_u8(const char *k,uint8_t *out) {
    if(!legacy_present)return ESP_ERR_NVS_NOT_FOUND;
#define OLD_BOOL(key,field) if(!strcmp(k,key)){*out=legacy_config.field;return ESP_OK;}
    OLD_BOOL("ntfy_en",enabled) OLD_BOOL("ntfy_alert",tailscale_alerts)
    OLD_BOOL("ntfy_cmd",commands_enabled) OLD_BOOL("ntfy_down",commands_only_when_tailscale_down)
    OLD_BOOL("ntfy_mac",allow_direct_mac) OLD_BOOL("ntfy_info",info_enabled)
    OLD_BOOL("ntfy_infdet",info_include_details)
#undef OLD_BOOL
    assert(false);return ESP_FAIL;
}
static esp_err_t nvs_param_get_u16(const char *k,uint16_t *out) {
    if(!legacy_present)return ESP_ERR_NVS_NOT_FOUND;
    *out=!strcmp(k,"ntfy_delay")?legacy_config.failure_delay_seconds:legacy_config.poll_interval_seconds;
    return ESP_OK;
}
static int legacy_read_failure;
static esp_err_t nvs_param_get_str_buf(const char *k,char *out,size_t *size) {
    if(!legacy_present)return ESP_ERR_NVS_NOT_FOUND;
    if(legacy_read_failure)return ESP_FAIL;
    const char *value="legacy-id";
    if(!strcmp(k,"ntfy_srv"))value=legacy_config.server;
    else if(!strcmp(k,"ntfy_topic"))value=legacy_config.topic;
    else if(!strcmp(k,"ntfy_token"))value=legacy_token_override?legacy_token_override:legacy_config.token;
    else assert(!strcmp(k,"ntfy_last"));
    if(!strcmp(k,"ntfy_last")&&legacy_cursor_override)value=legacy_cursor_override;
    size_t length=strlen(value)+1;
    if(length>*size)return ESP_FAIL;
    memcpy(out,value,length);*size=length;return ESP_OK;
}
static esp_err_t ntfy_integration_set_config(const ntfy_integration_config_t *);
'''
command_stub = 'static void handle_command(const ntfy_integration_config_t *c,const char *s) {(void)c;assert(!strcmp(s,"info"));commands++;if(after_command)after_command();}\n'
tests = r'''
static int change_mode;
static void change_during_request(void) {
    ntfy_integration_config_t changed=s_config;
    if(change_mode==1) changed.enabled=false;
    if(change_mode==2) changed.commands_enabled=false;
    if(change_mode==3) strcpy(changed.topic,"new-topic");
    if(change_mode==4) strcpy(changed.server,"https://new.example");
    if(change_mode==5) strcpy(changed.token,"tk_new");
    if(change_mode==6) changed.commands_only_when_tailscale_down=true;
    if(change_mode==7) { changed.enabled=false;assert(ntfy_integration_set_config(&changed)==ESP_OK);changed.enabled=true; }
    if(change_mode==8) { connected=true;return; }
    assert(ntfy_integration_set_config(&changed)==ESP_OK);
    cursor_writes=0; /* Only count subsequent stale poll writes. */
}
static void reset(int code) {
    response_code=code; auth_failure=network_calls=foreign_requests=cleanups=commands=cursor_writes=0;
    s_last_event_id[0]=0;
    s_config_generation=0; during_request=after_command=NULL;
    connected=false;stored_size=pending_size=0;
    open_failure=write_failure=commit_failure=nvs_closes=0;
    read_chunk=512;read_failure=open_failure_http=headers_failure=0;body_complete=true;
}
int main(void) {
    assert(sizeof(command_batch_t)<8192);
    ntfy_integration_config_t c={.enabled=true,.commands_enabled=true,.failure_delay_seconds=120,.poll_interval_seconds=15};
    strcpy(c.server,"https://notify.example");strcpy(c.topic,"fixture");strcpy(c.token,"tk_fixture");
    assert(config_valid(&c));
    s_config=c;
    reset(200); assert(publish_message(&c,"Fixture","fixture","Synthetic data")==ESP_OK);
    assert(network_calls==1&&cleanups==1&&s_status.last_publish_ok);
    assert(!strcmp(client.authorization,"Bearer tk_fixture"));
    reset(200); poll_commands(&c); assert(network_calls==1&&cleanups==1&&commands==1&&cursor_writes==1);
    char backlog[16000];size_t backlog_size=0;
    for(unsigned i=0;i<200;i++) backlog_size+=(size_t)snprintf(backlog+backlog_size,sizeof backlog-backlog_size,
        "{\"id\":\"msg-%u\",\"event\":\"message\",\"message\":\"info\"}\n",i);
    assert(backlog_size>8192);response=backlog;
    reset(200);poll_commands(&c);assert(commands==NTFY_POLL_BATCH);
    for(unsigned attempt=0;attempt<10&&strcmp(s_last_event_id,"msg-199");attempt++)poll_commands(&c);
    assert(commands==200&&!strcmp(s_last_event_id,"msg-199"));
    char *large=malloc(200000);assert(large);
    const char *large_prefix="{\"attachment\":{\"padding\":\"";
    size_t large_at=strlen(large_prefix);strcpy(large,large_prefix);memset(large+large_at,'x',150000);
    strcpy(large+large_at+150000,"\"},\"id\":\"large-meta\",\"event\":\"message\",\"message\":\"info\"}\n");
    response=large;reset(200);read_chunk=11;poll_commands(&c);
    assert(commands==1&&!strcmp(s_last_event_id,"large-meta"));
    const char *message_prefix="{\"id\":\"large-message\",\"event\":\"message\",\"message\":\"";
    large_at=strlen(message_prefix);strcpy(large,message_prefix);memset(large+large_at,'x',150000);
    strcpy(large+large_at+150000,"\"}\n{\"id\":\"after-large\",\"event\":\"message\",\"message\":\"info\"}\n");
    response=large;reset(200);poll_commands(&c);
    assert(commands==1&&cursor_writes==2&&!strcmp(s_last_event_id,"after-large"));
    free(large);
    /* Arbitrary fragmentation must preserve complete events and Unicode. */
    response="{\"id\":\"chunked\",\"event\":\"message\",\"message\":\"\\u0069nfo\\n\"}\n";
    for(size_t chunk=1;chunk<70;chunk++) {
        reset(200);read_chunk=chunk;poll_commands(&c);assert(commands==1);
    }
    /* No commands/cursor on failed headers, reads or incomplete HTTP body. */
    for(int mode=0;mode<4;mode++) {
        reset(200);open_failure_http=mode==0;headers_failure=mode==1;
        read_failure=mode==2;body_complete=mode!=3;
        poll_commands(&c);assert(commands==0&&cursor_writes==0&&!s_last_event_id[0]);
    }
    response="{\"id\":\"self-reply\",\"event\":\"message\",\"title\":\"ESP32 reply\",\"message\":\"info\"}\n";
    reset(200);poll_commands(&c);assert(commands==0&&cursor_writes==1);
    response="{\"id\":\"no-newline\",\"event\":\"message\",\"message\":\"info\"}";
    reset(200);poll_commands(&c);assert(commands==1);
    response="{\"id\":\"truncated\",\"event\":\"message\",\"message\":\"info\"";
    reset(200);poll_commands(&c);assert(commands==0&&cursor_writes==0);
    response="{\"id\":\"fixture-id\",\"event\":\"message\",\"message\":\"info\"}\n";
    for(change_mode=1;change_mode<=7;change_mode++) {
        reset(200);s_config=c;during_request=change_during_request;poll_commands(&c);
        assert(network_calls==1&&cleanups==1&&commands==0&&cursor_writes==0&&!s_last_event_id[0]);
    }
    c.commands_only_when_tailscale_down=true;
    reset(200);s_config=c;change_mode=8;during_request=change_during_request;poll_commands(&c);
    assert(commands==0&&cursor_writes==0&&!s_last_event_id[0]);
    c.commands_only_when_tailscale_down=false;s_config=c;
    response="{\"id\":\"first-id\",\"event\":\"message\",\"message\":\"info\"}\n"
             "{\"id\":\"second-id\",\"event\":\"message\",\"message\":\"info\"}\n";
    for(change_mode=2;change_mode<=3;change_mode++) {
        reset(200);s_config=c;after_command=change_during_request;poll_commands(&c);
        assert(commands==1&&cursor_writes==0);
        assert(change_mode==2?!strcmp(s_last_event_id,"first-id"):!s_last_event_id[0]);
    }
    response="{\"id\":\"fixture-id\",\"event\":\"message\",\"message\":\"info\"}\n";
    reset(200);s_config=c;
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
        strcpy(c.token,bad[i]);assert(!config_valid(&c));s_config=c;
        reset(200); assert(publish_message(&c,NULL,NULL,"Synthetic data")==ESP_ERR_INVALID_ARG);
        assert(network_calls==0&&cleanups==1&&!s_status.last_publish_ok);
        reset(200); poll_commands(&c); assert(network_calls==0&&cleanups==1&&commands==0);
    }
    c.token[0]=0; assert(config_valid(&c));
    s_config=c;
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
    s_config=c;
    /* Missing, unsafe, oversized and query-injection IDs cannot execute. */
    const char *bad_ids[]={"", "bad&id=value", "bad%20id", "bad id", "12345678901234567890123456789012345678901234567890"};
    char wire[256];
    for(unsigned i=0;i<sizeof bad_ids/sizeof bad_ids[0];i++) {
        snprintf(wire,sizeof wire,"{\"id\":\"%s\",\"event\":\"message\",\"message\":\"info\"}\n",bad_ids[i]);
        response=wire;reset(200);poll_commands(&c);assert(commands==0&&cursor_writes==0);
    }
    response="{\"event\":\"message\",\"message\":\"info\"}\n";
    reset(200);poll_commands(&c);assert(commands==0&&cursor_writes==0);
    response="{\"id\":\"fixture-id\",\"event\":\"message\",\"message\":\"info\"}\n";
    /* Persistence errors defer dispatch and preserve the previous cursor. */
    for(int mode=0;mode<3;mode++) {
        reset(200);strcpy(s_last_event_id,"prior-id");
        open_failure=mode==0;write_failure=mode==1;commit_failure=mode==2;
        poll_commands(&c);assert(commands==0&&!strcmp(s_last_event_id,"prior-id"));
        assert(nvs_closes==(mode==0?0:1));
        open_failure=write_failure=commit_failure=0;
        poll_commands(&c);assert(commands==1&&!strcmp(s_last_event_id,"fixture-id"));
        poll_commands(&c);assert(commands==1); /* Same ID is not replayed. */
    }
    /* All configuration fields/cursor survive loading as a single value. */
    c.info_include_details=c.allow_direct_mac=c.tailscale_alerts=true;
    reset(200);s_config=c;strcpy(s_last_event_id,"prior-id");
    assert(ntfy_integration_set_config(&c)==ESP_OK);
    ntfy_integration_config_t loaded;
    load_state(&loaded);assert(config_equal(&c,&loaded)&&!strcmp(s_last_event_id,"prior-id"));
    ntfy_integration_config_t changed=c;strcpy(changed.topic,"changed");
    for(int mode=0;mode<3;mode++) {
        open_failure=mode==0;write_failure=mode==1;commit_failure=mode==2;
        assert(ntfy_integration_set_config(&changed)!=ESP_OK);
        assert(config_equal(&c,&s_config)&&!strcmp(s_last_event_id,"prior-id"));
        open_failure=write_failure=commit_failure=0;
        load_state(&loaded);assert(config_equal(&c,&loaded)&&!strcmp(s_last_event_id,"prior-id"));
    }
    assert(ntfy_integration_set_config(&changed)==ESP_OK);
    load_state(&loaded);assert(!strcmp(loaded.topic,"changed")&&!s_last_event_id[0]);
    /* System events live in a separate key: failure leaves both stores and RAM
     * unchanged; a failed main record reverts the separate key. */
    ntfy_integration_config_t events=changed;events.system_events=true;
    sysev_failure=1;assert(ntfy_integration_set_config(&events)!=ESP_OK&&!s_config.system_events&&sysev_value==0xff);sysev_failure=0;
    write_failure=1;assert(ntfy_integration_set_config(&events)!=ESP_OK&&!s_config.system_events&&sysev_value==0);write_failure=0;
    assert(ntfy_integration_set_config(&events)==ESP_OK&&s_config.system_events&&sysev_value==3);
    sysev_value=0x55;assert(ntfy_integration_set_config(&events)==ESP_OK&&sysev_value==0x55); /* unchanged flag: no extra write */
    events.system_events=false;assert(ntfy_integration_set_config(&events)==ESP_OK&&sysev_value==0&&!s_config.system_events);
    events.poweron_events=true;assert(ntfy_integration_set_config(&events)==ESP_OK&&sysev_value==2&&s_config.poweron_events&&!s_config.system_events);
    events.system_events=true;assert(ntfy_integration_set_config(&events)==ESP_OK&&sysev_value==1);
    events.poweron_events=false;write_failure=1;assert(ntfy_integration_set_config(&events)!=ESP_OK&&sysev_value==1&&s_config.poweron_events);write_failure=0;
    events.system_events=events.poweron_events=false;assert(ntfy_integration_set_config(&events)==ESP_OK&&sysev_value==0);
    /* Valid legacy settings migrate, but corrupt new data never falls back. */
    legacy_present=true;legacy_config=c;stored_size=0;
    load_state(&loaded);assert(config_equal(&c,&loaded)&&!strcmp(s_last_event_id,"legacy-id"));
    saved_ntfy_state_t corrupt;memcpy(&corrupt,stored,sizeof corrupt);
    saved_ntfy_state_t valid_saved=corrupt;
    for(int mode=0;mode<7;mode++) {
        corrupt=valid_saved;
        if(mode==0)corrupt.flags=128;
        if(mode==1)corrupt.schema=99;
        if(mode==2)memset(corrupt.token,'x',sizeof corrupt.token);
        if(mode==3)memset(corrupt.server,'x',sizeof corrupt.server);
        if(mode==4)memset(corrupt.cursor,'x',sizeof corrupt.cursor);
        if(mode==5)strcpy(corrupt.cursor,"bad&id=value");
        if(mode==6)corrupt.poll=0;
        memcpy(stored,&corrupt,sizeof corrupt);
        load_state(&loaded);assert(!loaded.enabled&&!s_last_event_id[0]);
    }
    stored_size=0;write_failure=1;load_state(&loaded);assert(!loaded.enabled);
    write_failure=0;load_state(&loaded);assert(loaded.enabled);
    stored_size=0;legacy_read_failure=1;load_state(&loaded);assert(!loaded.enabled&&!stored_size);
    legacy_read_failure=0;
    char large_legacy[256];memset(large_legacy,'x',sizeof large_legacy-1);large_legacy[255]=0;
    stored_size=0;legacy_token_override=large_legacy;
    load_state(&loaded);assert(!loaded.enabled&&!stored_size);
    legacy_token_override=NULL;legacy_cursor_override=large_legacy;
    load_state(&loaded);assert(loaded.enabled&&!s_last_event_id[0]);
    puts("PASS: actual ntfy transport/state: bounded streaming/resume, large events, fragmentation, partial/error refusal, redirects/auth, configuration changes, durable cursors and migration");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-transport-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture + config_type + storage_fixture + buffer_type + loading + validation + transport + command_stub + poll + setter + tests)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main'), str(ROOT / 'main/ntfy_json_stream.c')]
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
