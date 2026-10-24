"""Actual throughput-test core of main/throughput.c.

Covered: URL validation (schemes, hosts, ports, credentials, spaces,
control and quote characters, length), the rate calculation (rounding,
zero, very large values) and the stop rules (time, size, low internal
memory). Real downloads, TLS, the browser-side test and the worker task are
NOT covered. THR_SANITIZE=1 adds ASan/UBSan on Linux.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / 'main/throughput.c').read_text(encoding='utf-8')
core = core.split('/* --- throughput core (begin) --- */', 1)[1].split('/* --- throughput core (end) --- */', 1)[0]

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "throughput.h"
''' + core + r'''
static bool ok(const char *u){char why[96]="";bool v=throughput_url_valid(u,why,sizeof why);assert(v||why[0]);return v;}
int main(void){
    assert(ok("https://speed.cloudflare.com/__down?bytes=25000000")&&ok("http://100.64.0.7/big.iso")&&ok("http://nas:8080/file.bin")&&ok("http://[fd7a::1]/x")==false);
    assert(ok("https://example.org")&&ok("http://192.168.1.10:65535/a"));
    const char *bad[]={NULL,"","ftp://example.org/x","example.org/x","https://","http:///x","http://user:pw@nas/x","http://nas/a b","http://nas/\x01",
        "http://nas/\"x\"","http://nas:0/x","http://nas:65536/x","http://nas:12a/x","https://nas/\\x"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++)assert(!ok(bad[i]));
    char longurl[300];memset(longurl,'a',sizeof longurl-1);longurl[299]=0;memcpy(longurl,"http://nas/",11);assert(!ok(longurl));
    /* kbit/s */
    assert(throughput_kbps(0,1000)==0&&throughput_kbps(1000,0)==0);
    assert(throughput_kbps(125000,1000000)==1000);                              /* 1 Mbit/s */
    assert(throughput_kbps(2500000,1000000)==20000);
    assert(throughput_kbps(1,3)==2667);                                         /* rounded */
    assert(throughput_kbps(UINT64_MAX/16,1)==UINT32_MAX);                        /* saturates */
    /* stop rules */
    assert(!throughput_stop(0,0,10,100000));
    assert(throughput_stop(0,10*1000000ull,10,100000)&&!throughput_stop(0,10*1000000ull-1,10,100000));
    assert(throughput_stop(THR_MAX_BYTES,1,10,100000)&&!throughput_stop(THR_MAX_BYTES-1,1,10,100000));
    assert(strstr(throughput_stop(5,5,10,1000),"memory"));
    puts("throughput core: ok");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='thr-') as folder:
        path = Path(folder)
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
        (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
        (path / 'thr.c').write_text(PROGRAM, encoding='utf-8')
        binary = path / ('thr.exe' if os.name == 'nt' else 'thr')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-I', str(path), '-I', str(ROOT / 'main')]
        if os.environ.get('THR_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'thr.c'), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=60)


if __name__ == '__main__':
    main()
