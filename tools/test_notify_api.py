"""Actual notification POST parser + store, with synthetic HTTP/NVS fixtures.

Uses real cJSON/json_guard and the existing store fault-injection fixture.
This tests handler authorization dispatch, not real session/TLS/device NVS.
"""
import os
from pathlib import Path
import subprocess
import tempfile
from test_notify_store import PROGRAM as STORE, ESP_ERR

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/notify_channels.c').read_text(encoding='utf-8')
handlers = source[source.index('static bool copy_string('):source.index('static esp_err_t post_test(')]
fixture = r'''
#include "cJSON.h"
#include "json_guard.h"
#define portMAX_DELAY 0
#define MALLOC_CAP_SPIRAM 0
typedef struct {const char *body;int content_len,offset,status;bool authorized;} httpd_req_t;
static notify_config_t s_cfg;
static uint8_t s_mail_level, s_startup_channels;
static uint16_t s_link_grace_s=60, persisted_grace;
static int timing_error;
static int nvs_param_set_u16(const char *key,uint16_t value){assert(!strcmp(key,"ntf_grace"));if(timing_error)return ESP_FAIL;persisted_grace=value;return ESP_OK;}
static int s_lock, applied, allocations, fail_allocation;
static void xSemaphoreTake(int a,int b){(void)a;(void)b;}
static void xSemaphoreGive(int a){(void)a;}
static int web_ui_require_auth(httpd_req_t *r){return r->authorized?ESP_OK:ESP_FAIL;}
static int httpd_req_recv(httpd_req_t *r,char *s,int n){
 if(n>17)n=17;memcpy(s,r->body+r->offset,(size_t)n);r->offset+=n;return n;}
static void httpd_resp_send_500(httpd_req_t *r){r->status=500;}
static void httpd_resp_set_type(httpd_req_t *r,const char *t){(void)r;(void)t;}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){assert(s);if(!r->status)r->status=200;return ESP_OK;}
static const char *esp_err_to_name(int e){(void)e;return "injected failure";}
static void *heap_caps_malloc(size_t n,int cap){(void)cap;return ++allocations==fail_allocation?NULL:malloc(n);}
static void apply_locked(void){applied++;}
'''
tests = r'''
static void setup(void){reset();s_cfg=sample();s_mail_level=NOTIFY_PROBLEMS;s_startup_channels=0;
 applied=allocations=fail_allocation=0;assert(store_save(&s_cfg,s_mail_level,0)==ESP_OK);}
static int post(const char *body,bool authorized){httpd_req_t r={.body=body,.content_len=(int)strlen(body),.authorized=authorized};
 int e=post_notify(&r);if(!authorized)assert(e==ESP_FAIL&&r.offset==0);return r.status;}
int main(void){
 notify_config_t saved;uint8_t lv,startup;
 setup();assert(post("{\"telegram\":{\"notify_startup\":true}}",false)==0);
 assert(!s_startup_channels&&!applied&&!allocations);
 /* Startup choices do not enable a channel or widen its event selection. */
 setup();s_cfg.tg_enabled=false;
 assert(post("{\"telegram\":{\"notify_startup\":true}}",true)==200);
 assert(s_startup_channels==CH_TG&&!s_cfg.tg_enabled&&s_cfg.level==NOTIFY_PROBLEMS&&applied==1);
 store_load(&saved,&lv,&startup);assert(startup==CH_TG&&!saved.tg_enabled&&lv==NOTIFY_PROBLEMS);
 assert(post("{\"email\":{\"notify_startup\":true}}",true)==200);
 assert(s_startup_channels==(CH_TG|CH_MAIL));
 assert(post("{\"telegram\":{\"events\":\"all\",\"notify_startup\":false}}",true)==200);
 assert(s_startup_channels==CH_MAIL&&s_cfg.level==NOTIFY_ALL);
 assert(post("{\"telegram\":{\"notify_poweron\":true}}",true)==200);
 assert(s_startup_channels==(CH_MAIL|(CH_TG<<2)));
 assert(post("{\"telegram\":{\"notify_poweron\":false}}",true)==200&&s_startup_channels==CH_MAIL);
 /* Old clients omit the new field: preserve both explicit choices. */
 assert(post("{\"events\":\"problems\"}",true)==200&&s_startup_channels==CH_MAIL);
 assert(post("{\"email\":{\"events\":\"all\"}}",true)==200&&s_startup_channels==CH_MAIL);
 store_load(&saved,&lv,&startup);assert(startup==CH_MAIL&&lv==NOTIFY_ALL);
 const char *bad[]={"{\"telegram\":{\"notify_startup\":1}}","{\"email\":{\"notify_startup\":null}}",
 "{\"telegram\":{\"notify_poweron\":1}}","{\"telegram\":{\"notify_startup\":\"true\"}}","{\"email\":{\"notify_startup\":{}}}",
 "{\"email\":{\"notify_startup\":true,\"notify_startup\":false}}","{\"telegram\":[]}","{"};
 for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){
  setup();assert(post(bad[i],true)==400&&!s_startup_channels&&!applied);
  store_load(&saved,&lv,&startup);assert(!startup);
 }
 /* Failed durable writes never publish the requested switch in RAM. */
 for(unsigned phase=0;phase<3;phase++){
  setup();fail_open=phase==0;fail_set_blob=phase==1;commits=0;fail_commit_at=phase==2?1:0;
  assert(post("{\"telegram\":{\"notify_startup\":true}}",true)==500);
  assert(!s_startup_channels&&!applied);
 }
 for(int failure=1;failure<=2;failure++){
  setup();fail_allocation=failure;assert(post("{}",true)==500&&!applied&&!s_startup_channels);
 }
 /* Actual independent timing endpoint: range/types/auth and durable failure. */
 const char *timings[]={"{\"connectivity_grace_seconds\":15}","{\"connectivity_grace_seconds\":3600}"};
 for(unsigned i=0;i<2;i++){
  httpd_req_t r={.body=timings[i],.content_len=(int)strlen(timings[i]),.authorized=true};
  assert(post_timing(&r)==ESP_OK&&r.status==200&&persisted_grace==s_link_grace_s);
 }
 const char *invalid[]={"{}","{\"connectivity_grace_seconds\":14}","{\"connectivity_grace_seconds\":3601}",
 "{\"connectivity_grace_seconds\":1.5}","{\"connectivity_grace_seconds\":\"60\"}","{\"connectivity_grace_seconds\":null}",
 "{\"connectivity_grace_seconds\":60,\"connectivity_grace_seconds\":90}"};
 for(unsigned i=0;i<sizeof invalid/sizeof *invalid;i++){
  httpd_req_t r={.body=invalid[i],.content_len=(int)strlen(invalid[i]),.authorized=true};
  assert(post_timing(&r)==ESP_OK&&r.status==400&&s_link_grace_s==3600);
 }
 httpd_req_t denied={.body=timings[0],.content_len=(int)strlen(timings[0])};
 assert(post_timing(&denied)==ESP_FAIL&&!denied.offset);
 timing_error=1;httpd_req_t failure={.body=timings[0],.content_len=(int)strlen(timings[0]),.authorized=true};
 assert(post_timing(&failure)==ESP_OK&&failure.status==500&&s_link_grace_s==3600);
 puts("PASS actual notification POST: auth dispatch, independent startup choices, omitted-field preservation, type/duplicate refusal, persistence failures and OOM");
}
'''
with tempfile.TemporaryDirectory(prefix='notify-api-') as folder:
    path = Path(folder)
    (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
    (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
    c = path / 'api.c'
    c.write_text(STORE.split('int main(void){', 1)[0] + fixture + handlers + tests, encoding='utf-8')
    binary = path / ('api.exe' if os.name == 'nt' else 'api')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-misleading-indentation',
             '-I', str(path), '-I', str(ROOT / 'main')]
    libs = ['-lm']
    dep = os.environ.get('CJSON_SOURCE')
    if dep:
        flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('NOTIFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(c), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
