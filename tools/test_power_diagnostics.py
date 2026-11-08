"""Reset classification and TX-power save regressions on the actual sources.

Compiles the whole of main/reset_history.c against an in-memory NVS fixture
(which also counts writes, so a diagnostic change cannot add flash traffic per
boot) and the actual TX-power block of the /api/system save handler with the
pinned SDK cJSON. No board, NVS partition or radio is touched.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK = Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components'
CJSON = Path(os.environ.get('CJSON_SOURCE', SDK / 'json/cJSON/cJSON.c'))
# The pinned SDK's cJSON.c (Windows, CJSON_SOURCE) or the system libcjson
# through pkg-config (Linux CI), like the other cJSON-based drivers.
if CJSON.is_file():
    CJSON_SOURCES, CJSON_FLAGS, CJSON_LIBS = [CJSON], ['-I', str(CJSON.parent)], []
else:
    CJSON_SOURCES = []
    CJSON_FLAGS = subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
    CJSON_LIBS = subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()

STUBS = {
    'esp_err.h': '#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n'
                 '#define ESP_ERR_NO_MEM 0x101\n#define ESP_ERR_INVALID_ARG 0x102\n'
                 '#define ESP_ERR_NVS_NOT_FOUND 0x1102\n#define ESP_ERR_NVS_INVALID_LENGTH 0x110c\n',
    # Same order as ESP-IDF 5.5 esp_reset_reason_t.
    'esp_system.h': '#pragma once\n#include "esp_err.h"\ntypedef enum {ESP_RST_UNKNOWN,ESP_RST_POWERON,ESP_RST_EXT,'
                    'ESP_RST_SW,ESP_RST_PANIC,ESP_RST_INT_WDT,ESP_RST_TASK_WDT,ESP_RST_WDT,ESP_RST_DEEPSLEEP,'
                    'ESP_RST_BROWNOUT,ESP_RST_SDIO,ESP_RST_USB,ESP_RST_JTAG,ESP_RST_EFUSE,ESP_RST_PWR_GLITCH,'
                    'ESP_RST_CPU_LOCKUP} esp_reset_reason_t;\nesp_reset_reason_t esp_reset_reason(void);\n'
                    'void esp_restart(void);\n',
    'nvs.h': '#pragma once\n#include <stddef.h>\n#include <stdint.h>\n#include "esp_err.h"\ntypedef int nvs_handle_t;\n'
             'typedef enum {NVS_READONLY,NVS_READWRITE} nvs_open_mode_t;\n'
             'esp_err_t nvs_open(const char*,nvs_open_mode_t,nvs_handle_t*);void nvs_close(nvs_handle_t);\n'
             'esp_err_t nvs_get_str(nvs_handle_t,const char*,char*,size_t*);esp_err_t nvs_set_str(nvs_handle_t,const char*,const char*);\n'
             'esp_err_t nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);esp_err_t nvs_set_blob(nvs_handle_t,const char*,const void*,size_t);\n'
             'esp_err_t nvs_set_i32(nvs_handle_t,const char*,int32_t);esp_err_t nvs_erase_key(nvs_handle_t,const char*);\n'
             'esp_err_t nvs_commit(nvs_handle_t);\n',
    'nvs_params.h': '#pragma once\n#include "nvs.h"\n#define NVS_NAMESPACE "fixture"\n',
    'esp_log.h': '#pragma once\n#define ESP_LOGW(tag, ...) ((void)(tag))\n',
    'esp_app_desc.h': '#pragma once\n#include <stdint.h>\ntypedef struct {uint8_t app_elf_sha256[32];} esp_app_desc_t;\n'
                      'const esp_app_desc_t *esp_app_get_description(void);\n',
    'esp_ota_ops.h': '#pragma once\ntypedef struct {int unused;} esp_partition_t;\n'
                     'const esp_partition_t *esp_ota_get_last_invalid_partition(void);\n',
    'freertos/FreeRTOS.h': '#pragma once\n#define pdMS_TO_TICKS(x) (x)\n',
    'freertos/task.h': '#pragma once\nvoid vTaskDelay(int);\n',
}

RESET_CASES = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "reset_history.h"
#include "nvs.h"
#include "esp_app_desc.h"
#include "esp_ota_ops.h"

/* In-memory NVS: one namespace, typed entries, write counters. */
typedef struct {char key[16]; int type; unsigned char data[2048]; size_t len; int used;} item_t;
static item_t items[16];
static int sets, commits, open_ok = 1;
static esp_reset_reason_t raw;
static esp_app_desc_t app;
static esp_partition_t invalid_part;
static int rolled;
static item_t *find(const char *k){for(int i=0;i<16;i++)if(items[i].used&&!strcmp(items[i].key,k))return &items[i];return NULL;}
static esp_err_t put(const char *k,int type,const void *d,size_t n){item_t *it=find(k);
 if(!it){for(int i=0;i<16&&!it;i++)if(!items[i].used)it=&items[i];assert(it);memset(it,0,sizeof *it);it->used=1;snprintf(it->key,sizeof it->key,"%s",k);}
 assert(n<=sizeof it->data);it->type=type;memcpy(it->data,d,n);it->len=n;sets++;return ESP_OK;}
esp_reset_reason_t esp_reset_reason(void){return raw;}
void esp_restart(void){}
void vTaskDelay(int t){(void)t;}
const esp_app_desc_t *esp_app_get_description(void){return &app;}
const esp_partition_t *esp_ota_get_last_invalid_partition(void){return rolled?&invalid_part:NULL;}
esp_err_t nvs_open(const char *ns,nvs_open_mode_t m,nvs_handle_t *h){(void)ns;(void)m;*h=1;return open_ok?ESP_OK:ESP_FAIL;}
void nvs_close(nvs_handle_t h){(void)h;}
esp_err_t nvs_commit(nvs_handle_t h){(void)h;commits++;return ESP_OK;}
esp_err_t nvs_get_str(nvs_handle_t h,const char *k,char *o,size_t *n){(void)h;item_t *it=find(k);if(!it||it->type!=1)return ESP_ERR_NVS_NOT_FOUND;
 if(*n<it->len){return ESP_ERR_NVS_INVALID_LENGTH;}
 memcpy(o,it->data,it->len);*n=it->len;return ESP_OK;}
esp_err_t nvs_set_str(nvs_handle_t h,const char *k,const char *v){(void)h;return put(k,1,v,strlen(v)+1);}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *k,void *o,size_t *n){(void)h;item_t *it=find(k);if(!it||it->type!=2)return ESP_ERR_NVS_NOT_FOUND;
 if(!o){*n=it->len;return ESP_OK;}
 if(*n<it->len){return ESP_ERR_NVS_INVALID_LENGTH;}
 memcpy(o,it->data,it->len);*n=it->len;return ESP_OK;}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *k,const void *v,size_t n){(void)h;return put(k,2,v,n);}
esp_err_t nvs_set_i32(nvs_handle_t h,const char *k,int32_t v){(void)h;return put(k,3,&v,sizeof v);}
esp_err_t nvs_erase_key(nvs_handle_t h,const char *k){(void)h;item_t *it=find(k);if(!it)return ESP_ERR_NVS_NOT_FOUND;it->used=0;sets++;return ESP_OK;}

static void wipe(void){memset(items,0,sizeof items);sets=commits=0;open_ok=1;rolled=0;memset(&app,0,sizeof app);}
static void image(unsigned char id){memset(app.app_elf_sha256,id,sizeof app.app_elf_sha256);}
static reset_history_entry_t boot(esp_reset_reason_t r){raw=r;sets=commits=0;reset_history_record_boot();
 reset_history_entry_t row[RESET_HISTORY_MAX];assert(reset_history_load(row,RESET_HISTORY_MAX)>=1);return row[0];}
static const char *last_label(void){item_t *it=find("last_rst");assert(it);return (const char*)it->data;}

int main(void){
 /* Every IDF 5.5 code has the label the live status and persisted rows share. */
 static const char *labels[]={NULL,"POWERON","EXT","SW","PANIC","INT_WDT","TASK_WDT","WDT","DEEPSLEEP","BROWNOUT","SDIO","USB","JTAG","EFUSE","PWR_GLITCH","CPU_LOCKUP"};
 for(int r=0;r<=ESP_RST_CPU_LOCKUP;r++){const char *l=reset_history_reason_label((esp_reset_reason_t)r);
  assert(labels[r]?l&&!strcmp(l,labels[r]):l==NULL);}
 assert(reset_history_reason_label((esp_reset_reason_t)99)==NULL);
 static const int abnormal[]={ESP_RST_PANIC,ESP_RST_INT_WDT,ESP_RST_TASK_WDT,ESP_RST_WDT,ESP_RST_BROWNOUT,ESP_RST_EFUSE,ESP_RST_PWR_GLITCH,ESP_RST_CPU_LOCKUP};
 for(int r=0;r<=ESP_RST_CPU_LOCKUP;r++){bool want=false;for(size_t i=0;i<sizeof abnormal/sizeof *abnormal;i++)want|=abnormal[i]==r;
  assert(reset_history_reason_abnormal((esp_reset_reason_t)r)==want);}
 assert(!reset_history_reason_abnormal((esp_reset_reason_t)99));

 /* First boot of an image: FLASH; a plain USB/power-on flash reset adds no cause. */
 wipe();image(1);reset_history_entry_t e=boot(ESP_RST_POWERON);assert(!strcmp(e.reason,"FLASH")&&!e.who[0]);
 /* Same image afterwards: the hardware reason, including USB (was UNKNOWN). */
 e=boot(ESP_RST_USB);assert(!strcmp(e.reason,"USB")&&!strcmp(last_label(),"USB"));
 e=boot(ESP_RST_UNKNOWN);assert(!strcmp(e.reason,"UNKNOWN"));
 e=boot(ESP_RST_BROWNOUT);assert(!strcmp(e.reason,"BROWNOUT")&&!e.who[0]&&!e.crash[0]&&!strcmp(last_label(),"BROWNOUT"));
 /* Steady boot: blob + label + raw code, one commit, nothing else. */
 assert(sets==3&&commits==1);

 /* A brownout during the first boot of an OTA image: the bootloader rolled
  * back; the row keeps the cause in `who` without any extra NVS write. */
 image(2);rolled=1;e=boot(ESP_RST_BROWNOUT);
 assert(!strcmp(e.reason,"ROLLBACK")&&!strcmp(e.who,"after BROWNOUT")&&!strcmp(last_label(),"ROLLBACK"));
 assert(sets==4&&commits==1);   /* + the new image fingerprint, as before */
 image(3);rolled=0;e=boot(ESP_RST_TASK_WDT);assert(!strcmp(e.reason,"FLASH")&&!strcmp(e.who,"after TASK_WDT"));
 image(4);e=boot(ESP_RST_CPU_LOCKUP);assert(!strcmp(e.who,"after CPU_LOCKUP"));
 /* A requested OTA restart keeps its deliberate attribution. */
 image(5);put("rst_who",1,"web ota",8);e=boot(ESP_RST_SW);assert(!strcmp(e.reason,"FLASH")&&!strcmp(e.who,"web ota"));
 /* Stale attribution never survives a hardware reset. */
 put("rst_who",1,"cli restart",12);e=boot(ESP_RST_BROWNOUT);assert(!e.who[0]&&!find("rst_who"));
 image(6);e=boot(ESP_RST_EXT);assert(!strcmp(e.reason,"FLASH")&&!e.who[0]);

 /* Ring: newest first, bounded to ten rows, crash text only on crash rows. */
 wipe();image(7);boot(ESP_RST_POWERON);
 for(int i=0;i<12;i++)boot(i%2?ESP_RST_BROWNOUT:ESP_RST_PANIC);
 /* A brownout has no core dump: a stray crash line never shows on its row. */
 reset_history_set_current_crash("stale");
 reset_history_entry_t rows[RESET_HISTORY_MAX];assert(reset_history_load(rows,RESET_HISTORY_MAX)==RESET_HISTORY_MAX);
 assert(!strcmp(rows[0].reason,"BROWNOUT")&&!rows[0].crash[0]&&!strcmp(rows[1].reason,"PANIC"));
 boot(ESP_RST_PANIC);reset_history_set_current_crash("task=x pc=0x1");
 assert(reset_history_load(rows,RESET_HISTORY_MAX)==RESET_HISTORY_MAX);
 assert(!strcmp(rows[0].reason,"PANIC")&&!strcmp(rows[0].crash,"task=x pc=0x1")&&!strcmp(rows[1].reason,"BROWNOUT"));
 boot(ESP_RST_SW);assert(reset_history_load(rows,3)==3&&!strcmp(rows[0].reason,"SW")&&!rows[0].crash[0]&&!strcmp(rows[1].crash,"task=x pc=0x1"));
 assert(reset_history_load(rows,RESET_HISTORY_MAX)==RESET_HISTORY_MAX&&!rows[RESET_HISTORY_MAX-1].crash[0]);
 assert(reset_history_load(NULL,1)==0&&reset_history_load(rows,0)==0);

 /* NVS unavailable: recorder and loader degrade without writing. */
 open_ok=0;sets=0;reset_history_record_boot();assert(sets==0&&reset_history_load(rows,1)==0);
 puts("PASS actual reset history: shared labels incl. USB/JTAG/EFUSE/PWR_GLITCH/CPU_LOCKUP, abnormal set, "
      "cause kept behind ROLLBACK/FLASH, deliberate attribution, stale who, ring bound, crash column, "
      "per-boot write budget unchanged, NVS failure");
}
'''

web = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')
start = web.index('    const cJSON *tx_j = cJSON_GetObjectItem(root, "tx_power");')
tx_block = web[start:web.index('    /* Modem sleep applies live', start)]
TX_CASES = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "cJSON.h"
typedef int esp_err_t;
static int stored = -1, saves;   /* -1: key absent */
static esp_err_t nvs_param_get_u8(const char *k, uint8_t *v){assert(!strcmp(k,"tx_pwr"));if(stored<0)return 1;*v=(uint8_t)stored;return 0;}
static void nvs_save_u8(const char *k, uint8_t v){assert(!strcmp(k,"tx_pwr"));stored=v;saves++;}
static void run(const char *json, int before, int *tx_out, bool *restart_out){
 stored=before;saves=0;cJSON *root=cJSON_Parse(json);assert(root);
''' + tx_block + r'''
 *tx_out=tx_power;*restart_out=tx_default_restart;cJSON_Delete(root);}
int main(void){
 int tx;bool restart;
 run("{\"tx_power\":0}",60,&tx,&restart);assert(tx==0&&restart&&stored==0&&saves==1);
 run("{\"tx_power\":0}",0,&tx,&restart);assert(tx==0&&!restart&&stored==0);
 run("{\"tx_power\":0}",-1,&tx,&restart);assert(tx==0&&!restart&&stored==0);
 run("{\"tx_power\":-5}",80,&tx,&restart);assert(tx==0&&restart&&stored==0);
 run("{\"tx_power\":60}",-1,&tx,&restart);assert(tx==60&&!restart&&stored==60);
 run("{\"tx_power\":3}",-1,&tx,&restart);assert(tx==8&&!restart&&stored==8);
 run("{\"tx_power\":100}",8,&tx,&restart);assert(tx==84&&!restart&&stored==84);
 run("{\"tx_power\":44}",60,&tx,&restart);assert(tx==44&&!restart&&stored==44);
 run("{\"tx_power\":\"60\"}",60,&tx,&restart);assert(tx==-1&&!restart&&stored==60&&saves==0);
 run("{}",60,&tx,&restart);assert(tx==-1&&!restart&&stored==60&&saves==0);
 puts("PASS actual TX-power save block: default keeps no override, removing an override asks for a reboot, clamps, non-numbers ignored");
}
'''


def build_and_run(directory, name, sources, includes, extra_flags=(), libs=()):
    binary = directory / (name + ('.exe' if os.name == 'nt' else ''))
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if os.environ.get('POWER_DIAG_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    for inc in includes:
        flags += ['-I', str(inc)]
    flags += list(extra_flags)
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, *map(str, sources), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)


with tempfile.TemporaryDirectory(prefix='power-diag-') as tmp:
    d = Path(tmp)
    (d / 'freertos').mkdir()
    for name, text in STUBS.items():
        (d / name).write_text(text, encoding='utf-8')
    # Copies, so quoted includes resolve to the fixtures rather than main/.
    shutil.copy(ROOT / 'main/reset_history.c', d / 'reset_history.c')
    shutil.copy(ROOT / 'main/reset_history.h', d / 'reset_history.h')
    (d / 'reset_cases.c').write_text(RESET_CASES, encoding='utf-8')
    build_and_run(d, 'reset_cases', [d / 'reset_cases.c', d / 'reset_history.c'], [d])
    (d / 'tx_cases.c').write_text(TX_CASES, encoding='utf-8')
    build_and_run(d, 'tx_cases', [d / 'tx_cases.c', *CJSON_SOURCES], [], CJSON_FLAGS, CJSON_LIBS)
