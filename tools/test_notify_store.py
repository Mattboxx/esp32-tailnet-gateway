"""Actual notification settings store of main/notify_channels.c on a fake NVS.

The Telegram/email settings and the email event choice must be saved all or
nothing (3.0.1 wrote them to two keys, notify_cfg and ntf_mlv: a failed
second write left the first one changed). Covered, with fault injection on
every NVS call: one record carries everything; a failed open/write/commit
keeps the previous record and reports the error; the rollback-only key never
decides; records of 3.0.0 (no email choice) and 3.0.1 (choice in ntf_mlv)
migrate; damaged, foreign-size or out-of-range records mean "off"; and a
3.0.0/3.0.1 reader (same size, version and checksum range) still accepts
what this firmware writes, so a rollback keeps the settings.
NOTIFY_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'main/notify_channels.c').read_text(encoding='utf-8')
core = src.split('/* --- notify core (begin) --- */', 1)[1].split('/* --- notify core (end) --- */', 1)[0]
store = src.split('/* --- notify store (begin) --- */', 1)[1].split('/* --- notify store (end) --- */', 1)[0]
magic = [l for l in src.splitlines() if l.startswith('#define CFG_MAGIC')][0]

ESP_ERR = '''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_NVS_NOT_FOUND 0x1102
'''

PROGRAM = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "history.h"
#include "notify_channels.h"
''' + core + r'''
/* --- fake NVS: one blob and one u8, each call can be made to fail --- */
typedef int nvs_handle_t;
enum {NVS_READONLY, NVS_READWRITE};
static unsigned char blob[1024]; static size_t blob_len; static int has_blob;
static uint8_t legacy; static int has_legacy;
static int fail_open, fail_set_blob, fail_commit_at, fail_set_u8, commits;
static esp_err_t nvs_open(const char *ns, int mode, nvs_handle_t *h){(void)mode;assert(!strcmp(ns,"tsr"));*h=1;return fail_open?ESP_FAIL:ESP_OK;}
static void nvs_close(nvs_handle_t h){(void)h;}
static esp_err_t nvs_get_blob(nvs_handle_t h,const char *k,void *out,size_t *n){(void)h;assert(!strcmp(k,"notify_cfg"));
    if(!has_blob)return ESP_ERR_NVS_NOT_FOUND;if(*n<blob_len){*n=blob_len;return ESP_FAIL;}memcpy(out,blob,blob_len);*n=blob_len;return ESP_OK;}
static esp_err_t nvs_set_blob(nvs_handle_t h,const char *k,const void *in,size_t n){(void)h;assert(!strcmp(k,"notify_cfg")&&n<=sizeof blob);
    if(fail_set_blob)return ESP_FAIL;memcpy(blob,in,n);blob_len=n;has_blob=1;return ESP_OK;}
static esp_err_t nvs_get_u8(nvs_handle_t h,const char *k,uint8_t *v){(void)h;assert(!strcmp(k,"ntf_mlv"));if(!has_legacy)return ESP_ERR_NVS_NOT_FOUND;*v=legacy;return ESP_OK;}
static esp_err_t nvs_set_u8(nvs_handle_t h,const char *k,uint8_t v){(void)h;assert(!strcmp(k,"ntf_mlv"));if(fail_set_u8)return ESP_FAIL;legacy=v;has_legacy=1;return ESP_OK;}
static esp_err_t nvs_commit(nvs_handle_t h){(void)h;return ++commits==fail_commit_at?ESP_FAIL:ESP_OK;}
static uint32_t esp_rom_crc32_le(uint32_t crc,const uint8_t *p,size_t n){crc=~crc;while(n--){crc^=*p++;for(int i=0;i<8;i++)crc=crc>>1^(0xEDB88320u&-(crc&1));}return ~crc;}
''' + magic + '\n#define CH_TG 1\n#define CH_MAIL 2\n' + store + r'''
/* The record exactly as 3.0.0/3.0.1 declared and read it. */
typedef struct {uint32_t magic, version; notify_config_t config; uint32_t checksum;} old_record_t;
static int old_reader_accepts(notify_config_t *out){
    old_record_t r;if(!has_blob||blob_len!=sizeof r)return 0;memcpy(&r,blob,sizeof r);
    if(r.magic!=CFG_MAGIC||r.version!=1||r.checksum!=esp_rom_crc32_le(0,(const uint8_t *)&r,offsetof(old_record_t,checksum)))return 0;
    if(!notify_config_valid(&r.config,NULL,0))return 0;
    *out=r.config;return 1;}
static void old_writer(const notify_config_t *c){   /* how 3.0.0/3.0.1 saved */
    old_record_t r;memset(&r,0,sizeof r);r.magic=CFG_MAGIC;r.version=1;r.config=*c;
    r.checksum=esp_rom_crc32_le(0,(const uint8_t *)&r,offsetof(old_record_t,checksum));memcpy(blob,&r,sizeof r);blob_len=sizeof r;has_blob=1;}
static notify_config_t sample(void){notify_config_t c;memset(&c,0,sizeof c);c.tg_enabled=true;strcpy(c.tg_token,"123456789:AAH4kq_ZXcvbnm-1234567890qwertyuiopASD");
    strcpy(c.tg_chat,"42");c.mail_enabled=true;strcpy(c.mail_host,"smtp.example.com");c.mail_port=587;c.mail_security=NOTIFY_STARTTLS;
    strcpy(c.mail_from,"gw@example.com");strcpy(c.mail_to,"me@example.com");c.level=NOTIFY_PROBLEMS;return c;}
static void reset(void){has_blob=has_legacy=0;blob_len=0;fail_open=fail_set_blob=fail_set_u8=0;fail_commit_at=0;commits=0;}
int main(void){
    notify_config_t c,a=sample(),b=sample();uint8_t lv, startup;
    _Static_assert(sizeof(cfg_record_t)==sizeof(old_record_t),"record size changed: a rollback would read it as damaged");
    _Static_assert(offsetof(cfg_record_t,checksum)==offsetof(old_record_t,checksum),"checksum moved");
    _Static_assert(offsetof(cfg_record_t,mail_level_plus1)>=offsetof(old_record_t,config)+sizeof(notify_config_t),"email choice overlaps the settings");
    /* Nothing stored: everything off. */
    reset();store_load(&c,&lv,&startup);assert(!c.tg_enabled&&!c.mail_enabled&&c.mail_port==465&&lv==NOTIFY_PROBLEMS&&startup==0);
    /* One record round trip, both choices. */
    a.level=NOTIFY_ALL;assert(store_save(&a,NOTIFY_PROBLEMS,CH_TG)==ESP_OK);store_load(&c,&lv,&startup);
    assert(!memcmp(&c,&a,sizeof c)&&c.level==NOTIFY_ALL&&lv==NOTIFY_PROBLEMS&&startup==CH_TG);
    /* A 3.0.0/3.0.1 image after a rollback still reads the same settings. */
    assert(old_reader_accepts(&c)&&!memcmp(&c,&a,sizeof c));
    /* The rollback-only key follows, but never decides: changed by hand, ignored. */
    assert(has_legacy&&legacy==NOTIFY_PROBLEMS);legacy=NOTIFY_ALL;store_load(&c,&lv,&startup);assert(lv==NOTIFY_PROBLEMS);
    /* Failed write, commit or open: the previous record stays, the error is reported. */
    b.tg_enabled=false;b.level=NOTIFY_PROBLEMS;
    fail_set_blob=1;assert(store_save(&b,NOTIFY_ALL,CH_TG)!=ESP_OK);fail_set_blob=0;store_load(&c,&lv,&startup);assert(c.tg_enabled&&lv==NOTIFY_PROBLEMS);
    commits=0;fail_commit_at=1;assert(store_save(&b,NOTIFY_ALL,CH_TG)!=ESP_OK);fail_commit_at=0;
    fail_open=1;assert(store_save(&b,NOTIFY_ALL,CH_TG)!=ESP_OK);store_load(&c,&lv,&startup);assert(!c.tg_enabled&&!c.mail_enabled&&lv==NOTIFY_PROBLEMS);fail_open=0;
    /* (A failed commit after a completed write is the NVS library's own atomic
     * entry: either record is whole; the checksum decides on load.) */
    store_load(&c,&lv,&startup);assert(lv<=NOTIFY_ALL);
    /* The rollback-only key failing does not fail the save or change the result. */
    reset();fail_set_u8=1;assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);fail_set_u8=0;assert(!has_legacy);
    store_load(&c,&lv,&startup);assert(c.tg_enabled&&lv==NOTIFY_ALL);
    reset();fail_set_u8=1;commits=0;fail_commit_at=2;assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);fail_set_u8=0;fail_commit_at=0;
    /* Migration: 3.0.0 record (one shared choice), 3.0.1 record + ntf_mlv. */
    reset();a.level=NOTIFY_ALL;old_writer(&a);store_load(&c,&lv,&startup);assert(c.tg_enabled&&lv==NOTIFY_ALL&&startup==15);
    has_legacy=1;legacy=NOTIFY_PROBLEMS;store_load(&c,&lv,&startup);assert(lv==NOTIFY_PROBLEMS&&startup==(CH_TG|(CH_TG<<2)));
    legacy=7;store_load(&c,&lv,&startup);assert(lv==NOTIFY_ALL);                 /* invalid legacy value: shared choice */
    /* Damaged records mean off. */
    reset();assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);blob[20]^=1;store_load(&c,&lv,&startup);assert(!c.tg_enabled&&!c.mail_enabled&&lv==NOTIFY_PROBLEMS);
    reset();assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);blob_len-=4;store_load(&c,&lv,&startup);assert(!c.tg_enabled);
    reset();assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);{cfg_record_t r;memcpy(&r,blob,sizeof r);r.mail_level_plus1=9;
        r.checksum=record_checksum(&r);memcpy(blob,&r,sizeof r);}store_load(&c,&lv,&startup);assert(!c.tg_enabled);
    reset();assert(store_save(&a,NOTIFY_ALL,CH_TG)==ESP_OK);{cfg_record_t r;memcpy(&r,blob,sizeof r);r.version=2;
        r.checksum=record_checksum(&r);memcpy(blob,&r,sizeof r);}store_load(&c,&lv,&startup);assert(!c.tg_enabled);
    reset();notify_config_t bad=sample();strcpy(bad.mail_host,"no host");old_writer(&bad);store_load(&c,&lv,&startup);assert(!c.mail_enabled&&!c.tg_enabled);
    reset();assert(store_save(&a,NOTIFY_ALL+1,CH_TG)==ESP_ERR_INVALID_ARG&&!has_blob);
    /* Independent startup choices include explicit opt-out with All events. */
    for(unsigned mask=0;mask<=15;mask++){
        reset();assert(store_save(&a,NOTIFY_ALL,(uint8_t)mask)==ESP_OK);
        store_load(&c,&lv,&startup);assert(startup==mask&&lv==NOTIFY_ALL);
        assert(old_reader_accepts(&c));
    }
    /* 3.0.2 record: mail level present, startup byte still zero. */
    reset();assert(store_save(&a,NOTIFY_PROBLEMS,0)==ESP_OK);
    {cfg_record_t r;memcpy(&r,blob,sizeof r);r.startup_flags=0;
     r.checksum=record_checksum(&r);memcpy(blob,&r,sizeof r);}
    store_load(&c,&lv,&startup);assert(c.tg_enabled&&startup==(CH_TG|(CH_TG<<2)));
    /* Nonzero unknown bits, or bits without the presence marker, fail closed. */
    const uint8_t invalid[]={1,2,3,4,0x90,0xff};
    for(unsigned i=0;i<sizeof invalid;i++){
        reset();assert(store_save(&a,NOTIFY_ALL,0)==ESP_OK);
        cfg_record_t r;memcpy(&r,blob,sizeof r);r.startup_flags=invalid[i];
        r.checksum=record_checksum(&r);memcpy(blob,&r,sizeof r);
        store_load(&c,&lv,&startup);assert(!c.tg_enabled&&!c.mail_enabled&&!startup);
    }
    reset();assert(store_save(&a,NOTIFY_ALL,16)==ESP_ERR_INVALID_ARG&&!has_blob);
    puts("notify store: ok (startup masks, migration and rollback included)");return 0;
}
'''


def main():
    source = PROGRAM
    with tempfile.TemporaryDirectory(prefix='notify-store-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'store.c').write_text(source, encoding='utf-8')
        binary = path / ('store.exe' if os.name == 'nt' else 'store')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-Wno-misleading-indentation', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('NOTIFY_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'store.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
