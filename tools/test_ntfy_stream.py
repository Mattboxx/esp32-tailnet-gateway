"""Compile the actual bounded ntfy JSON parser; compare accepted mutations to cJSON."""
from pathlib import Path
import json
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def cbytes(value):
    return '"' + ''.join(f'\\x{b:02x}' for b in value.encode('utf-8')) + '"'


valid = [
    {'id': 'frame', 'event': 'message', 'message': 'info'},
    {'id': 'frame', 'event': 'message', 'message': ' \r\ninfo\n '},
    {'id': 'frame', 'event': 'message', 'message': 'wol NAS café 🚀'},
    {'id': 'frame', 'event': 'message', 'message': 'info', 'title': 'ESP32 reply'},
    {'attachment': {'name': 'x' * 250000, 'size': 2**63}, 'message': 'info', 'event': 'message', 'id': 'frame'},
    {'message': 'x' * 250000, 'id': 'frame', 'event': 'message'},
    {'message': ' ' * 250000 + 'info' + '\n' * 250000, 'event': 'message', 'id': 'frame'},
    {'id': 'frame', 'message': 'x' * 127, 'event': 'message'},
    {'id': 'frame', 'message': 'x' * 128, 'event': 'message'},
    {'id': 'frame', 'event': 'message', 'time': 1.25e-5, 'actions': [True, False, None, {}, [], {'id': 'nested'}]},
    {},
]
valid_wires = [json.dumps(value, ensure_ascii=ascii_only) for value in valid for ascii_only in (True, False)]
invalid = [
    '[]', 'null', '{}{}', '{"id":"x",}', '{"id":}', '{"a":[1,]}',
    '{"a":01}', '{"a":-}', '{"a":1.}', '{"a":1e}', '{"a":1e+}',
    '{"a":tru}', '{"a":true false}', '{"a":"\\z"}', '{"a":"\\u12z4"}',
    '{"a":"\\ud800"}', '{"a":"\\udc00"}', '{"a":"\\ud800\\u0041"}',
    '{"message":"info\\u0000hidden"}', '{"id":"a","id":"b"}',
    '{"message":"info","message":"wol NAS"}', '{"message":"info"',
    '{"a":"raw\nnewline"}', '{"a":[' + '[' * 40 + '0' + ']' * 41 + '}',
]
fixture = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ntfy_json_stream.h"
#include "cJSON.h"
static bool edge_space(unsigned char b) {return b==' '||b=='\t'||b=='\n'||b=='\r'||b=='\v'||b=='\f';}
static void expected_field(const cJSON *root,const char *name,char *out,size_t capacity) {
    const cJSON *v=cJSON_GetObjectItemCaseSensitive(root,name);
    out[0]=0;
    if(cJSON_IsString(v)&&strlen(v->valuestring)<capacity)strcpy(out,v->valuestring);
}
static bool verify(const unsigned char *data,size_t length) {
    struct {uint32_t before;ntfy_json_parser_t p;uint32_t after;} guard;
    guard.before=guard.after=0x1234abcd;ntfy_json_reset(&guard.p);
    for(size_t i=0;i<length;i++)ntfy_json_feed(&guard.p,data[i]);
    assert(guard.before==0x1234abcd&&guard.after==0x1234abcd);
    if(!ntfy_json_finish(&guard.p))return false;
    const char *end=NULL;
    char *terminated=malloc(length+1);assert(terminated);memcpy(terminated,data,length);terminated[length]=0;
    cJSON *root=cJSON_ParseWithLengthOpts(terminated,length+1,&end,true);
    assert(cJSON_IsObject(root));
    char expected[128];expected_field(root,"id",expected,48);assert(!strcmp(expected,guard.p.event.id));
    expected_field(root,"event",expected,16);assert(!strcmp(expected,guard.p.event.event));
    const cJSON *m=cJSON_GetObjectItemCaseSensitive(root,"message");
    assert(guard.p.event.has_message==cJSON_IsString(m));
    if(cJSON_IsString(m)) {
        const char *text=m->valuestring;while(*text&&edge_space((unsigned char)*text))text++;
        size_t size=strlen(text);while(size&&edge_space((unsigned char)text[size-1]))size--;
        assert(guard.p.event.message_too_long==(size>=128));
        if(size<128){memcpy(expected,text,size);expected[size]=0;assert(!strcmp(expected,guard.p.event.message));}
    }
    const cJSON *title=cJSON_GetObjectItemCaseSensitive(root,"title");
    expected[0]=0;if(cJSON_IsString(title)){size_t n=strlen(title->valuestring);if(n>6)n=6;memcpy(expected,title->valuestring,n);expected[n]=0;}
    assert(!strcmp(expected,guard.p.event.title));
    cJSON_Delete(root);free(terminated);return true;
}
int main(void) {
    assert(sizeof(ntfy_json_parser_t)<512);
'''
fixture += ''.join(f'assert(verify((const unsigned char *){cbytes(wire)}, {len(wire.encode())}));\n' for wire in valid_wires)
fixture += ''.join(f'assert(!verify((const unsigned char *){cbytes(wire)}, {len(wire.encode())}));\n' for wire in invalid)
fixture += r'''
    unsigned char invalid_utf8[]={ '{','"','a','"',':','"',0xc0,0x80,'"','}'};
    assert(!verify(invalid_utf8,sizeof invalid_utf8));
    const unsigned char original[]="{\"id\":\"frame\",\"event\":\"message\",\"message\":\"info\",\"metadata\":{\"n\":-1.25e+2,\"a\":[true,null,{}]}}";
    unsigned char mutation[256];uint32_t rng=0xa195427;
    for(unsigned iteration=0;iteration<100000;iteration++) {
        size_t n=sizeof original-1;memcpy(mutation,original,n);
        for(unsigned changes=0;changes<1+iteration%4;changes++) {
            rng=rng*1664525+1013904223;size_t at=rng%n;
            rng=rng*1664525+1013904223;mutation[at]=(unsigned char)(rng>>24);
        }
        verify(mutation,n);
    }
    puts("PASS: bounded ntfy JSON: large strings/metadata, trimming, UTF-8/escapes/surrogates, malformed/deep/duplicate fields, 100000 mutations checked against cJSON");
}
'''
with tempfile.TemporaryDirectory(prefix='ntfy-stream-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(fixture)
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
    libs = []
    cjson = os.environ.get('CJSON_SOURCE')
    if cjson:
        flags += ['-I', str(Path(cjson).parent), cjson]
    else:
        flags += subprocess.check_output(['pkg-config', '--cflags', 'libcjson'], text=True).split()
        libs += subprocess.check_output(['pkg-config', '--libs', 'libcjson'], text=True).split()
    if os.environ.get('NTFY_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(ROOT / 'main/ntfy_json_stream.c'), str(path / 'test.c'), '-o', str(binary), *libs], check=True)
    subprocess.run([str(binary)], check=True)
