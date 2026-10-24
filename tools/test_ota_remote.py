"""Real-C version/release guards and downloader failure paths, no device access.

Uses the SDK's cJSON source via CJSON_SOURCE, or system libcjson in Linux CI.
OTA_SANITIZE=1 enables ASan/UBSan. HTTP/flash/crypto calls are deterministic
fixtures: this tests transaction decisions, not TLS, cryptography or hardware.
"""
from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/ota_remote.c').read_text()
selector = 'bool ota_remote_select_release' + source.split('bool ota_remote_select_release', 1)[1].split('typedef struct { char *body', 1)[0]
installer = 'static bool image_matches' + source.split('static bool image_matches', 1)[1].split('static void worker(', 1)[0]
writer_source = (ROOT / 'main/ota.c').read_text()
writer = 'static portMUX_TYPE s_writer_lock' + writer_source.split('static portMUX_TYPE s_writer_lock', 1)[1].split('esp_err_t ota_upload_handler', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include "cJSON.h"
#include "ota_validation.h"
#define OTA_NOINLINE
#define ESP_OK 0
#define pdMS_TO_TICKS(x) (x)
#define portMAX_DELAY 0
#define ESP_IMAGE_HEADER_MAGIC 0xe9
#define ESP_CHIP_ID_ESP32S3 9
#define ESP_APP_DESC_MAGIC_WORD 0xabcd5432u
typedef int esp_err_t;
typedef pthread_mutex_t portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED PTHREAD_MUTEX_INITIALIZER
#define portENTER_CRITICAL(m) assert(!pthread_mutex_lock(m))
#define portEXIT_CRITICAL(m) assert(!pthread_mutex_unlock(m))
static size_t strlcpy(char *dst,const char *src,size_t cap) { size_t n=strlen(src); if(cap) { size_t k=n<cap-1?n:cap-1; memcpy(dst,src,k); dst[k]=0; } return n; }
typedef struct __attribute__((packed)) { uint8_t magic,pad[11]; uint16_t chip_id; uint8_t tail[10]; } esp_image_header_t;
typedef struct { uint32_t address,length; } esp_image_segment_header_t;
typedef struct { uint32_t magic_word,secure,pad[2]; char version[32],project_name[32]; uint8_t tail[176]; } esp_app_desc_t;
typedef struct { uint32_t size; } esp_partition_t;
typedef unsigned esp_ota_handle_t;
typedef struct { bool enabled,auto_install,beta_channel; int install_hour; char language[4]; } ota_remote_config_t;
typedef struct { ota_remote_config_t config; bool busy,checked,update_available; uint32_t last_check,asset_size; unsigned progress; uint8_t repo; char latest_version[32],status[96],release_url[192]; char asset[24]; } ota_remote_state_t;
static ota_remote_state_t s_state;
static unsigned char s_digest[32];
static int s_lock;
#define xSemaphoreTake(a,b) ((void)(a),(void)(b))
#define xSemaphoreGive(a) ((void)(a))
static void ota_remote_get_state(ota_remote_state_t *s) { *s=s_state; }
static void status_set(const char *s) { strlcpy(s_state.status,s,sizeof s_state.status); }
static esp_app_desc_t running={.version="0.1.31-Mattboxx-1.10-dev",.project_name="esp32-tailscale-subnet-router"};
static const esp_app_desc_t *esp_app_get_description(void) { return &running; }
static esp_partition_t partition={2048};
static const esp_partition_t *ota_flash_next_partition(void) { return &partition; }
static unsigned char image[1024];
static int opens,reads,offset,begins,writes,aborts,ends,boots,restarts,releases;
static int fault; /* 1 length,2 prefix EOF,3 hash,4 begin,5 write,6 end,7 boot,8 truncated,9 incomplete,10 redirect,11 allowed redirect,12 timeout,13 crypto */
typedef struct { char *body; size_t used; bool overflow; char *location; } http_buffer_t;
typedef http_buffer_t *esp_http_client_handle_t;
static esp_http_client_handle_t http_client(const char *url,http_buffer_t *b) { assert(ota_download_url_allowed(url)); return b; }
static int esp_http_client_open(esp_http_client_handle_t c,int n) { (void)c;(void)n; opens++; return ESP_OK; }
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c) {
    if(opens==1 && (fault==10 || fault==11)) strlcpy(c->location,fault==10?"https://evil.example/file":"https://release-assets.githubusercontent.com/github-production-release-asset/1/blob?sig=fixture",2048);
    return fault==1?1023:1024;
}
static int esp_http_client_get_status_code(esp_http_client_handle_t c) { (void)c; return opens==1&&(fault==10||fault==11)?302:200; }
static void esp_http_client_close(esp_http_client_handle_t c) { (void)c; }
static int esp_http_client_set_url(esp_http_client_handle_t c,const char *url) { (void)c; assert(ota_download_url_allowed(url)); return ESP_OK; }
static int esp_http_client_read(esp_http_client_handle_t c,char *b,int length) {
    (void)c; reads++; if(fault==2 || (fault==8&&reads>1)) return 0;
    if(length>73) length=73; /* exercise partial prefix and streaming reads */
    if(length>1024-offset) length=1024-offset;
    memcpy(b,image+offset,length); offset+=length; return length;
}
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c) { (void)c; return fault!=9&&offset==1024; }
static void esp_http_client_cleanup(esp_http_client_handle_t c) { (void)c; releases++; }
typedef struct { int used; } mbedtls_sha256_context;
static void mbedtls_sha256_init(mbedtls_sha256_context *h) { h->used=0; }
static void mbedtls_sha256_free(mbedtls_sha256_context *h) { (void)h; }
static int mbedtls_sha256_starts(mbedtls_sha256_context *h,int n) { (void)h;(void)n; return 0; }
static int mbedtls_sha256_update(mbedtls_sha256_context *h,const unsigned char *b,size_t n) { (void)b; h->used+=(int)n; return fault==13?-1:0; }
static int mbedtls_sha256_finish(mbedtls_sha256_context *h,unsigned char out[32]) { assert(h->used==1024); memset(out,fault==3?2:1,32); return 0; }
static int64_t clock_us;
static int64_t esp_timer_get_time(void) { clock_us+=fault==12?200000000:100; return clock_us; }
static esp_err_t ota_flash_begin(const esp_partition_t *p,size_t n,esp_ota_handle_t *h) { assert(p==&partition&&n==1024); begins++; if(fault==4)return -1; *h=1; return fault==16?-1:0; }
static esp_err_t ota_flash_write(esp_ota_handle_t h,const void *p,size_t n) { assert(h==1&&p&&n); writes++; return fault==5||fault==14?-1:0; }
static esp_err_t ota_flash_end(esp_ota_handle_t *h) { assert(*h==1); if(fault==15)return -1; ends++; *h=0; return fault==6?-1:0; }
static esp_err_t ota_flash_set_boot_partition(const esp_partition_t *p) { assert(p==&partition); boots++; return fault==7?-1:0; }
static esp_err_t ota_flash_abort(esp_ota_handle_t h) { assert(h==1); aborts++; return fault==14?-1:0; }
static void vTaskDelay(int t) { (void)t; }
static void ota_flash_restart(void) { restarts++; }
'''
tests = r'''
static void reset(void) {
    memset(&s_state,0,sizeof s_state); memset(image,0,sizeof image);
    s_state.checked=s_state.update_available=true; s_state.asset_size=1024;
    strcpy(s_state.latest_version,"v0.1.31-Mattboxx-1.10");
    strcpy(s_state.asset,OTA_ASSET);
    memset(s_digest,1,32);
    esp_image_header_t header={.magic=ESP_IMAGE_HEADER_MAGIC,.chip_id=ESP_CHIP_ID_ESP32S3};
    esp_app_desc_t app=running; app.magic_word=ESP_APP_DESC_MAGIC_WORD;
    strcpy(app.version,"0.1.31-Mattboxx-1.10");
    memcpy(image,&header,sizeof header); memcpy(image+32,&app,sizeof app);
    opens=reads=offset=begins=writes=aborts=ends=boots=restarts=releases=0;
    fault=0; clock_us=0; s_writer_active=false;
}
static void release_row(cJSON *rows,const char *tag,bool pre,bool draft,const char *file,const char *digest,int size) {
    cJSON *r=cJSON_CreateObject(),*assets=cJSON_AddArrayToObject(r,"assets"),*a=cJSON_CreateObject();
    cJSON_AddStringToObject(r,"tag_name",tag); cJSON_AddBoolToObject(r,"prerelease",pre); cJSON_AddBoolToObject(r,"draft",draft);
    cJSON_AddStringToObject(a,"name",file); cJSON_AddStringToObject(a,"state","uploaded");
    cJSON_AddStringToObject(a,"digest",digest); cJSON_AddNumberToObject(a,"size",size);
    cJSON_AddItemToArray(assets,a); cJSON_AddItemToArray(rows,r);
}
int main(void) {
    ota_version_t a,b; unsigned char digest[32];
    assert(ota_version_parse("v0.1.31-Mattboxx-1.10",&a));
    assert(ota_version_parse("0.1.31-Mattboxx-1.9",&b)); assert(ota_version_compare(&a,&b)>0);
    const char *invalid[]={"","v0.1.31","0.1.31-Mattboxx-1","0.1.31-Mattboxx-1.10-beta.","0.1.31-Mattboxx-1.10-pwn","0.1.31-Mattboxx-1.10/evil","0.1.31-Mattboxx-999999.1"};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];i++) assert(!ota_version_parse(invalid[i],&a));
    uint32_t rng=7;
    for(unsigned i=0;i<10000;i++) {
        char text[96]; unsigned n=i%95;
        for(unsigned j=0;j<n;j++) { rng=rng*1664525u+1013904223u; text[j]=(char)(33+(rng%90)); }
        text[n]=0; (void)ota_version_parse(text,&a);
    }
    const char *stages[]={"dev","alpha1","beta.1","rc2",""};
    for(int i=0;i<5;i++) { char v[32]; snprintf(v,sizeof v,"0.1.31-Mattboxx-1.10%s%s",i==4?"":"-",stages[i]); assert(ota_version_parse(v,&a)); if(i) assert(ota_version_compare(&a,&b)>0); b=a; }
    assert(ota_download_url_allowed(OTA_FORK_URL "/releases/download/v0.1.31-Mattboxx-1.10/" OTA_ASSET));
#ifdef ETH_VARIANT
    /* Variant isolation: the Ethernet build never accepts the WiFi image, and the reverse. */
    assert(!ota_download_url_allowed(OTA_FORK_URL "/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin"));
#else
    assert(!ota_download_url_allowed(OTA_FORK_URL "/releases/download/v0.1.31-Mattboxx-1.10/firmware-eth.bin"));
#endif
    /* Rename bridge: both fixed release paths, nothing that merely shares a prefix. */
    assert(!strcmp(ota_repo(0),OTA_REPO_CURRENT)&&!strcmp(ota_repo(1),OTA_REPO_PREVIOUS)&&!ota_repo(2));
    assert(ota_download_url_allowed("https://github.com/" OTA_REPO_PREVIOUS "/releases/download/v0.1.31-Mattboxx-1.10/" OTA_ASSET));
    const char *near[]={"https://github.com/Mattboxx/esp32-tailnet-gatewayX/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin",
        "https://github.com/Mattboxx/esp32-tailnet/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin",
        "https://github.com/Csontikka/esp32-tailscale-subnet-router/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin",
        "https://github.com/mattboxx/esp32-tailnet-gateway/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin",
        "https://github.com/" OTA_REPO_PREVIOUS "/releases/download/v0.1.31-Mattboxx-1.10/firmware.bin.sig"};
    for(unsigned i=0;i<sizeof near/sizeof near[0];i++) assert(!ota_download_url_allowed(near[i]));
    const char *bad[]={"http://github.com/x","https://github.com@evil.example/x","https://release-assets.githubusercontent.com.evil.example/github-production-release-asset/x","https://release-assets.githubusercontent.com:443/github-production-release-asset/x",OTA_FORK_URL "/releases/download/v0.1.31/firmware.bin",OTA_FORK_URL "/releases/download/v0.1.31-Mattboxx-1.10/firmware-factory.bin"};
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++) assert(!ota_download_url_allowed(bad[i]));
    const char *hash="sha256:1111111111111111111111111111111111111111111111111111111111111111";
    assert(ota_digest_parse(hash,digest)&&digest[0]==0x11); assert(!ota_digest_parse("sha256:123",digest));
    cJSON *rows=cJSON_CreateArray();
    release_row(rows,"v0.1.31-Mattboxx-1.11-beta.1",true,false,OTA_ASSET,hash,1024);
    release_row(rows,"v0.1.31-Mattboxx-1.10",false,false,OTA_ASSET,hash,1024);
    release_row(rows,"v0.1.99",false,false,OTA_ASSET,hash,1024);
    release_row(rows,"v0.1.31-Mattboxx-1.99",false,true,OTA_ASSET,hash,1024);
    release_row(rows,"v0.1.31-Mattboxx-1.98",false,false,"firmware-factory.bin",hash,1024);
    release_row(rows,"v0.1.31-Mattboxx-1.97",false,false,OTA_ASSET,"missing",1024);
    release_row(rows,"v0.1.31-Mattboxx-1.96",false,false,OTA_ASSET,hash,999999);
    char tag[32]; uint32_t size;
    assert(ota_remote_select_release(rows,running.version,false,OTA_ASSET,false,2048,tag,&size,digest)); assert(!strcmp(tag,"v0.1.31-Mattboxx-1.10")&&size==1024);
    assert(ota_remote_select_release(rows,running.version,true,OTA_ASSET,false,2048,tag,&size,digest)); assert(!strcmp(tag,"v0.1.31-Mattboxx-1.11-beta.1"));
    assert(!ota_remote_select_release(rows,"0.1.31-Mattboxx-1.11",true,OTA_ASSET,false,2048,tag,&size,digest));
    cJSON_Delete(rows);
    /* Product numbering from 2.0.0: newer than every legacy build, stages ordered,
     * ambiguous or malformed forms refused. */
    ota_version_t p1,p2,p3,l1,l2;
    assert(ota_version_parse("2.0.0",&p1)&&p1.scheme==1&&p1.stage==4);
    assert(ota_version_parse("v2.0.0-rc.1",&p2)&&p2.stage==3&&p2.serial==1);
    assert(ota_version_parse("2.0.1",&p3)&&ota_version_parse("0.1.38-Mattboxx-1.99",&l1)&&ota_version_parse("0.1.38-Mattboxx-1.14-dev.8",&l2));
    assert(ota_version_compare(&p1,&p2)>0&&ota_version_compare(&p3,&p1)>0&&ota_version_compare(&p2,&l1)>0&&ota_version_compare(&l1,&l2)>0);
    assert(ota_version_parse("99.0.0-Mattboxx-1.0",&l1)&&ota_version_compare(&p2,&l1)>0); /* scheme first */
    const char *bad2[]={"1.9.9","2.0","2.0.0-","2.0.0-rc.","2.0.0-pwn","2.0.0.1","v2.0.0/x","2.0.0-Mattboxx","200000.0.0"};
    for(unsigned i=0;i<sizeof bad2/sizeof bad2[0];i++) assert(!ota_version_parse(bad2[i],&a));
    rows=cJSON_CreateArray();
    release_row(rows,"v2.0.0-rc.1",true,false,OTA_ASSET,hash,1024);
    release_row(rows,"v2.0.0",false,false,OTA_ASSET,hash,1024);
    release_row(rows,"v0.1.38-Mattboxx-1.99",false,false,OTA_ASSET,hash,1024);
    /* A bridge (legacy numbering) device moves to the product release. */
    assert(ota_remote_select_release(rows,"0.1.38-Mattboxx-1.99",false,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.0"));
    assert(ota_remote_select_release(rows,"0.1.38-Mattboxx-1.13",false,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.0"));
    assert(ota_remote_select_release(rows,"2.0.0-rc.1",false,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.0"));
    assert(!ota_remote_select_release(rows,"2.0.0",true,OTA_ASSET,false,2048,tag,&size,digest));          /* never downgrade */
    cJSON_Delete(rows);
    /* Release policy: numbered betas of a version (2.0.4-beta.1, -beta.2, ...)
     * lead to its stable 2.0.4; the more advanced beta wins over an older one,
     * the stable wins over all its betas, the stable channel ignores betas. */
    ota_version_t b1,b2,s4,b5;
    assert(ota_version_parse("2.0.4-beta.1",&b1)&&ota_version_parse("2.0.4-beta.2",&b2)&&ota_version_parse("2.0.4",&s4)&&ota_version_parse("2.0.5-beta.1",&b5));
    assert(ota_version_compare(&b2,&b1)>0&&ota_version_compare(&s4,&b2)>0&&ota_version_compare(&b5,&s4)>0);
    rows=cJSON_CreateArray();
    release_row(rows,"v2.0.4-beta.1",true,false,OTA_ASSET,hash,1024);
    release_row(rows,"v2.0.4-beta.2",true,false,OTA_ASSET,hash,1024);
    release_row(rows,"v2.0.3",false,false,OTA_ASSET,hash,1024);
    assert(ota_remote_select_release(rows,"2.0.3",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4-beta.2"));   /* newest beta */
    assert(ota_remote_select_release(rows,"2.0.4-beta.1",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4-beta.2"));
    assert(!ota_remote_select_release(rows,"2.0.3",false,OTA_ASSET,false,2048,tag,&size,digest));            /* stable channel: no beta */
    release_row(rows,"v2.0.4",false,false,OTA_ASSET,hash,1024);
    assert(ota_remote_select_release(rows,"2.0.3",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4"));          /* stable beats its betas */
    assert(ota_remote_select_release(rows,"2.0.4-beta.2",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4"));
    assert(ota_remote_select_release(rows,"2.0.4-beta.2",false,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4"));   /* a beta device on the stable channel */
    assert(!ota_remote_select_release(rows,"2.0.4",true,OTA_ASSET,false,2048,tag,&size,digest));                                  /* no beta after its stable */
    release_row(rows,"v2.0.5-beta.1",true,false,OTA_ASSET,hash,1024);
    assert(ota_remote_select_release(rows,"2.0.4",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.5-beta.1"));    /* next version's beta: beta channel only */
    assert(!ota_remote_select_release(rows,"2.0.4",false,OTA_ASSET,false,2048,tag,&size,digest));
    release_row(rows,"v2.0.6-beta.1",false,false,OTA_ASSET,hash,1024);                                            /* a beta tag not marked pre-release is refused */
    assert(ota_remote_select_release(rows,"2.0.4",true,OTA_ASSET,false,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.5-beta.1"));
    cJSON_Delete(rows);
    /* Web UI language variants: each language has its own asset; the running
     * version is offered again only for another language, never an older one. */
    assert(!strcmp(ota_asset_for("en"),OTA_ASSET)&&!ota_asset_for("xx")&&!ota_asset_for(NULL)&&!ota_asset_for(""));
#ifdef ETH_VARIANT
    assert(!ota_asset_for("it")&&!ota_asset_for("zh"));   /* the Ethernet image is English only */
#else
    assert(!strcmp(ota_asset_for("it"),"firmware-it.bin")&&!strcmp(ota_asset_for("es"),"firmware-es.bin")&&!strcmp(ota_asset_for("zh"),"firmware-zh.bin"));
    assert(ota_download_url_allowed_for(OTA_FORK_URL "/releases/download/v2.0.4/firmware-it.bin","firmware-it.bin"));
    assert(!ota_download_url_allowed_for(OTA_FORK_URL "/releases/download/v2.0.4/firmware-it.bin","firmware.bin"));
    assert(!ota_download_url_allowed_for(OTA_FORK_URL "/releases/download/v2.0.4/firmware.bin","firmware-it.bin"));
    assert(!ota_download_url_allowed_for(OTA_FORK_URL "/releases/download/v2.0.4/firmware-it.bin",NULL));
    rows=cJSON_CreateArray();
    release_row(rows,"v2.0.4",false,false,"firmware.bin",hash,1024);
    release_row(rows,"v2.0.4",false,false,"firmware-it.bin",hash,1000);
    release_row(rows,"v2.0.3",false,false,"firmware-it.bin",hash,1024);
    assert(!ota_remote_select_release(rows,"2.0.4",false,"firmware-it.bin",false,2048,tag,&size,digest));          /* same language: up to date */
    assert(ota_remote_select_release(rows,"2.0.4",false,"firmware-it.bin",true,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4")&&size==1000);
    assert(!ota_remote_select_release(rows,"2.0.4",false,"firmware-es.bin",true,2048,tag,&size,digest));          /* no Spanish asset */
    assert(ota_remote_select_release(rows,"2.0.3",false,"firmware-it.bin",true,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.4"));
    assert(!ota_remote_select_release(rows,"2.0.5",false,"firmware-it.bin",true,2048,tag,&size,digest));          /* never downgrade */
    release_row(rows,"v2.0.5",false,false,"firmware-it.bin",hash,1024);
    assert(ota_remote_select_release(rows,"2.0.4",false,"firmware-it.bin",true,2048,tag,&size,digest)&&!strcmp(tag,"v2.0.5")); /* newer wins */
    assert(!ota_remote_select_release(rows,"2.0.4",false,NULL,true,2048,tag,&size,digest));
    cJSON_Delete(rows);
#endif
    reset(); s_state.repo=2; assert(!install_release()); assert(!opens&&!begins&&!s_writer_active);
    reset(); s_state.repo=1; assert(install_release()&&boots==1); /* previous name, before the rename */
    reset(); assert(ota_writer_try_acquire()); assert(!install_release()); assert(!opens&&!begins&&s_writer_active); ota_writer_release();
    for(int f=1;f<=16;f++) { if(f==11||f==14)continue; reset(); fault=f; assert(!install_release()); assert(!restarts&&!s_writer_active); if(f!=7)assert(!boots); assert(aborts<=1&&ends<=1); if(f==15||f==16)assert(aborts==1&&!ends); }
    /* Unacknowledged cleanup retains exclusion; repeated attempts cannot leak
     * more handles or write over an SDK transaction until explicit restart. */
    reset(); fault=14; assert(!install_release()&&s_writer_active&&aborts==1);
    assert(strstr(s_state.status,"restart"));
    fault=0; assert(!install_release()&&!ota_writer_try_acquire()&&aborts==1);
    for(int f=0;f<=11;f+=11) { reset(); fault=f; assert(install_release()); assert(boots==1&&restarts==1&&!aborts&&ends==1&&s_writer_active&&s_state.progress==100); }
    for(int f=0;f<3;f++) { reset(); if(f==0)image[12]=1; if(f==1)image[32+48]='!'; if(f==2)image[32+16]='!'; assert(!install_release()); assert(!begins&&!boots&&!restarts&&!s_writer_active); }
    puts("PASS: real-C fork version/channel/release selection, digest/URL guards, partial reads, exclusive writer, redirects, download/hash/image/flash failure cleanup and commit-before-reboot");
}
'''
for variant in ([], ['-DOTA_ASSET="firmware-eth.bin"', '-DETH_VARIANT']):
  with tempfile.TemporaryDirectory(prefix='ota-remote-') as directory:
      path = Path(directory)
      (path / 'test.c').write_text(fixture + writer + selector + installer + tests, encoding='utf-8')
      flags = ['-std=c11', '-pthread', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')] + variant
      libs = []
      cjson = os.environ.get('CJSON_SOURCE')
      if cjson:
          flags += ['-I', str(Path(cjson).parent), cjson]
      else:
          flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
          libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
      if os.environ.get('OTA_SANITIZE') == '1':
          flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
      binary = path / ('test.exe' if os.name == 'nt' else 'test')
      subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary), *libs], check=True)
      subprocess.run([str(binary)], check=True)

# Second program: actual check_release() repository lookup across the rename.
checker = 'static OTA_NOINLINE bool check_release' + source.split('static OTA_NOINLINE bool check_release', 1)[1].split('/* Check the app descriptor', 1)[0]
CHECK = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "ota_validation.h"
#define OTA_NOINLINE
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define JSON_LIMIT 4096u
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define portMAX_DELAY 0
#define xSemaphoreTake(a,b) ((void)(a),(void)(b))
#define xSemaphoreGive(a) ((void)(a))
typedef int esp_err_t;
static size_t strlcpy(char *d,const char *s,size_t n){size_t l=strlen(s);if(n){size_t k=l<n-1?l:n-1;memcpy(d,s,k);d[k]=0;}return l;}
typedef struct { bool enabled,auto_install,beta_channel; int install_hour; char language[4]; } ota_remote_config_t;
typedef struct { ota_remote_config_t config; bool busy,checked,update_available; uint32_t last_check,asset_size; unsigned progress; uint8_t repo; char latest_version[32],status[96],release_url[192]; char asset[24]; } ota_remote_state_t;
static ota_remote_state_t s_state; static unsigned char s_digest[32]; static int s_lock;
static void status_set(const char *s){strlcpy(s_state.status,s,sizeof s_state.status);}
typedef struct { char *body; size_t used; bool overflow; char *location; } http_buffer_t;
typedef http_buffer_t *esp_http_client_handle_t;
typedef struct { uint32_t size; } esp_partition_t;
typedef struct { char version[32]; } esp_app_desc_t;
static esp_partition_t part={1u<<20}; static esp_app_desc_t app={"0.1.38-Mattboxx-1.14-dev.6"};
static bool no_partition;
static const esp_partition_t *ota_flash_next_partition(void){return no_partition?NULL:&part;}
static const esp_app_desc_t *esp_app_get_description(void){return &app;}
static void *heap_caps_malloc(size_t n,int caps){(void)caps;return malloc(n);}
static int answers[3],calls; static char urls[3][128]; static int fail_transport;
static esp_http_client_handle_t http_client(const char *url,http_buffer_t *b){assert(calls<3);snprintf(urls[calls],sizeof urls[0],"%s",url);return b;}
static esp_err_t esp_http_client_perform(esp_http_client_handle_t c){
    if(fail_transport==calls+1){calls++;return ESP_FAIL;}
    if(answers[calls]==200)strcpy(c->body,"[{\"tag_name\":\"v0.1.38-Mattboxx-1.14\",\"prerelease\":false,\"draft\":false,\"assets\":[{\"name\":\"" OTA_ASSET "\",\"state\":\"uploaded\",\"size\":1024,\"digest\":\"sha256:1111111111111111111111111111111111111111111111111111111111111111\"}]}]");
    else strcpy(c->body,"{\"message\":\"Not Found\"}");
    c->used=strlen(c->body);calls++;return ESP_OK;}
static int esp_http_client_get_status_code(esp_http_client_handle_t c){(void)c;return answers[calls-1];}
static void esp_http_client_cleanup(esp_http_client_handle_t c){(void)c;}
static int time(void *p){(void)p;return 1800000000;}
bool ota_remote_select_release(const cJSON *releases,const char *running,bool beta,const char *asset,bool reinstall,uint32_t partition_size,char tag[32],uint32_t *size,unsigned char digest[32]);
''' + selector + checker + r'''
static bool run(int a,int b){memset(&s_state,0,sizeof s_state);strcpy(s_state.config.language,"en");calls=0;fail_transport=0;answers[0]=a;answers[1]=b;memset(urls,0,sizeof urls);return check_release();}
int main(void){
    /* After the rename: the current name answers; the previous one is never asked. */
    assert(run(200,0)&&calls==1&&s_state.repo==0&&s_state.update_available&&strstr(urls[0],"/repos/" OTA_REPO_CURRENT "/"));
    assert(!strcmp(s_state.release_url,"https://github.com/" OTA_REPO_CURRENT "/releases/tag/v0.1.38-Mattboxx-1.14"));
    /* Before the rename: 404 for the current name, then the previous name. */
    assert(run(404,200)&&calls==2&&s_state.repo==1&&strstr(urls[1],"/repos/" OTA_REPO_PREVIOUS "/"));
    assert(!strcmp(s_state.release_url,"https://github.com/" OTA_REPO_PREVIOUS "/releases/tag/v0.1.38-Mattboxx-1.14"));
    /* Any other failure of the current name never falls back (rate limit, 5xx, moved, transport). */
    int other[]={403,429,500,301};
    for(unsigned i=0;i<4;i++){assert(!run(other[i],200)&&calls==1&&!s_state.checked&&!s_state.update_available);}
    memset(&s_state,0,sizeof s_state);calls=0;answers[0]=200;fail_transport=1;assert(!check_release()&&calls==1);
    /* Both names missing: clean failure, nothing cached. */
    assert(!run(404,404)&&calls==2&&!s_state.checked&&!s_state.latest_version[0]);
    /* Unavailable executor or slot must not be presented as "up to date". */
    no_partition=true;
    assert(!run(200,0)&&calls==1&&!s_state.checked&&!s_state.update_available);
    assert(strstr(s_state.status,"unavailable")); no_partition=false;
    /* No asset for the chosen language: the check completes and offers nothing. */
    memset(&s_state,0,sizeof s_state);strcpy(s_state.config.language,"xx");calls=0;answers[0]=200;
    assert(check_release()&&!s_state.update_available&&!s_state.asset[0]);
    /* The found asset is remembered for the download. */
    assert(run(200,0)&&!strcmp(s_state.asset,OTA_ASSET));
    puts("PASS: actual release check across the repository rename: current first, previous only on 404, no fallback on other errors (fixtures)");
}
'''
with tempfile.TemporaryDirectory(prefix='ota-check-') as directory:
    path = Path(directory); (path / 'check.c').write_text(CHECK, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(ROOT / 'main')]
    libs = []
    cjson = os.environ.get('CJSON_SOURCE')
    if cjson:
        flags += ['-I', str(Path(cjson).parent), cjson]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('OTA_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('check.exe' if os.name == 'nt' else 'check')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'check.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--objdump')
parser.add_argument('--object', type=Path)
args = parser.parse_args()
if args.object:
    assert args.objdump, '--objdump is required with --object'
    disassembly = subprocess.check_output([args.objdump, '-d', str(args.object)], text=True)
    frames = {}
    for name, limit in {'worker': 768, 'check_release': 512, 'install_release': 1536}.items():
        match = re.search(rf'<{name}(?:[.$][^>]+)?>:\s*\n[^\n]*\bentry\s+a1,\s*(0x[\da-f]+|\d+)', disassembly)
        assert match, f'Missing separate updater frame: {name}'
        size = int(match[1], 0)
        assert size <= limit, f'Updater {name} frame {size} exceeds {limit}'
        frames[name] = size
    print('PASS: exact updater object frame budgets:', frames)
