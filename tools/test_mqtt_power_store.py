"""Actual MQTT config/API paths with fake NVS/HTTP; not a device test."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
s = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
h = (ROOT / 'main/mqtt_integration.h').read_text(encoding='utf-8')
w = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
config = 'typedef struct {' + h.split('typedef struct {', 1)[1].split('} mqtt_integration_config_t;', 1)[0] + '} mqtt_integration_config_t;\n'
load = s[s.index('static void config_defaults'):s.index('static int publish(')]
save = s[s.index('esp_err_t mqtt_integration_set_config('):s.index('bool mqtt_integration_connected(')]
api = w[w.index('static esp_err_t mqtt_save_handler('):w.index('static const httpd_uri_t uri_mqtt =')]
program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "json_guard.h"
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG -2
#define ESP_MAC_WIFI_STA 0
#define portMAX_DELAY 0
#define HTTPD_400_BAD_REQUEST 400
''' + config + r'''
_Static_assert(sizeof(mqtt_integration_config_t)==496,"RAM footprint");
static mqtt_integration_config_t s_config;
static char s_device_id[24];static int s_lock,s_manager_task=1;
static unsigned writes,fail_at,notifications;static bool begin_fail,commit_fail;
static bool have_key,pending_have;static uint8_t stored_power,pending_power;
static size_t strlcpy(char *d,const char *s,size_t n){size_t z=strlen(s);if(n){size_t k=z<n-1?z:n-1;memcpy(d,s,k);d[k]=0;}return z;}
static void esp_read_mac(uint8_t *m,int kind){(void)kind;memset(m,0,6);}
static char *nvs_param_get_str(const char *k){(void)k;return NULL;}
static int nvs_param_get_u8(const char *k,uint8_t *v){if(!strcmp(k,"mqtt_pwr")&&have_key){*v=stored_power;return 0;}return -1;}
static int nvs_param_get_u16(const char *k,uint16_t *v){(void)k;(void)v;return -1;}
static int nvs_param_get_u32(const char *k,uint32_t *v){(void)k;(void)v;return -1;}
static int nvs_param_txn_begin(void){pending_have=have_key;pending_power=stored_power;return begin_fail?-1:0;}
static int write_step(void){return ++writes==fail_at?-1:0;}
static int nvs_param_set_u8(const char *k,uint8_t v){int e=write_step();if(!e&&!strcmp(k,"mqtt_pwr")){pending_have=true;pending_power=v;}return e;}
static int nvs_param_set_u16(const char *k,uint16_t v){(void)k;(void)v;return write_step();}
static int nvs_param_set_u32(const char *k,uint32_t v){(void)k;(void)v;return write_step();}
static int nvs_param_set_str(const char *k,const char *v){(void)k;(void)v;return write_step();}
static int nvs_param_txn_end(bool commit){if(commit&&!commit_fail){have_key=pending_have;stored_power=pending_power;}return commit_fail?-1:0;}
static void xSemaphoreTake(int l,int t){(void)l;(void)t;}
static void xSemaphoreGive(int l){(void)l;}
static void xTaskNotifyGive(int t){(void)t;notifications++;}
static bool wol_parse_mac(const char *s,uint8_t m[6]){(void)s;(void)m;return true;}
static void wol_format_mac(const uint8_t m[6],char s[18]){(void)m;strlcpy(s,"00:00:00:00:00:01",18);}
static void mqtt_integration_get_config(mqtt_integration_config_t *c){*c=s_config;}
typedef struct {const char *body;bool auth;int status;} httpd_req_t;
static int require_auth(httpd_req_t *r){if(!r->auth){r->status=401;return -1;}return 0;}
static char *malloc_body_buf(size_t n){return malloc(n);}
static int recv_body(httpd_req_t *r,char *s,size_t n,void *x){(void)x;assert(strlen(r->body)<n);strlcpy(s,r->body,n);return 0;}
static int httpd_resp_send_500(httpd_req_t *r){r->status=500;return 0;}
static int httpd_resp_send_err(httpd_req_t *r,int c,const char *s){(void)s;r->status=c;return 0;}
static int httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;return 0;}
static int httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);return 0;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){(void)r;(void)s;return 0;}
''' + load + save + api + r'''
int main(void){
 load_config();assert(!s_config.poweron_events&&!have_key);
 mqtt_integration_config_t initial=s_config,want=s_config;want.poweron_events=true;
 assert(mqtt_integration_set_config(&want)==0&&stored_power==1&&s_config.poweron_events&&notifications==1);
 unsigned count=writes;
 for(unsigned n=1;n<=count;n++){
  s_config=initial;have_key=false;stored_power=0;writes=0;fail_at=n;unsigned before=notifications;
  assert(mqtt_integration_set_config(&want)!=0&&!memcmp(&s_config,&initial,sizeof initial));
  assert(!have_key&&!stored_power&&notifications==before);
 }
 fail_at=0;writes=0;commit_fail=true;s_config=initial;have_key=false;
 assert(mqtt_integration_set_config(&want)!=0&&!have_key&&!s_config.poweron_events);commit_fail=false;
 begin_fail=true;writes=0;assert(mqtt_integration_set_config(&want)!=0&&!writes);begin_fail=false;
 for(unsigned v=0;v<256;v++){have_key=true;stored_power=v;load_config();assert(s_config.poweron_events==(v==1));}
 s_config=initial;const char *bad[]={"{\"poweron_events\":1}","{\"poweron_events\":\"ON\"}","{\"poweron_events\":null}","{\"poweron_events\":[]}","{\"poweron_events\":true,\"poweron_events\":false}"};
 for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){writes=0;httpd_req_t r={bad[i],true,200};mqtt_save_handler(&r);assert(r.status==400&&!writes&&!s_config.poweron_events);}
 writes=0;httpd_req_t denied={"{\"poweron_events\":true}",false,200};mqtt_save_handler(&denied);assert(denied.status==401&&!writes);
 httpd_req_t on={"{\"poweron_events\":true}",true,200};mqtt_save_handler(&on);assert(on.status==200&&s_config.poweron_events&&stored_power==1);
 httpd_req_t legacy={"{}",true,200};mqtt_save_handler(&legacy);assert(legacy.status==200&&s_config.poweron_events); /* omitted keeps current */
 httpd_req_t off={"{\"poweron_events\":false}",true,200};mqtt_save_handler(&off);assert(off.status==200&&!s_config.poweron_events&&stored_power==0);
 puts("PASS: actual MQTT load/store/API, absent/invalid key OFF, all NVS write faults and commit failure keep RAM/state, strict authenticated bool, omitted flag retained, config496B");
}
'''
with tempfile.TemporaryDirectory(prefix='mqtt-power-store-') as folder:
    p = Path(folder)
    (p / 'test.c').write_text(program, encoding='utf-8')
    binary = p / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    libs = []
    cjson = os.environ.get('CJSON_SOURCE')
    if cjson:
        flags += ['-I', str(Path(cjson).parent), cjson]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('MQTTPOWER_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(p / 'test.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
