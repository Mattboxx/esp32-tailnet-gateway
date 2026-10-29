"""Actual browser OTA handler with deterministic HTTP/flash/clock fixtures.

No device, real flash or transport. OTALOCAL_SANITIZE=1 enables host ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/'main/ota.c').read_text()
actual = source[source.index('static portMUX_TYPE s_writer_lock'):]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define HTTPD_400_BAD_REQUEST 400
#define HTTPD_408_REQ_TIMEOUT 408
#define HTTPD_500_INTERNAL_SERVER_ERROR 500
#define HTTPD_SOCK_ERR_TIMEOUT -3
#define OTA_SIZE_UNKNOWN ((size_t)-1)
#define OTA_HTTP_RX_BUF 2048
#define SNAP_UPLOAD 1
#define HIST_EV_UPDATE 1
#define HIST_INFO 1
#define pdMS_TO_TICKS(n) (n)
typedef int esp_err_t;
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(m) ((void)(m))
#define portEXIT_CRITICAL(m) ((void)(m))
typedef unsigned esp_ota_handle_t;
typedef struct {int content_len;} httpd_req_t;
typedef struct {size_t size;const char *label;unsigned long address;} esp_partition_t;
static const char *TAG="ota_local";
static esp_partition_t partition={8192,"ota_0",0x20000};
static int fault,recvs,begins,writes,ends,aborts,boots,errors,last_code,snapshots,logs;
static size_t consumed,written,begin_size;
static int64_t clock_us;
static void note(const char *tag,const char *fmt,...) {(void)tag;(void)fmt;logs++;}
#define ESP_LOGI(...) note(__VA_ARGS__)
#define ESP_LOGW(...) note(__VA_ARGS__)
#define ESP_LOGE(...) note(__VA_ARGS__)
static const char *esp_err_to_name(int e){(void)e;return "fixture error";}
static const esp_partition_t *esp_ota_get_next_update_partition(void *p){(void)p;return fault==15?NULL:&partition;}
static void settings_snapshot_before_update(int reason){assert(reason==SNAP_UPLOAD);snapshots++;}
static int esp_ota_begin(const esp_partition_t *p,size_t n,esp_ota_handle_t *h){assert(p==&partition);begins++;begin_size=n;if(fault==10)return -1;*h=1;return 0;}
static int esp_ota_write(esp_ota_handle_t h,const void *p,size_t n){assert(h==1&&p&&n);writes++;if(fault==7)return -1;written+=n;return 0;}
static int esp_ota_abort(esp_ota_handle_t h){assert(h==1);aborts++;return fault==8||fault==18?-1:0;}
static int esp_ota_end(esp_ota_handle_t h){assert(h==1);ends++;return fault==9?-1:0;}
static int esp_ota_set_boot_partition(const esp_partition_t *p){assert(p==&partition);boots++;return fault==11?-1:0;}
static void httpd_resp_send_err(httpd_req_t *r,int code,const char *s){assert(r&&s);errors++;last_code=code;}
static void httpd_resp_send_500(httpd_req_t *r){httpd_resp_send_err(r,500,"oom");}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){assert(r&&s);last_code=409;}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){assert(r&&s);}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){assert(r&&s);return fault==12?-1:0;}
static int64_t esp_timer_get_time(void){return clock_us;}
static void vTaskDelay(int ms){clock_us+=(int64_t)ms*1000;}
static void history_event(int a,int b,const char *fmt,...){assert(a==HIST_EV_UPDATE&&b==HIST_INFO&&fmt);}
static int httpd_req_recv(httpd_req_t *r,char *p,size_t n){
 recvs++;
 if ((fault==1&&recvs==1)||(fault==2&&recvs==2)||fault==3||(fault==4&&recvs%2)) {
  clock_us+=5000000;return HTTPD_SOCK_ERR_TIMEOUT;
 }
 if(fault==5||fault==8)return -1;
 if(fault==6)return 0;
 if(fault==19)clock_us+=5000000;
 if(n>63)n=63;
 if(n>(size_t)r->content_len-consumed)n=(size_t)r->content_len-consumed;
 memset(p,0xe9,n);consumed+=n;return (int)n;
}
static void *allocate(size_t n){return fault==17||fault==18?NULL:malloc(n);}
#define malloc allocate
'''
tests = r'''
#undef malloc
static void reset(void){
 fault=recvs=begins=writes=ends=aborts=boots=errors=last_code=snapshots=logs=0;
 consumed=written=begin_size=0;clock_us=0;s_writer_active=false;
}
int main(void){
 (void)esp_timer_get_time;(void)vTaskDelay;
 httpd_req_t r={1024};
 /* First regression reproduces the former abort-on-first-timeout bug. */
 reset();fault=1;assert(ota_upload_handler(&r)==ESP_OK);
 assert(written==1024&&consumed==1024&&begin_size==1024&&boots==1&&ends==1&&!aborts&&s_writer_active);
 for(int f=0;f<=4;f++){
  if(f==3)continue;
  reset();fault=f;assert(ota_upload_handler(&r)==ESP_OK);
  assert(written==1024&&begin_size==1024&&boots==1&&ends==1&&!aborts&&s_writer_active);
  if(f==4)assert(clock_us>30000000&&clock_us<600000000);
 }
 reset();fault=3;assert(ota_upload_handler(&r)!=ESP_OK);
 assert(!boots&&aborts==1&&!s_writer_active&&last_code==408&&clock_us>=30000000&&clock_us<36000000);
 for(int f=5;f<=7;f++){
  reset();fault=f;assert(ota_upload_handler(&r)!=ESP_OK);
  assert(!boots&&aborts==1&&!s_writer_active);
 }
 for(int f=8;f<=18;f++){
  if(f==12||f==13||f==14||f==16)continue;
  reset();fault=f;assert(ota_upload_handler(&r)!=ESP_OK);
  if(f==8||f==18){assert(aborts==1&&s_writer_active);assert(ota_upload_handler(&r)!=ESP_OK&&last_code==409&&aborts==1);}
  else assert(!s_writer_active);
  if(f!=11)assert(!boots);
 }
 reset();fault=12;assert(ota_upload_handler(&r)==ESP_OK&&boots==1&&s_writer_active); /* response loss cannot roll back committed boot */
 reset();r.content_len=8193;assert(ota_upload_handler(&r)!=ESP_OK&&last_code==400&&!begins);r.content_len=1024;
 reset();r.content_len=0;assert(ota_upload_handler(&r)!=ESP_OK&&last_code==400&&!begins);r.content_len=1024;
 reset();s_writer_active=true;assert(ota_upload_handler(&r)!=ESP_OK&&last_code==409&&!begins&&s_writer_active);
 reset();fault=19;r.content_len=8192;assert(ota_upload_handler(&r)!=ESP_OK&&last_code==408&&!boots&&aborts==1&&!s_writer_active);assert(clock_us>=600000000&&clock_us<610000000);
 puts("PASS actual local OTA: partial reads, timeout recovery, bounded idle/total deadlines, exact erase size, writer/abort exclusion, flash faults, committed response loss");
}
'''
with tempfile.TemporaryDirectory(prefix='ota-local-') as directory:
    p=Path(directory);(p/'test.c').write_text(fixture+actual+tests)
    flags=['-std=c11','-Wall','-Wextra','-Werror']
    if os.environ.get('OTALOCAL_SANITIZE')=='1':
        flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    binary=p/('test.exe' if os.name=='nt' else 'test')
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
