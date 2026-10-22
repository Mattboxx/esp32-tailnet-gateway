"""Actual profile core: preview token, ordering, apply/undo/rollback faults.

Compiles the real core of main/config_profiles.c against fixture settings and
a fixture NVS record store. No device, NVS flash or HTTP server.
Set PROFILE_SANITIZE=1 on Linux to add ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/config_profiles.c').read_text(encoding='utf-8')
start = '#define PROFILE_MAGIC'
core = start + source.split(start, 1)[1].split('/* --- profile core (end) --- */', 1)[0]

STUBS = {
    'esp_err.h': '#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n'
                 '#define ESP_ERR_NO_MEM 0x101\n#define ESP_ERR_INVALID_ARG 0x102\n'
                 '#define ESP_ERR_INVALID_STATE 0x103\n#define ESP_ERR_NOT_FOUND 0x105\n',
    'esp_http_server.h': '#pragma once\ntypedef void *httpd_handle_t;\n',
}

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "config_profiles.h"
static profile_values_t settings;
static int fail_write_at=-1, fail_undo=0, fail_save_at=-1, writes, saves, reads_fail;
static char trace[64]; static unsigned trace_len;
static unsigned char stored[64]; static size_t stored_len;
''' + core.replace('/* --- profile core (begin) --- */', '') + r'''
static bool values_read(profile_values_t *out){if(reads_fail)return false;*out=settings;return true;}
static esp_err_t value_write(profile_key_t key,uint8_t value){
    assert(key<PK_COUNT&&value<=1);
    int n=writes++; trace[trace_len++]='w';
    if(n==fail_write_at)return ESP_ERR_NO_MEM;
    if(fail_undo&&value==0&&n>fail_write_at&&fail_write_at>=0)return ESP_FAIL;
    settings.value[key]=value;return ESP_OK;
}
static esp_err_t record_save(const profile_record_t *r){
    int n=saves++; trace[trace_len++]='s';
    if(n==fail_save_at)return ESP_FAIL;
    assert(record_valid(r));memcpy(stored,r,sizeof *r);stored_len=sizeof *r;return ESP_OK;
}
static void reset(void){
    memset(&settings,0,sizeof settings);record_defaults(&record);
    fail_write_at=-1;fail_undo=0;fail_save_at=-1;writes=saves=reads_fail=0;trace_len=0;memset(trace,0,sizeof trace);
}
static uint32_t token_for(profile_id_t p){profile_plan_t plan;assert(preview_locked(p,&plan)==ESP_OK);return plan.token;}
int main(void){
    profile_plan_t plan; profile_result_t r; profile_id_t id;
    reset();
    assert(config_profile_parse("monitoring",&id)&&id==PROFILE_MONITORING);
    assert(!config_profile_parse("none",&id)&&!config_profile_parse("Monitoring",&id)&&!config_profile_parse(NULL,&id));
    assert(!strcmp(config_profile_name(PROFILE_COUNT),"unknown"));
    assert(preview_locked(PROFILE_NONE,&plan)==ESP_ERR_INVALID_ARG&&preview_locked(PROFILE_COUNT,&plan)==ESP_ERR_INVALID_ARG);
    assert(preview_locked(PROFILE_MONITORING,&plan)==ESP_OK);
    assert(plan.change_mask==(1u<<PK_OPS_MONITORING|1u<<PK_HEALTH)&&plan.token);
    assert(preview_locked(PROFILE_GATEWAY,&plan)==ESP_OK&&plan.change_mask==1u<<PK_LEASE_NOTIFY);
    assert(preview_locked(PROFILE_IOT,&plan)==ESP_OK&&!plan.change_mask&&!plan.proposed_mask);
    assert(preview_locked(PROFILE_ADVANCED,&plan)==ESP_OK&&!plan.change_mask);
    for(unsigned p=0;p<PROFILE_COUNT;p++)assert(!(profile_wants[p]>>PK_COUNT));
    for(unsigned k=0;k<PK_COUNT;k++)assert(key_names[k]&&key_names[k][0]);
    reads_fail=1;assert(preview_locked(PROFILE_MONITORING,&plan)==ESP_FAIL);
    assert(apply_locked(PROFILE_MONITORING,1,&r)==ESP_FAIL&&!saves&&!writes);reads_fail=0;

    /* Token binds profile and state; mismatch changes nothing. */
    uint32_t mon=token_for(PROFILE_MONITORING),gw=token_for(PROFILE_GATEWAY);
    assert(mon!=gw);
    assert(apply_locked(PROFILE_RECOVERY,mon,&r)==ESP_ERR_INVALID_STATE&&!saves&&!writes);
    assert(apply_locked(PROFILE_MONITORING,0,&r)==ESP_ERR_INVALID_STATE);
    assert(apply_locked(PROFILE_NONE,mon,&r)==ESP_ERR_INVALID_ARG);
    settings.value[PK_LEASE_NOTIFY]=1;assert(apply_locked(PROFILE_MONITORING,mon,&r)==ESP_ERR_INVALID_STATE&&!writes);
    settings.value[PK_LEASE_NOTIFY]=0;

    /* Apply: backup persisted before any setting changes. */
    assert(apply_locked(PROFILE_MONITORING,mon,&r)==ESP_OK&&r.applied&&!r.rolled_back);
    assert(!strcmp(trace,"sww")&&settings.value[PK_OPS_MONITORING]&&settings.value[PK_HEALTH]&&!settings.value[PK_LEASE_NOTIFY]);
    assert(record.active==PROFILE_MONITORING&&record.has_backup&&record.applied_mask==r.changed_mask);
    assert(!memcmp(stored,&record,sizeof record));
    assert(apply_locked(PROFILE_MONITORING,mon,&r)==ESP_ERR_INVALID_STATE); /* replay refused */
    assert(token_for(PROFILE_MONITORING)!=mon);

    /* Operator turned health off since; rollback keeps that, restores the rest. */
    settings.value[PK_HEALTH]=0;trace_len=0;memset(trace,0,sizeof trace);
    assert(rollback_locked(&r)==ESP_OK&&r.rolled_back&&r.changed_mask==1u<<PK_OPS_MONITORING&&r.kept_mask==1u<<PK_HEALTH);
    assert(!strcmp(trace,"ws")&&!settings.value[PK_OPS_MONITORING]&&!record.has_backup&&record.active==PROFILE_NONE);
    assert(rollback_locked(&r)==ESP_ERR_NOT_FOUND);

    /* Never disables something already on, even on rollback. */
    reset();settings.value[PK_OPS_MONITORING]=1;
    assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_OK&&r.changed_mask==1u<<PK_HEALTH);
    assert(rollback_locked(&r)==ESP_OK&&settings.value[PK_OPS_MONITORING]==1&&!settings.value[PK_HEALTH]);
    reset();assert(apply_locked(PROFILE_ADVANCED,token_for(PROFILE_ADVANCED),&r)==ESP_OK&&!writes&&record.active==PROFILE_ADVANCED);
    assert(rollback_locked(&r)==ESP_OK&&record.active==PROFILE_NONE&&!writes);

    /* Backup save failure: nothing is touched. */
    reset();fail_save_at=0;
    assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_FAIL&&!writes&&!record.has_backup);

    /* Second setting fails: first undone, old record persisted, no backup left. */
    reset();fail_write_at=1;
    assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_ERR_NO_MEM&&r.rolled_back&&!r.partial);
    assert(!settings.value[PK_OPS_MONITORING]&&!settings.value[PK_HEALTH]&&!record.has_backup&&record.active==PROFILE_NONE);
    assert(!strcmp(trace,"swwws")); /* backup, ON, failed ON, undo, restore record */
    profile_record_t persisted;memcpy(&persisted,stored,sizeof persisted);assert(!persisted.has_backup);

    /* Undo also fails: truthful partial backup that rollback can still use. */
    reset();fail_write_at=1;fail_undo=1;
    assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_ERR_NO_MEM&&r.partial&&r.changed_mask==1u<<PK_OPS_MONITORING);
    assert(settings.value[PK_OPS_MONITORING]&&record.has_backup&&record.applied_mask==1u<<PK_OPS_MONITORING);
    fail_write_at=-1;fail_undo=0;
    assert(rollback_locked(&r)==ESP_OK&&!settings.value[PK_OPS_MONITORING]&&!record.has_backup);

    /* Rollback write failure re-applies what it undid and keeps the backup. */
    reset();assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_OK);
    fail_write_at=writes+1;
    assert(rollback_locked(&r)==ESP_ERR_NO_MEM&&!r.partial&&record.has_backup);
    assert(settings.value[PK_OPS_MONITORING]&&settings.value[PK_HEALTH]);
    /* Rollback record save failure: values restored, backup retained; retry converges. */
    fail_write_at=-1;fail_save_at=saves;
    assert(rollback_locked(&r)==ESP_FAIL&&r.partial&&record.has_backup&&!settings.value[PK_OPS_MONITORING]);
    fail_save_at=-1;assert(rollback_locked(&r)==ESP_OK&&r.kept_mask==(1u<<PK_OPS_MONITORING|1u<<PK_HEALTH)&&!record.has_backup);

    /* Single-level history: rollback returns to the previous profile only. */
    reset();assert(apply_locked(PROFILE_GATEWAY,token_for(PROFILE_GATEWAY),&r)==ESP_OK);
    assert(apply_locked(PROFILE_MONITORING,token_for(PROFILE_MONITORING),&r)==ESP_OK&&record.previous==PROFILE_GATEWAY);
    assert(rollback_locked(&r)==ESP_OK&&record.active==PROFILE_GATEWAY&&settings.value[PK_LEASE_NOTIFY]);
    assert(!settings.value[PK_OPS_MONITORING]&&!settings.value[PK_HEALTH]);

    /* Record validation rejects every malformed field. */
    profile_record_t v=record;v.checksum=record_checksum(&v);assert(record_valid(&v));
    profile_record_t bad=v;bad.checksum^=1;assert(!record_valid(&bad));
    bad=v;bad.active=PROFILE_COUNT;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.previous=200;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.applied_mask=1u<<PK_COUNT;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.previous_values[0]=2;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.reserved[0]=1;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.has_backup=2;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.version=2;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    bad=v;bad.magic=0;bad.checksum=record_checksum(&bad);assert(!record_valid(&bad));
    puts("PASS: actual profile preview/token binding, backup-before-change, undo/partial faults, non-destructive rollback, record validation (fixtures)");
}
'''

with tempfile.TemporaryDirectory(prefix='config-profiles-') as folder:
    path = Path(folder)
    for name, text in STUBS.items():
        (path / name).write_text(text, encoding='utf-8')
    (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
    if os.environ.get('PROFILE_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)

# Second program: actual POST /api/profiles parser and error mapping.
def function(signature):
    at = source.index(signature); return source[at:source.index('\n}', at) + 2] + '\n'
HTTP = r'''
#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "json_guard.h"
#include "config_profiles.h"
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_NOT_FOUND 0x105
struct httpd_req {int content_len,offset,status;const char *body;bool authorized;char reply[300];};
static const char *const key_names[PK_COUNT]={"device_monitoring","service_expiry_notifications","health_monitor"};
static const char *const profile_names[PROFILE_COUNT]={"none","gateway","recovery","iot","monitoring","advanced"};
const char *config_profile_name(profile_id_t p){return p<PROFILE_COUNT?profile_names[p]:"unknown";}
bool config_profile_parse(const char *n,profile_id_t *o){for(unsigned i=1;n&&i<PROFILE_COUNT;i++)if(!strcmp(n,profile_names[i])){*o=(profile_id_t)i;return true;}return false;}
static int applies,rollbacks;static uint32_t last_token;static profile_id_t last_profile;static esp_err_t apply_result,rollback_result;static profile_result_t canned;
esp_err_t config_profiles_apply(profile_id_t p,uint32_t t,profile_result_t *o){applies++;last_profile=p;last_token=t;*o=canned;return apply_result;}
esp_err_t config_profiles_rollback(profile_result_t *o){rollbacks++;*o=canned;return rollback_result;}
static const char *esp_err_to_name(esp_err_t e){(void)e;return "ERR";}
static int web_ui_require_auth(httpd_req_t *r){if(r->authorized)return ESP_OK;r->status=401;return ESP_FAIL;}
static void httpd_resp_set_status(httpd_req_t *r,const char *s){r->status=atoi(s);}
static void httpd_resp_set_type(httpd_req_t *r,const char *s){(void)r;(void)s;}
static void httpd_resp_set_hdr(httpd_req_t *r,const char *k,const char *v){(void)r;(void)k;(void)v;}
static void httpd_resp_send_500(httpd_req_t *r){r->status=500;}
static int httpd_resp_sendstr(httpd_req_t *r,const char *s){snprintf(r->reply,sizeof r->reply,"%s",s);if(!r->status)r->status=200;return ESP_OK;}
static int httpd_req_recv(httpd_req_t *r,char *out,int n){memcpy(out,r->body+r->offset,n);r->offset+=n;return n;}
''' + ''.join(function(s) for s in ('static esp_err_t send_json(', 'static bool add_keys(', 'static esp_err_t send_error(', 'static esp_err_t post_profiles(')) + r'''
static httpd_req_t post(const char *body){httpd_req_t r={.content_len=(int)strlen(body),.body=body,.authorized=true};post_profiles(&r);return r;}
int main(void){
    canned=(profile_result_t){.applied=true,.changed_mask=1u<<PK_HEALTH};
    httpd_req_t r=post("{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":4294967295}");
    assert(r.status==200&&applies==1&&last_profile==PROFILE_MONITORING&&last_token==4294967295u&&strstr(r.reply,"\"changed\":[\"health_monitor\"]"));
    const char *bad[]={"{\"action\":\"apply\",\"profile\":\"none\",\"token\":5}","{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":0}",
        "{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":4294967296}","{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":1.5}",
        "{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":\"5\"}","{\"action\":\"apply\",\"profile\":\"monitoring\"}",
        "{\"action\":\"apply\",\"profile\":\"monitoring\",\"token\":5,\"x\":1}","{\"action\":\"rollback\",\"profile\":\"gateway\"}",
        "{\"action\":\"delete\"}","{\"action\":\"apply\",\"action\":\"rollback\"}","[]","{"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++){r=post(bad[i]);assert(r.status==400);}
    assert(applies==1&&!rollbacks);
    char big[200];memset(big,' ',sizeof big-1);big[sizeof big-1]=0;r=post(big);assert(r.status==400);
    apply_result=ESP_ERR_INVALID_STATE;r=post("{\"action\":\"apply\",\"profile\":\"gateway\",\"token\":7}");assert(r.status==409&&strstr(r.reply,"preview again"));
    canned=(profile_result_t){.rolled_back=true,.partial=true,.changed_mask=1u<<PK_OPS_MONITORING};apply_result=ESP_ERR_NO_MEM;
    r=post("{\"action\":\"apply\",\"profile\":\"gateway\",\"token\":7}");assert(r.status==503&&strstr(r.reply,"\"partial\":true")&&strstr(r.reply,"device_monitoring"));
    rollback_result=ESP_ERR_NOT_FOUND;r=post("{\"action\":\"rollback\"}");assert(r.status==404&&rollbacks==1);
    rollback_result=ESP_OK;canned=(profile_result_t){.rolled_back=true,.kept_mask=1u<<PK_HEALTH};r=post("{\"action\":\"rollback\"}");assert(r.status==200&&strstr(r.reply,"\"kept\":[\"health_monitor\"]"));
    httpd_req_t denied={.content_len=2,.body="{}",.authorized=false};int before=applies;post_profiles(&denied);assert(denied.status==401&&applies==before);
    puts("PASS: actual profiles POST: strict action/profile/token, 400/409/503/404 mapping with partial/left-changed detail, auth (fixtures)");
}
'''
STUBS2 = {'esp_err.h': STUBS['esp_err.h'], 'esp_http_server.h': '#pragma once\ntypedef struct httpd_req httpd_req_t;\ntypedef void *httpd_handle_t;\n'}
with tempfile.TemporaryDirectory(prefix='config-profiles-http-') as folder:
    path = Path(folder)
    for name, text in STUBS2.items(): (path / name).write_text(text, encoding='utf-8')
    (path / 'http.c').write_text(HTTP, encoding='utf-8')
    binary = path / ('http.exe' if os.name == 'nt' else 'http')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
    libs = ['-lm']; dep = os.environ.get('CJSON_SOURCE')
    if dep: flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('PROFILE_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'http.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
