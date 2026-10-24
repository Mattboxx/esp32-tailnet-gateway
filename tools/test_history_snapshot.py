"""Actual history and settings-copy cores of main/history.c and
main/settings_snapshot.c, with the real record ring, on simulated NOR flash.

History: sample packing, interval merging (lowest heap, summed traffic,
averaged RSSI/CPU, flags held, newest stamp), rate limiting, JSON escaping
and truncation, placing points in time across boots. Settings copies: slot
choice and rotation, exclusion, NVS changing during a copy, verified
headers, restore requests, damaged copies never reaching NVS, power cuts
and failing writes during a restore with bounded retries, delete and cancel.
The firmware wiring (esp_partition, tasks, HTTP, nvs_flash_init order) and
real flash are NOT covered. HIST_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def core(name, marker):
    text = (ROOT / 'main' / name).read_text(encoding='utf-8')
    return text.split(f'/* --- {marker} core (begin) --- */', 1)[1].split(f'/* --- {marker} core (end) --- */', 1)[0]


ESP_ERR = r'''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_CRC 0x109
'''
HTTPD = '#pragma once\ntypedef void *httpd_handle_t;\n'

FLASH = r'''
typedef struct {uint8_t *mem; uint32_t size; int fail_write, fail_erase, cut; void (*on_read)(uint32_t); unsigned erases;} fake_t;
static esp_err_t f_read(void *c, uint32_t at, void *out, size_t n){fake_t *f=c;assert(at+n<=f->size);memcpy(out,f->mem+at,n);if(f->on_read)f->on_read(at);return ESP_OK;}
static esp_err_t f_write(void *c, uint32_t at, const void *d, size_t n){
    fake_t *f=c;assert(at+n<=f->size);if(f->fail_write)return ESP_FAIL;
    size_t keep=n;if(f->cut>0&&(size_t)f->cut<n)keep=(size_t)f->cut;
    for(size_t i=0;i<keep;i++)f->mem[at+i]&=((const uint8_t*)d)[i];
    if(keep<n){f->cut=-1;return ESP_FAIL;}
    if(f->cut>0)f->cut-=(int)n;   /* counts down across writes */
    return ESP_OK;}
static esp_err_t f_erase(void *c, uint32_t at){fake_t *f=c;assert(at%STORE_SECTOR==0&&at<f->size);if(f->fail_erase)return ESP_FAIL;memset(f->mem+at,0xFF,STORE_SECTOR);f->erases++;return ESP_OK;}
'''

PROGRAM = r'''
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "history.h"
#include "settings_snapshot.h"
''' + core('storage_store.c', 'store') + core('history.c', 'history') + core('settings_snapshot.c', 'snapshot') + FLASH + r'''
#define STORAGE_SIZE (STORE_CONTROL_BASE + STORE_SECTOR)
#define NVS_SIZE 0x10000u
static uint8_t storage_mem[STORAGE_SIZE], nvs_mem[NVS_SIZE], buffer[STORE_SECTOR];
static fake_t fs = {storage_mem, STORAGE_SIZE, 0, 0, 0, NULL, 0}, fn = {nvs_mem, NVS_SIZE, 0, 0, 0, NULL, 0};
static const store_flash_t storage = {&fs, f_read, f_write, f_erase}, nvs = {&fn, f_read, f_write, f_erase};

static void fill_nvs(uint8_t seed){for(unsigned i=0;i<NVS_SIZE;i++)nvs_mem[i]=(uint8_t)(i*7+seed);}
static int changes_left;
static void nvs_writer(uint32_t at){if(changes_left>0&&at==NVS_SIZE-STORE_SECTOR){nvs_mem[100]^=0x55;changes_left--;}}
static uint32_t slot_data(unsigned s){return STORE_SNAPSHOT_BASE+s*STORE_SNAPSHOT_SLOT+0x1000u;}

static void history_tests(void){
    /* Packing round trip, including negative and extreme values. */
    history_sample_t s={.uptime=600,.wall=1700000600,.boot=7,.int_free=45527,.int_largest=31744,.psram_free=7000000,
                        .rx=UINT32_MAX,.tx=12,.rssi=-67,.cpu=42,.peers=9,.flags=HIST_UP_UPLINK|HIST_UP_TAILNET,.temp=-123};
    uint8_t packed[HIST_SAMPLE_BYTES];history_sample_t back;
    history_sample_pack(&s,packed);
    assert(history_sample_unpack(packed,sizeof packed,s.wall,s.uptime,&back));
    assert(back.boot==7&&back.int_free==45527&&back.rx==UINT32_MAX&&back.rssi==-67&&back.cpu==42&&back.peers==9&&back.flags==3&&back.temp==-123&&back.wall==s.wall);
    assert(!history_sample_unpack(packed,HIST_SAMPLE_BYTES-1,0,0,&back)&&!history_sample_unpack(NULL,HIST_SAMPLE_BYTES,0,0,&back));
    packed[3]=150;assert(!history_sample_unpack(packed,sizeof packed,0,0,&back));   /* impossible CPU % */

    /* Merging: lowest heap, summed traffic (saturating), averages ignore unknowns, flags held, newest stamp. */
    history_agg_t a;memset(&a,0,sizeof a);history_sample_t r;
    assert(!history_agg_result(&a,&r));
    history_sample_t x=s;x.uptime=660;x.int_free=40000;x.int_largest=40000;x.rx=5;x.rssi=-61;x.cpu=0xFF;x.peers=4;x.flags=HIST_UP_UPLINK;x.temp=INT16_MIN;
    history_sample_t y=s;y.uptime=540;y.rx=10;y.tx=8;y.rssi=0;y.cpu=10;y.psram_free=100;y.temp=77;
    history_agg_add(&a,&x);history_agg_add(&a,&s);history_agg_add(&a,&y);
    assert(history_agg_result(&a,&r)&&a.count==3);
    assert(r.int_free==40000&&r.int_largest==31744&&r.psram_free==100&&r.rx==UINT32_MAX&&r.tx==12+12+8);
    assert(r.rssi==-64&&r.cpu==26&&r.peers==9&&r.flags==HIST_UP_UPLINK&&r.temp==(-123+77)/2&&r.uptime==660);
    history_agg_t b;memset(&b,0,sizeof b);history_sample_t z=s;z.rssi=0;z.cpu=0xFF;z.temp=INT16_MIN;
    history_agg_add(&b,&z);assert(history_agg_result(&b,&r)&&r.rssi==0&&r.cpu==0xFF&&r.temp==INT16_MIN);
    history_sample_t later=s;later.boot=8;later.uptime=5;history_agg_add(&b,&later);
    assert(history_agg_result(&b,&r)&&r.boot==8&&r.uptime==5);                  /* a later boot is newer */

    /* Rate limit: a burst, then one line every 3 s, capped. */
    history_rate_t rate={0};unsigned ok=0;
    for(int i=0;i<50;i++)ok+=history_rate_allow(&rate,100);
    assert(ok==HIST_RATE_BURST&&!history_rate_allow(&rate,102)&&history_rate_allow(&rate,103)&&!history_rate_allow(&rate,103));
    ok=0;for(int i=0;i<50;i++)ok+=history_rate_allow(&rate,100000);assert(ok==HIST_RATE_BURST);
    assert(!history_rate_allow(&rate,99999));                                    /* time going back adds nothing */

    /* JSON escaping and truncation. */
    char out[64];
    assert(history_json_escape(out,sizeof out,"a\"b\\c\n\x01")==strlen("a\\\"b\\\\c\\u000a\\u0001")&&!strcmp(out,"a\\\"b\\\\c\\u000a\\u0001"));
    assert(history_json_escape(out,4,"ab\"c")==2&&!strcmp(out,"ab"));          /* never half an escape */
    assert(history_json_escape(out,5,"ab\xc3\xa9z")==4&&!strcmp(out,"ab\xc3\xa9"));
    assert(history_json_escape(out,4,"ab\xc3\xa9z")==2&&!strcmp(out,"ab"));    /* never half a UTF-8 letter */
    assert(history_json_escape(out,5,"a\xe2\x82\xac")==4&&!strcmp(out,"a\xe2\x82\xac"));
    assert(history_json_escape(out,4,"a\xe2\x82\xac")==1&&!strcmp(out,"a"));
    assert(history_json_escape(out,sizeof out,NULL)==0&&!out[0]&&history_json_escape(NULL,4,"x")==0);
    assert(!strcmp(history_kind_name(HIST_EV_CRASH),"crash")&&!strcmp(history_kind_name(999),"event")&&!strcmp(history_level_name(HIST_ERROR),"error"));

    /* Placing points in time. */
    uint32_t age;
    assert(history_point_age(0,5000,3,0,4000,3,&age)&&age==1000);              /* same boot, no clock */
    assert(!history_point_age(0,5000,3,0,4000,2,&age));                        /* other boot, no clock */
    assert(history_point_age(1700100000,50,3,1700000000,90000,2,&age)&&age==100000);
    assert(!history_point_age(1700000000,50,3,1700000100,10,2,&age));          /* from the future */
    assert(history_point_age(1700000000,50,3,0,60,3,&age)==false);             /* uptime ahead of now */
}

static void snapshot_tests(void){
    memset(storage_mem,0xFF,sizeof storage_mem);
    snap_header_t h;
    for(unsigned i=0;i<STORE_SNAPSHOT_SLOTS;i++)assert(!snap_read_header(&storage,i,&h));
    assert(!snap_read_header(&storage,3,&h)&&!snap_read_header(NULL,0,&h));
    assert(snap_take(&storage,&nvs,NVS_SIZE+STORE_SECTOR,1,"x",0,-1,buffer)==-1);   /* larger than a slot */
    assert(snap_take(&storage,&nvs,1000,1,"x",0,-1,buffer)==-1&&snap_take(&storage,&nvs,NVS_SIZE,1,"x",0,-1,NULL)==-1);

    /* Three copies fill the slots, the fourth replaces the oldest. */
    for(int i=0;i<3;i++){fill_nvs((uint8_t)i);assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"3.0.0",1700000000+i,-1,buffer)==i);}
    assert(snap_read_header(&storage,2,&h)&&h.seq==3&&h.wall==1700000002&&!strcmp(h.firmware,"3.0.0")&&h.reason==SNAP_MANUAL);
    fill_nvs(1);assert(!memcmp(storage_mem+slot_data(1),nvs_mem,NVS_SIZE));
    fill_nvs(9);assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_UPDATE,"3.0.1-with-a-very-long-version-string-here",0,-1,buffer)==0);
    assert(snap_read_header(&storage,0,&h)&&h.seq==4&&h.reason==SNAP_UPDATE&&strlen(h.firmware)==31);
    assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_BEFORE_RESTORE,"x",0,1,buffer)==2);   /* oldest is 1, excluded */

    /* NVS written during the copy: retried; never stable -> no copy, slot left invalid. */
    fn.on_read=nvs_writer;changes_left=1;fill_nvs(20);
    int slot=snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer);
    assert(slot==1&&!memcmp(storage_mem+slot_data(1),nvs_mem,NVS_SIZE));
    changes_left=100;assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer)==-1);
    fn.on_read=NULL;changes_left=0;
    assert(!snap_read_header(&storage,0,&h));                                    /* the target slot (oldest) stays invalid */
    /* A cut while writing the header leaves no valid copy. */
    fs.cut=10;assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer)==-1);fs.cut=0;
    fs.fail_erase=1;assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer)==-1);fs.fail_erase=0;
    /* A corrupted header is not a copy. */
    assert(snap_read_header(&storage,1,&h));storage_mem[STORE_SNAPSHOT_BASE+STORE_SNAPSHOT_SLOT+20]^=1;assert(!snap_read_header(&storage,1,&h));
    storage_mem[STORE_SNAPSHOT_BASE+STORE_SNAPSHOT_SLOT+20]^=1;

    /* Restore requests. */
    assert(!snap_restore_pending(&storage));
    unsigned which=99;
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_NONE&&which==99);
    assert(snap_request_restore(&storage,0,buffer)==ESP_ERR_INVALID_CRC);       /* empty slot */
    assert(snap_request_restore(&storage,5,buffer)==ESP_ERR_INVALID_ARG);
    storage_mem[slot_data(2)+7]^=0x10;assert(snap_request_restore(&storage,2,buffer)==ESP_ERR_INVALID_CRC);   /* damaged data */
    storage_mem[slot_data(2)+7]^=0x10;
    assert(snap_request_restore(&storage,1,buffer)==ESP_OK&&snap_restore_pending(&storage));
    fill_nvs(77);
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_RESTORED&&which==1);
    assert(!memcmp(nvs_mem,storage_mem+slot_data(1),NVS_SIZE)&&nvs_mem[100]==(uint8_t)((100*7+20)^0x55));
    static uint8_t want[NVS_SIZE];
    assert(!snap_restore_pending(&storage)&&snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_NONE);

    /* Damaged after the request: NVS untouched (fail closed), request dropped. */
    assert(snap_request_restore(&storage,2,buffer)==ESP_OK);
    storage_mem[slot_data(2)+NVS_SIZE-1]^=0x01;fill_nvs(55);memcpy(want,nvs_mem,NVS_SIZE);
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_INVALID&&!memcmp(want,nvs_mem,NVS_SIZE));
    assert(!snap_restore_pending(&storage));
    storage_mem[slot_data(2)+NVS_SIZE-1]^=0x01;
    /* Replaced after the request (another copy in that slot): refused. */
    assert(snap_request_restore(&storage,2,buffer)==ESP_OK);
    assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer)==0);
    assert(snap_take(&storage,&nvs,NVS_SIZE,SNAP_MANUAL,"x",0,-1,buffer)==2);
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_INVALID);
    /* Size mismatch with the running NVS partition: refused. */
    assert(snap_request_restore(&storage,2,buffer)==ESP_OK);
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE-STORE_SECTOR,buffer,&which)==SNAP_BOOT_INVALID);

    /* Failing NVS writes (power cut): the request stays, retried at most three times. */
    assert(snap_request_restore(&storage,2,buffer)==ESP_OK);
    fn.fail_write=1;
    for(int i=0;i<SNAP_RESTORE_ATTEMPTS;i++){assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_FAILED);assert(snap_restore_pending(&storage));}
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_GAVE_UP&&!snap_restore_pending(&storage));
    fn.fail_write=0;
    /* A cut in the middle of the NVS copy, then success at the next start. */
    assert(snap_request_restore(&storage,2,buffer)==ESP_OK);
    fn.cut=3*STORE_SECTOR+5;assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_FAILED);fn.cut=0;
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_RESTORED&&!memcmp(nvs_mem,storage_mem+slot_data(2),NVS_SIZE));
    /* A garbage control sector is dropped, never applied. */
    memset(storage_mem+STORE_CONTROL_BASE,0x5A,64);fill_nvs(3);memcpy(want,nvs_mem,NVS_SIZE);
    assert(snap_boot_restore(&storage,&nvs,NVS_SIZE,buffer,&which)==SNAP_BOOT_INVALID&&!memcmp(want,nvs_mem,NVS_SIZE));
    assert(storage_mem[STORE_CONTROL_BASE]==0xFF);

    /* Cancel and delete (the data, not only the header). */
    assert(snap_request_restore(&storage,0,buffer)==ESP_OK&&snap_cancel_restore(&storage)==ESP_OK&&!snap_restore_pending(&storage));
    assert(snap_request_restore(&storage,0,buffer)==ESP_OK&&snap_delete(&storage,0)==ESP_OK&&!snap_restore_pending(&storage));
    assert(!snap_read_header(&storage,0,&h));
    for(unsigned i=0;i<STORE_SNAPSHOT_SLOT;i++)assert(storage_mem[STORE_SNAPSHOT_BASE+i]==0xFF);
    assert(snap_read_header(&storage,1,&h)&&snap_read_header(&storage,2,&h));     /* the others stay */
    assert(snap_delete(&storage,3)==ESP_ERR_INVALID_ARG&&snap_delete(NULL,0)==ESP_ERR_INVALID_ARG);
    /* Copies never write outside their slots (events/metrics rings untouched). */
    for(unsigned i=0;i<STORE_SNAPSHOT_BASE;i++)assert(storage_mem[i]==0xFF);
}

int main(void){
    history_tests();
    snapshot_tests();
    puts("history + settings snapshot cores: ok");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='hist-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
        (path / 'esp_http_server.h').write_text(HTTPD, encoding='utf-8')
        (path / 'hist.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('hist.exe' if os.name == 'nt' else 'hist')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('HIST_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'hist.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=120)


if __name__ == '__main__':
    main()
