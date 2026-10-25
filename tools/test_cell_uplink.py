"""Actual cellular uplink core and HTTP API, no modem.

Compiles the real core, record loader and /api/cellular handlers of
main/cell_uplink.c with fixture NVS/HTTP: config validation (pins, APN,
PIN, data notice), AT response parsers, primary/failover selection,
fail-closed record load, write-only SIM PIN and password. UART, PPP and any
physical modem/SIM/carrier behavior are NOT covered.
CELL_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/cell_uplink.c').read_text(encoding='utf-8')
header = (ROOT / 'main/cell_uplink.h').read_text(encoding='utf-8')
types = 'enum {CELL_MODE_FAILOVER' + header.split('enum {CELL_MODE_FAILOVER', 1)[1].split('/* Core (pure, host-tested). */', 1)[0]
types += 'typedef struct {uint8_t streak;} cell_selector_t;\n#define CELL_STABLE_SAMPLES 3\n'
core = source.split('/* --- cell core (begin) --- */', 1)[1].split('/* --- cell core (end) --- */', 1)[0]


def function(text, signature):
    at = text.index(signature)
    return text[at:text.index('\n}', at) + 2] + '\n'


COMMON = r'''
#include <assert.h>
#include <ctype.h>
#include <math.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
'''

PROGRAM = COMMON + r'''
#define NVS_READONLY 0
#define NVS_NAMESPACE "tsr"
typedef int nvs_handle_t;
''' + types + core + r'''
static unsigned char blob[512];static size_t blob_size;static int open_fail;
static esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h){(void)ns;(void)mode;*h=1;return open_fail?ESP_FAIL:ESP_OK;}
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *k,void *out,size_t *n){(void)h;assert(!strcmp(k,"cell_cfg"));if(!blob_size)return ESP_FAIL;if(*n<blob_size){*n=blob_size;return ESP_FAIL;}memcpy(out,blob,blob_size);*n=blob_size;return ESP_OK;}
static void nvs_close(nvs_handle_t h){(void)h;}
''' + '#define CELL_MAGIC 0x43454c31u /* CEL1 */\n' \
    + 'typedef struct {uint32_t magic, version; cell_config_t config; uint32_t checksum;} cell_record_t;\n' \
    + ''.join(function(source, s) for s in ('static void defaults(', 'static uint32_t record_checksum(', 'static void load(')) + r'''
static cell_config_t good(void){cell_config_t c;defaults(&c);c.enabled=1;c.data_ack=1;strcpy(c.apn,"internet.example");return c;}
static bool valid(cell_config_t c){char why[96]="";bool ok=cell_config_valid(&c,why,sizeof why);assert(ok||why[0]);return ok;}
int main(void){
    cell_config_t d;defaults(&d);assert(!d.enabled&&valid(d)); /* the default record: off, no APN, no secrets */
    cell_config_t c=good();assert(valid(c));
    c.data_ack=0;assert(!valid(c));                                       /* never dial without the data notice */
    c=good();c.apn[0]=0;assert(!valid(c));c.enabled=0;assert(valid(c));
    c=good();strcpy(c.apn,"bad\"apn");assert(!valid(c));strcpy(c.apn,"bad\\apn");assert(!valid(c));strcpy(c.apn,"tab\tapn");assert(!valid(c));
    c=good();strcpy(c.user,"user\"x");assert(!valid(c));c=good();strcpy(c.password,"p\r\nATD");assert(!valid(c));
    c=good();strcpy(c.pin,"1234");assert(valid(c));strcpy(c.pin,"12345678");assert(valid(c));
    strcpy(c.pin,"123");assert(!valid(c));strcpy(c.pin,"12a4");assert(!valid(c));memset(c.pin,'1',sizeof c.pin);assert(!valid(c));
    int forbidden[]={0,3,19,20,26,33,37,38,39,40,43,44,45,46,49,-5};
    for(unsigned i=0;i<sizeof forbidden/sizeof *forbidden;i++){c=good();c.tx=(int8_t)forbidden[i];assert(!valid(c));}
    c=good();c.rx=-1;assert(!valid(c));c=good();c.rx=c.tx;assert(!valid(c));
    c=good();c.rts=5;assert(!valid(c));c.cts=6;assert(valid(c));c.cts=c.rts;assert(!valid(c));   /* RTS needs CTS */
    c=good();c.pwrkey=7;assert(valid(c));c.pwrkey=c.tx;assert(!valid(c));
    c=good();c.uart=0;assert(!valid(c));c.uart=3;assert(!valid(c));c.uart=2;assert(valid(c));
    c=good();c.baud=12345;assert(!valid(c));c.baud=921600;assert(valid(c));
    c=good();c.mode=2;assert(!valid(c));c=good();c.enabled=2;assert(!valid(c));c=good();c.roaming=2;assert(!valid(c));
    assert(!cell_config_valid(NULL,NULL,0));

    /* AT responses. */
    assert(cell_csq_to_dbm(0)==-113&&cell_csq_to_dbm(31)==-51&&!cell_csq_to_dbm(99)&&!cell_csq_to_dbm(32)&&!cell_csq_to_dbm(-1));
    assert(cell_parse_csq("+CSQ: 18,99\nOK\n")==18&&cell_parse_csq("+CSQ: 99,99\n")==99&&cell_parse_csq("+CSQ: x\n")==-1&&cell_parse_csq("OK\n")==-1&&cell_parse_csq(NULL)==-1);
    assert(cell_parse_reg("+CEREG: 0,1\nOK\n","+CEREG")==1&&cell_parse_reg("+CREG: 0,5\n","+CREG")==5);
    assert(cell_parse_reg("+CGREG: 2,1,\"1A2B\",\"01C2D3E4\",7\n","+CGREG")==1);
    assert(cell_parse_reg("+CEREG: 2\n","+CEREG")==2);                     /* URC form */
    assert(cell_parse_reg("+CEREG: 0,1\n","+CREG")==-1&&cell_parse_reg("+CGREG: 0,1\n","+CREG")==-1);   /* no prefix confusion */
    assert(cell_parse_reg("+CREG: 0,\n","+CREG")==-1&&cell_parse_reg("+CREG: 0,99\n","+CREG")==-1&&cell_parse_reg("ERROR\n","+CREG")==-1);
    assert(cell_parse_cpin("+CPIN: READY\nOK\n")==CELL_SIM_READY&&cell_parse_cpin("+CPIN: SIM PIN\n")==CELL_SIM_PIN);
    assert(cell_parse_cpin("+CPIN: SIM PUK\n")==CELL_SIM_PUK&&cell_parse_cpin("+CPIN: SIM PIN2\n")==CELL_SIM_OTHER);
    assert(cell_parse_cpin("+CPIN: SIM PUK2\n")==CELL_SIM_OTHER&&cell_parse_cpin("+CME ERROR: SIM not inserted\n")==CELL_SIM_OTHER);
    char name[12];
    assert(cell_parse_cops("+COPS: 0,0,\"vodafone IT\",7\n",name,sizeof name)&&!strcmp(name,"vodafone IT"));
    assert(cell_parse_cops("+COPS: 0,0,\"A very long operator\",7\n",name,sizeof name)&&strlen(name)==sizeof name-1);
    assert(!cell_parse_cops("+COPS: 0\n",name,sizeof name)&&!cell_parse_cops("+COPS: 0,0,\"\",7\n",name,sizeof name));
    assert(cell_parse_cops("+COPS: 0,0,\"x\x01y\",7\n",name,sizeof name)&&!strcmp(name,"x?y"));
    assert(cell_registered(1,false)&&!cell_registered(5,false)&&cell_registered(5,true)&&!cell_registered(2,true)&&!cell_registered(-1,true));

    /* Selection: failover only while the other uplink is down; primary after a stable window. */
    cell_selector_t s={0};
    assert(!cell_uplink_choose(&s,CELL_MODE_FAILOVER,true,true));
    assert(cell_uplink_choose(&s,CELL_MODE_FAILOVER,false,true));
    assert(!cell_uplink_choose(&s,CELL_MODE_FAILOVER,false,false)&&!s.streak);
    assert(!cell_uplink_choose(&s,CELL_MODE_FAILOVER,true,true));          /* back to WiFi/Ethernet at once */
    s=(cell_selector_t){0};
    for(int i=1;i<CELL_STABLE_SAMPLES;i++)assert(!cell_uplink_choose(&s,CELL_MODE_PRIMARY,true,true));
    assert(cell_uplink_choose(&s,CELL_MODE_PRIMARY,true,true));
    assert(!cell_uplink_choose(&s,CELL_MODE_PRIMARY,true,false)&&!s.streak);
    assert(cell_uplink_choose(&s,CELL_MODE_PRIMARY,false,true));           /* nothing else: cellular now */
    for(int i=0;i<300;i++)cell_uplink_choose(&s,CELL_MODE_PRIMARY,true,true);
    assert(s.streak==CELL_STABLE_SAMPLES);

    /* Record load: only a checksummed, valid v1 record; anything else is OFF. */
    cell_config_t g=good(),out;strcpy(g.pin,"4321");
    cell_record_t r={.magic=CELL_MAGIC,.version=1,.config=g};r.checksum=record_checksum(&r);
    memcpy(blob,&r,sizeof r);blob_size=sizeof r;load(&out);assert(!memcmp(&out,&g,sizeof g));
    cell_record_t bad=r;bad.checksum^=1;memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    bad=r;bad.version=2;bad.checksum=record_checksum(&bad);memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    bad=r;bad.config.data_ack=0;bad.checksum=record_checksum(&bad);memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    bad=r;bad.config.tx=33;bad.checksum=record_checksum(&bad);memcpy(blob,&bad,sizeof bad);load(&out);assert(!out.enabled);
    blob_size=sizeof r-1;memcpy(blob,&r,sizeof r);load(&out);assert(!out.enabled);
    blob_size=0;load(&out);assert(!out.enabled);open_fail=1;blob_size=sizeof r;load(&out);assert(!out.enabled);
    puts("PASS: actual cellular validation (pins, APN/user/password quoting, PIN, data notice), AT parsers, failover/primary selection, fail-closed record load (no modem)");
}
'''

HTTP = COMMON + r'''
#include "cJSON.h"
#include "json_guard.h"
#define HTTPD_400_BAD_REQUEST 400
typedef struct {int content_len,offset,status;const char *body;bool authorized;char reply[1024];} httpd_req_t;
struct in_addr {uint32_t s_addr;};
static char *inet_ntoa_r(struct in_addr a,char *b,size_t n){uint32_t x=a.s_addr;snprintf(b,n,"%u.%u.%u.%u",x&255,(x>>8)&255,(x>>16)&255,x>>24);return b;}
static const char *esp_err_to_name(esp_err_t e){(void)e;return "ESP_FAIL";}
static int web_ui_require_auth(httpd_req_t *r){if(r->authorized)return ESP_OK;r->status=401;return ESP_FAIL;}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);}
static void httpd_resp_send_err(httpd_req_t *r,int s,const char *m){(void)m;r->status=s;}
static void httpd_resp_send_408(httpd_req_t *r){r->status=408;}
static void httpd_resp_send_500(httpd_req_t *r){r->status=500;}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;}
static void httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){(void)r;(void)k;(void)v;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){snprintf(r->reply,sizeof r->reply,"%s",s);if(!r->status)r->status=200;return ESP_OK;}
static int httpd_req_recv(httpd_req_t *r,char *out,int n){memcpy(out,r->body+r->offset,n);r->offset+=n;return n;}
''' + types + 'bool cell_config_valid(const cell_config_t *c, char *why, size_t why_size);\n' + core + r'''
static cell_config_t stored;static cell_status_t status;static int saves;static esp_err_t save_result;
static void cell_uplink_get_config(cell_config_t *out){*out=stored;}
static void cell_uplink_get_status(cell_status_t *out){*out=status;}
static esp_err_t cell_uplink_set_config(const cell_config_t *c,char *why,size_t n){if(!cell_config_valid(c,why,n))return ESP_ERR_INVALID_ARG;saves++;if(save_result)return save_result;stored=*c;return ESP_OK;}
''' + 'static const char *const STATE_NAMES[] = {"off", "powering", "sync", "sim", "registering", "dialing", "connected", "backoff", "stopped"};\n' \
    + ''.join(function(source, s) for s in ('static esp_err_t send_json(', 'static esp_err_t get_cellular(', 'static bool json_int(',
                                             'static bool json_text(', 'static bool json_secret(', 'static esp_err_t post_cellular(')) + r'''
static httpd_req_t post(const char *body){httpd_req_t r={.content_len=(int)strlen(body),.body=body,.authorized=true};post_cellular(&r);return r;}
static httpd_req_t get(void){httpd_req_t r={.authorized=true};get_cellular(&r);return r;}
#define PINS "\"uart\":1,\"baud\":115200,\"tx\":17,\"rx\":18,\"rts\":-1,\"cts\":-1,\"pwrkey\":-1,\"pwrkey_active_high\":false"
#define ON "{\"enabled\":true,\"data_ack\":true,\"roaming\":false,\"mode\":\"failover\"," PINS ",\"apn\":\"internet.example\",\"user\":\"\""
int main(void){
    httpd_req_t r=post(ON ",\"pin\":\"1234\",\"password\":\"s3cret-pw\"}");
    assert(r.status==200&&strstr(r.reply,"restart_required")&&stored.enabled&&!strcmp(stored.pin,"1234")&&!strcmp(stored.password,"s3cret-pw"));
    /* GET never returns the secrets, only their presence. */
    r=get();assert(r.status==200&&!strstr(r.reply,"1234")&&!strstr(r.reply,"s3cret")&&strstr(r.reply,"\"has_pin\":true")&&strstr(r.reply,"\"has_password\":true"));
    assert(strstr(r.reply,"\"apn\":\"internet.example\"")&&strstr(r.reply,"\"rssi_dbm\":null")&&strstr(r.reply,"experimental"));
    /* Omitted or empty secrets keep the saved value; clear_* removes it. */
    r=post(ON "}");assert(r.status==200&&!strcmp(stored.pin,"1234")&&!strcmp(stored.password,"s3cret-pw"));
    r=post(ON ",\"pin\":\"\",\"password\":\"\"}");assert(r.status==200&&!strcmp(stored.pin,"1234"));
    r=post(ON ",\"clear_pin\":true,\"clear_password\":true}");assert(r.status==200&&!stored.pin[0]&&!stored.password[0]);
    r=post(ON ",\"pin\":\"9876\",\"mode\":\"primary\"}");assert(r.status==400);      /* duplicate key refused by json_guard */
    cell_config_t keep=stored;
    const char *bad[]={
        "{\"enabled\":true,\"data_ack\":false,\"roaming\":false,\"mode\":\"failover\"," PINS ",\"apn\":\"internet.example\",\"user\":\"\"}",
        ON ",\"pin\":\"12\"}", ON ",\"pin\":\"12345678901\"}", ON ",\"clear_pin\":1}", ON ",\"password\":7}",
        "{\"enabled\":true,\"data_ack\":true,\"roaming\":false,\"mode\":\"fastest\"," PINS ",\"apn\":\"x\",\"user\":\"\"}",
        "{\"enabled\":true,\"data_ack\":true,\"roaming\":false,\"mode\":\"failover\",\"uart\":1,\"baud\":115200,\"tx\":33,\"rx\":18,\"rts\":-1,\"cts\":-1,\"pwrkey\":-1,\"pwrkey_active_high\":false,\"apn\":\"x\",\"user\":\"\"}",
        "{\"enabled\":true,\"data_ack\":true,\"roaming\":false,\"mode\":\"failover\"," PINS ",\"apn\":\"a\\\"b\",\"user\":\"\"}",
        "{\"enabled\":1}", "[]", "{"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){r=post(bad[i]);assert(r.status==400&&!memcmp(&stored,&keep,sizeof keep));}
    save_result=ESP_FAIL;r=post(ON ",\"pin\":\"5555\"}");assert(r.status==500&&!memcmp(&stored,&keep,sizeof keep));save_result=ESP_OK;
    httpd_req_t denied={.content_len=2,.body="{}",.authorized=false};int before=saves;post_cellular(&denied);assert(denied.status==401&&saves==before);
    char big[900];memset(big,' ',sizeof big-1);big[sizeof big-1]=0;r=post(big);assert(r.status==400);
    puts("PASS: actual cellular API: typed fields, real validation, write-only SIM PIN/password (kept, replaced, cleared, never returned), 400/500/401 without saved-state change (fixtures)");
}
'''


def build_and_run(name, program, extra=()):
    with tempfile.TemporaryDirectory(prefix='cell-') as folder:
        path = Path(folder); (path / f'{name}.c').write_text(program, encoding='utf-8')
        binary = path / (f'{name}.exe' if os.name == 'nt' else name)
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-unused-variable', '-I', str(ROOT / 'main')]
        if os.name != 'nt':
            # glibc hides POSIX strnlen in strict C11 unless requested.
            flags += ['-D_POSIX_C_SOURCE=200809L']
        libs = ['-lm']
        if extra:
            dep = os.environ.get('CJSON_SOURCE')
            if dep: flags += ['-I', str(Path(dep).parent), dep]
            else:
                flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
                libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
        if os.environ.get('CELL_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / f'{name}.c'), '-o', str(binary), *libs], check=True)
        subprocess.run([str(binary)], check=True, timeout=30)


build_and_run('core', PROGRAM)
build_and_run('http', HTTP, extra=('cjson',))
