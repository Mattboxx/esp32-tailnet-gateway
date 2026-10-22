"""Actual bounded administration JSON helper; no device or HTTP session."""
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
PROGRAM=r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "json_guard.h"
static unsigned allocations;
static void *deny(size_t n){(void)n;allocations++;return NULL;}
int main(void){
    const char *bad[]={"", "{} trailing", "{\"enabled\":true,\"Enabled\":false}","{\"a\":[{\"x\":1,\"x\":2}]}",
        "{\"pass\":\"a\\u0000b\"}","{\"a\":\"raw\nline\"}","[[[[[[[[[1]]]]]]]]]","{\"a\":1]"};
    for(unsigned i=0;i<sizeof bad/sizeof bad[0];i++){cJSON *j=json_guard_parse(bad[i]);assert(!j);}
    cJSON *j=json_guard_parse("{\"name\":\"braces { [ \\\" quoted \\\\ text\",\"enabled\":false}");assert(j);cJSON_Delete(j);
    j=json_guard_parse("[[[[[[[[1]]]]]]]]");assert(j);cJSON_Delete(j);
    j=json_guard_parse("{\"literal\":\"\\\\u0000\"}");assert(j);cJSON_Delete(j);
    const char nul[]={ '{','}',0,'x' };assert(!json_guard_preflight(nul,sizeof nul));
    cJSON_Hooks hooks={.malloc_fn=deny,.free_fn=free};cJSON_InitHooks(&hooks);
    assert(!json_guard_parse("[[[[[[[[[1]]]]]]]]]"));assert(!allocations); /* Reject depth before cJSON recursion/allocation. */
    assert(!json_guard_parse("{}")&&allocations);cJSON_InitHooks(NULL);
    uint16_t port=0;j=cJSON_CreateString("+80");assert(!json_guard_port(j,&port));cJSON_Delete(j);
    j=cJSON_CreateString("65535");assert(json_guard_port(j,&port)&&port==65535);cJSON_Delete(j);
    j=cJSON_CreateNumber(1.5);assert(!json_guard_port(j,&port));cJSON_Delete(j);
    puts("PASS: actual JSON depth/size/duplicate aliases/trailing/NUL/escape/OOM bounds and strict ports (host)");
}
'''
with tempfile.TemporaryDirectory(prefix='json-guard-') as folder:
    p=Path(folder);(p/'test.c').write_text(PROGRAM);binary=p/('test.exe' if os.name=='nt' else 'test')
    flags=['-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'main')];libs=[]
    cjson=os.environ.get('CJSON_SOURCE')
    if cjson:flags+=['-I',str(Path(cjson).parent),cjson]
    else:
        flags+=subprocess.check_output(['pkg-config','--cflags','libcjson'],text=True).split()
        libs+=subprocess.check_output(['pkg-config','--libs','libcjson'],text=True).split()
    if os.environ.get('JSON_SANITIZE')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC','gcc'),*flags,str(p/'test.c'),'-o',str(binary),*libs],check=True)
    subprocess.run([str(binary)],check=True,timeout=30)
