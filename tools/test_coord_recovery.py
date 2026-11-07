"""Actual coordinator request/initial-state branches with host transport stubs.

Not a hosted Tailscale/Headscale or physical reconnect qualification.
COORD_SOURCE optionally selects an archived before-fix source for reproduction.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
source = Path(os.environ.get('COORD_SOURCE', ML / 'src/ml_coord.c')).read_text(encoding='utf-8')
start = source.index('static int do_start_long_poll(')
request = source[start:source.index('\n}', start) + 2]
start = source.index('        case COORD_FETCH_PEERS:')
initial = source[start:source.index('                /* Signal registration only now', start)]
start = source.index('static void note_ctrl_loss(')
notes = source[start:source.index('ml->ctrl_retry_failures++;', start)] + 'ml->ctrl_retry_failures++;\n}\n'

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
typedef struct {uint8_t wg_public_key[32],disco_public_key[32];
    const char *ctrl_loss_reason;const char *ctrl_close_detail;int32_t ctrl_close_code,ctrl_loss_code;
    uint32_t ctrl_loss_count;const char *ctrl_retry_reason;uint32_t ctrl_retry_failures;
    uint64_t rt_loss_ms,rt_backoff_ms,rt_tcp_ms,rt_noise_ms,rt_register_ms,rt_fetch_ms,rt_stream_ms,rt_derp_ms;
    uint32_t ctrl_last_reconnect_ms;char ctrl_reconnect_stages[112];} microlink_t;
static uint64_t ml_get_time_ms(void){return 1234;}
static size_t strlcpy_(char *d,const char *s,size_t n){size_t l=strlen(s);if(n){size_t c=l<n-1?l:n-1;memcpy(d,s,c);d[c]=0;}return l;}
#define strlcpy strlcpy_
typedef struct {int unused;} ml_noise_state_t;
static bool authority;
static int suspended,closed,fetch_rc,stream_rc,stream_calls;
static bool fetch_authority,stream_authority;
static char captured[4096];
#define ML_CTRL_PROTOCOL_VER 131
#define CTRL_HOST_HDR(m) "synthetic.invalid"
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define TAG "test"
static bool ml_policy_authority_active(void){return authority;}
static void ml_policy_suspend(void){authority=false;suspended++;}
static void ml_conn_close(microlink_t *ml){(void)ml;closed++;ml_policy_suspend();}
static void bytes_to_hex(const uint8_t *p,int n,char *s){(void)p;memset(s,'0',n*2);s[n*2]=0;}
static cJSON *build_hostinfo(microlink_t *ml){(void)ml;return cJSON_CreateObject();}
static void *ml_psram_malloc(size_t n){return malloc(n);}
static int ml_h2_build_headers_frame(uint8_t *p,size_t n,const char *m,const char *path,const char *h,const char *t,unsigned sid,bool end){
    (void)p;(void)n;(void)m;(void)path;(void)h;(void)t;assert(sid==5&&!end);return 0;
}
static int ml_h2_build_data_frame(uint8_t *p,size_t n,const uint8_t *data,size_t len,unsigned sid,bool end){
    (void)p;assert(n>=len&&len<sizeof captured&&sid==5&&end);memcpy(captured,data,len);captured[len]=0;return 0;
}
static int noise_send(microlink_t *ml,ml_noise_state_t *noise,const uint8_t *p,int n){
    (void)ml;(void)noise;(void)p;return n;
}
''' + notes + request + r'''
static int do_map_exchange(microlink_t *ml,ml_noise_state_t *noise,bool fetch){
    (void)ml;(void)noise;
    if(fetch){authority=fetch_authority;return fetch_rc;}
    stream_calls++;authority=stream_authority;return stream_rc;
}
enum {COORD_FETCH_PEERS,COORD_RECONNECTING,TEST_REGISTERED};
static int initial_branch(microlink_t *ml){
    ml_noise_state_t noise={0};int state=COORD_FETCH_PEERS;
    switch(state){
''' + initial + r'''
                (void)lp_started;
                state=TEST_REGISTERED;
            }
            break;
    default:assert(false);
    }
    return state;
}
static void reset(void){authority=false;suspended=closed=stream_calls=0;fetch_rc=stream_rc=0;fetch_authority=stream_authority=false;}
static void check_request(microlink_t *ml,bool ready){
    authority=ready;ml_noise_state_t noise={0};assert(do_start_long_poll(ml,&noise)==0);
    cJSON *r=cJSON_Parse(captured);assert(r);
    assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"Stream")));
    assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"KeepAlive")));
    cJSON *omit=cJSON_GetObjectItemCaseSensitive(r,"OmitPeers");
    assert(cJSON_IsBool(omit)&&cJSON_IsTrue(omit)==ready);cJSON_Delete(r);
    assert(authority==ready);
}
int main(void){
    microlink_t ml={0};
    (void)note_reconnected;   /* covered by test_coord_session_end.py */
    reset();check_request(&ml,true);assert(suspended==0);
    reset();check_request(&ml,false);assert(suspended==1);
    reset();fetch_authority=true;assert(initial_branch(&ml)==TEST_REGISTERED&&stream_calls==0&&closed==0);
    reset();fetch_rc=1;stream_authority=true;assert(initial_branch(&ml)==TEST_REGISTERED&&stream_calls==1&&closed==0);
    reset();fetch_rc=1;stream_rc=-1;assert(initial_branch(&ml)==COORD_RECONNECTING&&closed==1&&!authority);
    reset();fetch_rc=1;assert(initial_branch(&ml)==COORD_RECONNECTING&&closed==1&&!authority);
    reset();assert(initial_branch(&ml)==COORD_RECONNECTING&&closed==1&&!authority);
    reset();fetch_rc=-1;assert(initial_branch(&ml)==COORD_RECONNECTING&&closed==1&&stream_calls==0);
    /* Each failed attempt is recorded with its reason; a loss clears the attempt tally. */
    assert(ml.ctrl_retry_failures>=4&&ml.ctrl_retry_reason&&!strcmp(ml.ctrl_retry_reason,"MapRequest failed"));
    note_ctrl_loss(&ml,"control-plane map stream silent");
    assert(ml.ctrl_loss_count==1&&ml.ctrl_retry_failures==0&&!ml.ctrl_retry_reason);
    assert(!strcmp(ml.ctrl_loss_reason,"control-plane map stream silent")&&ml.ctrl_loss_code==-1);
    note_poll_close(&ml,"control server sent GOAWAY",0);
    assert(!strcmp(ml.ctrl_close_detail,"control server sent GOAWAY")&&ml.ctrl_close_code==0);
    puts("PASS actual coordinator: fresh-map requests after loss; full initial/stream map only; timeout/delta/incomplete/fetch failure reconnect closed (transport stubs)");
}
'''

with tempfile.TemporaryDirectory(prefix='coord-recovery-') as folder:
    p = Path(folder)
    (p / 'test.c').write_text(PROGRAM, encoding='utf-8')
    binary = p / ('test.exe' if os.name == 'nt' else 'test')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-g']
    libs = []
    dep = os.environ.get('CJSON_SOURCE')
    if dep:
        flags += ['-I', str(Path(dep).parent), dep]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('POLICY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        if os.environ.get('POLICY_NO_PIE') == '1':
            flags += ['-fno-pie', '-no-pie']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(p / 'test.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
