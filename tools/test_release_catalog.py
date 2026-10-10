"""Opt-in check of actual firmware selection against the public fork catalog.

Compiles the real C selector with cJSON. Never installs firmware, changes a
device, uses a GitHub token or prints the response body.
"""
import argparse
from pathlib import Path
import os
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'main/ota_remote.c').read_text(encoding='utf-8')
selector = 'bool ota_remote_select_release' + source.split('bool ota_remote_select_release', 1)[1].split('typedef struct { char *body', 1)[0]
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cJSON.h"
#include "ota_validation.h"
static size_t strlcpy(char *d,const char *s,size_t z) {
    size_t n=strlen(s);if(z){size_t c=n<z-1?n:z-1;memcpy(d,s,c);d[c]=0;}return n;
}
'''
tests = r'''
int main(int argc,char **argv) {
    assert(argc==7);FILE *f=fopen(argv[1],"rb");assert(f);
    assert(!fseek(f,0,SEEK_END));long length=ftell(f);assert(length>0&&length<=262144);rewind(f);
    char *body=calloc(1,length+1);assert(body&&fread(body,1,length,f)==(size_t)length);fclose(f);
    cJSON *releases=cJSON_Parse(body);assert(releases);free(body);
    char tag[32]={0},digest_text[72];uint32_t size=0;unsigned char hash[32],expected[32];
    snprintf(digest_text,sizeof digest_text,"sha256:%s",argv[5]);assert(ota_digest_parse(digest_text,expected));
    uint32_t partition=(uint32_t)strtoul(argv[6],NULL,10);
    assert(ota_remote_select_release(releases,argv[2],true,partition,tag,&size,hash));
    assert(!strcmp(tag,argv[4])&&!memcmp(hash,expected,32)&&size>288);
    assert(!ota_remote_select_release(releases,argv[2],false,partition,tag,&size,hash));
    assert(!ota_remote_select_release(releases,argv[3],true,partition,tag,&size,hash));
    cJSON_Delete(releases);
    puts("PASS: real published beta asset/digest selected from older development version; stable-only excludes it; installed identical version has no update");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-github', action='store_true', required=True)
    parser.add_argument('--older-version', required=True)
    parser.add_argument('--installed-version', required=True)
    parser.add_argument('--expected-tag', required=True)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    req = urllib.request.Request('https://api.github.com/repos/Mattboxx/esp32-tailscale-gateway-NAS-recovery/releases?per_page=10',
                                 headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Mattboxx-release-validation'})
    with urllib.request.urlopen(req, timeout=20) as response:
        catalog = response.read(262145)
    assert len(catalog) <= 262144, 'Catalog exceeds the firmware response limit'
    with tempfile.TemporaryDirectory(prefix='release-catalog-') as directory:
        path = Path(directory)
        (path / 'catalog.json').write_bytes(catalog)
        (path / 'test.c').write_text(fixture + selector + tests, encoding='utf-8')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT / 'main')]
        cjson = os.environ.get('CJSON_SOURCE')
        flags += ['-I', str(Path(cjson).parent) if cjson else '/usr/include/cjson']
        binary = path / ('test.exe' if os.name == 'nt' else 'test')
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'),
                        *([cjson] if cjson else ['-lcjson']), '-o', str(binary)], check=True)
        subprocess.run([str(binary), str(path / 'catalog.json'), args.older_version,
                        args.installed_version, args.expected_tag, args.expected_sha256, '1966080'], check=True)


if __name__ == '__main__':
    main()
