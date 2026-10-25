"""Actual main/nvs_flags.c (history and tailnet-name switches) on a fake NVS.

3.0.0/3.0.1 saved each switch in its own key: a failed later write left the
earlier ones changed while the page reported an error. Covered with fault
injection on every write: the one-byte record decides and is written first;
its failure changes nothing; legacy keys are written after it only for a
rollback and their failure does not fail the save; legacy-only devices
migrate (only an explicit 1 is on); damaged or out-of-range records read all
off; history (3 switches) and tailnet names (2) as declared in the firmware.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
history = (ROOT / 'main/history.c').read_text(encoding='utf-8')
names = (ROOT / 'main/tailnet_names.c').read_text(encoding='utf-8')
decl = (re.search(r'static const char \*const HISTORY_LEGACY\[\].*?;\nconst nvs_flags_t history_flags = .*?;', history, re.S).group(0) + '\n' +
        re.search(r'static const char \*const NAMES_LEGACY\[\].*?;\nconst nvs_flags_t tailnet_names_flags = .*?;', names, re.S).group(0))

ESP_ERR = '''#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_NVS_NOT_FOUND 0x1102
'''
NVS_PARAMS = '''#pragma once
#include <stdint.h>
#include "esp_err.h"
esp_err_t nvs_param_get_u8(const char *key, uint8_t *out);
esp_err_t nvs_param_set_u8(const char *key, uint8_t value);
'''
PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "nvs_flags.h"
#include "nvs_params.h"
/* fake NVS: up to 16 keys; writes can fail by key name or by position */
static struct {char key[16]; uint8_t v; int set;} kv[16];
static const char *fail_key; static int writes, fail_write_at;
static int find(const char *k){for(int i=0;i<16;i++)if(kv[i].set&&!strcmp(kv[i].key,k))return i;return -1;}
esp_err_t nvs_param_get_u8(const char *k, uint8_t *o){int i=find(k);if(i<0)return ESP_ERR_NVS_NOT_FOUND;*o=kv[i].v;return ESP_OK;}
esp_err_t nvs_param_set_u8(const char *k, uint8_t v){
    assert(strlen(k)<=15);   /* NVS key limit */
    if(++writes==fail_write_at||(fail_key&&!strcmp(fail_key,k)))return ESP_FAIL;
    int i=find(k);if(i<0)for(i=0;kv[i].set;i++);strcpy(kv[i].key,k);kv[i].v=v;kv[i].set=1;return ESP_OK;}
static void reset(void){memset(kv,0,sizeof kv);fail_key=NULL;writes=0;fail_write_at=0;}
static int value(const char *k){int i=find(k);return i<0?-1:kv[i].v;}
''' + decl + r'''
int main(void){
    const nvs_flags_t *h=&history_flags,*n=&tailnet_names_flags;
    assert(h->count==3&&n->count==2&&!strcmp(h->record,"hist_cfg")&&!strcmp(n->record,"tsn_cfg"));
    assert(!strcmp(h->legacy[0],"hist_ev")&&!strcmp(h->legacy[1],"hist_mx")&&!strcmp(h->legacy[2],"hist_snap"));
    assert(!strcmp(n->legacy[0],"tsn_en")&&!strcmp(n->legacy[1],"tsn_lan"));
    /* Nothing stored: everything off. */
    reset();assert(nvs_flags_load(h)==0&&nvs_flags_load(n)==0);
    /* Legacy-only device (3.0.0/3.0.1): migrate; only an explicit 1 is on. */
    nvs_param_set_u8("hist_ev",1);nvs_param_set_u8("hist_mx",0);nvs_param_set_u8("hist_snap",7);
    assert(nvs_flags_load(h)==1);
    /* Save: record first, then the rollback keys. */
    writes=0;assert(nvs_flags_save(h,6)==ESP_OK&&writes==4&&value("hist_cfg")==0x86);
    assert(value("hist_ev")==0&&value("hist_mx")==1&&value("hist_snap")==1&&nvs_flags_load(h)==6);
    /* Once the record exists the legacy keys never decide. */
    nvs_param_set_u8("hist_ev",1);assert(nvs_flags_load(h)==6);
    /* Record write fails: nothing changes, the error is reported. */
    fail_key="hist_cfg";writes=0;assert(nvs_flags_save(h,1)!=ESP_OK&&writes==1);fail_key=NULL;
    assert(nvs_flags_load(h)==6&&value("hist_mx")==1);
    /* A legacy write fails after the record: the save succeeds, the record decides. */
    for(int at=2;at<=4;at++){writes=0;fail_write_at=at;assert(nvs_flags_save(h,at==3?5:3)==ESP_OK);fail_write_at=0;
        assert(nvs_flags_load(h)==(at==3?5:3));}
    /* Bad arguments and damaged records. */
    assert(nvs_flags_save(h,8)==ESP_ERR_INVALID_ARG&&nvs_flags_save(n,4)==ESP_ERR_INVALID_ARG);
    reset();nvs_param_set_u8("hist_cfg",0x07);assert(nvs_flags_load(h)==0);          /* no record mark */
    reset();nvs_param_set_u8("hist_cfg",0x88);assert(nvs_flags_load(h)==0);          /* unknown switch */
    reset();nvs_param_set_u8("tsn_cfg",0x84);assert(nvs_flags_load(n)==0);
    reset();nvs_param_set_u8("tsn_cfg",0x83);nvs_param_set_u8("tsn_en",0);assert(nvs_flags_load(n)==3);
    /* Tailnet names round trip; history untouched by it. */
    reset();assert(nvs_flags_save(n,1)==ESP_OK&&nvs_flags_load(n)==1&&value("tsn_en")==1&&value("tsn_lan")==0&&nvs_flags_load(h)==0);
    /* Pure decoder edge: legacy absent (-1) and 0 are off. */
    int16_t lv[3]={-1,0,1};assert(nvs_flags_decode(h,false,0,lv)==4);
    puts("nvs flags: ok");return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='nvs-flags-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text(ESP_ERR, encoding='utf-8')
        (path / 'nvs_params.h').write_text(NVS_PARAMS, encoding='utf-8')
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('flags.exe' if os.name == 'nt' else 'flags')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('NVS_FLAGS_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), str(ROOT / 'main/nvs_flags.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)
        print('PASS: actual nvs_flags store: one-byte record first, failure changes nothing, rollback keys best effort, migration, damaged records off (fake NVS)')


if __name__ == '__main__':
    main()
