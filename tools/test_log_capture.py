"""Actual unchanged log ring functions; synthetic critical sections.
No RTC persistence, concurrent tasks or physical crash/power test is claimed.
LOG_SANITIZE=1 enables host ASan/UBSan.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/log_capture.c').read_text(encoding='utf-8')
def function(signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2] + '\n'

constants = '\n'.join(line for line in source.splitlines() if line.startswith((
    '#define DEFAULT_BUFFER_BYTES', '#define INTERNAL_FALLBACK_BYTES',
    '#define MAX_BUFFER_BYTES', '#define ROUND_UP_1K', '#define PRECRASH_RING_BYTES')))
program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MALLOC_CAP_SPIRAM 1
#define taskENTER_CRITICAL(x) ((void)(x))
#define taskEXIT_CRITICAL(x) ((void)(x))
''' + constants + r'''
static char *s_buf;static size_t s_head,s_count,s_cap;static uint64_t s_seq;static int s_lock,s_precrash_lock;
static struct {size_t head,count;char data[PRECRASH_RING_BYTES];} s_precrash;
''' + function('static void buffer_append(') + function('size_t log_capture_read(') + function('size_t log_capture_read_since(') + function('void log_capture_clear(') + r'''
int main(void){
 s_cap=DEFAULT_BUFFER_BYTES;s_buf=calloc(s_cap,1);char input[1024],*out=calloc(s_cap+1,1);assert(s_buf&&out&&s_cap==16*1024);
 for(unsigned i=0;i<72;i++){memset(input,(int)('A'+i%26),sizeof input);buffer_append(input,sizeof input);}
 assert(s_seq==72*1024&&s_count==s_cap&&s_precrash.count==4096);
 assert(log_capture_read(out,s_cap+1)==s_cap);
 for(unsigned i=0;i<16;i++)for(unsigned j=0;j<1024;j++)assert(out[i*1024+j]==(char)('A'+(i+56)%26));
 uint64_t seq;assert(log_capture_read_since(0,out,s_cap+1,&seq)==s_cap&&seq==s_seq);
 char tail[8];assert(log_capture_read(tail,sizeof tail)==7&&!strcmp(tail,"TTTTTTT"));
 assert(log_capture_read_since(s_seq,out,s_cap+1,&seq)==0&&seq==s_seq);
 log_capture_clear();assert(!s_count&&s_seq==72*1024);buffer_append("new",3);
 assert(log_capture_read_since(seq,out,s_cap+1,&seq)==3&&!strcmp(out,"new"));
 free(out);free(s_buf);puts("PASS actual log ring: unchanged 16KB capacity, 4KB RTC, wrap, cursor, tail and clear");
}
'''
with tempfile.TemporaryDirectory(prefix='log-capture-') as folder:
    path = Path(folder); c = path / 'case.c'; c.write_text(program, encoding='utf-8')
    binary = path / ('case.exe' if os.name == 'nt' else 'case')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('LOG_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'), *flags, str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=30)
