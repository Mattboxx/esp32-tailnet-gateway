"""Per-board home network name (DHCP hostname and mDNS "<name>.local").

Compiles the actual lan_name_from() of main/lan_name.c: a saved hostname is
used only when it is a valid DNS label, otherwise every board gets its own
"esp32-tailnet-xxxx" from the AP MAC (the setup Wi-Fi's suffix), so two
gateways on one LAN never answer to the same default name. Host only.
LANNAME_SANITIZE=1 adds ASan/UBSan.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def c_func(src, signature):
    body = signature + src.split(signature, 1)[1]
    depth, out = 0, []
    for ch in body:
        out.append(ch)
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return ''.join(out)
    raise AssertionError(signature)


source = (ROOT / 'main/lan_name.c').read_text(encoding='utf-8')
function = c_func(source, 'void lan_name_from(const char *configured, const uint8_t ap_mac[6], char *out, size_t cap)')
max_len = (ROOT / 'main/lan_name.h').read_text(encoding='utf-8').split('#define LAN_NAME_MAX', 1)[1].split()[0]

program = r'''
#include <assert.h>
#include <ctype.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define LAN_NAME_MAX ''' + max_len + r'''
''' + function + r'''
static char out[64];
static const char *name(const char *configured, const uint8_t *mac, size_t cap) {
    memset(out, 0x5a, sizeof out); lan_name_from(configured, mac, out, cap); return out;
}
int main(void) {
    const uint8_t a[6] = {0xd4, 0x05, 0x92, 0x79, 0xc6, 0x3d}, b[6] = {0xd4, 0x05, 0x92, 0x79, 0x00, 0x0a};
    /* Defaults differ per board and match the setup Wi-Fi suffix (C63D). */
    assert(!strcmp(name(NULL, a, sizeof out), "esp32-tailnet-c63d"));
    assert(!strcmp(name("", a, sizeof out), "esp32-tailnet-c63d"));
    assert(!strcmp(name(NULL, b, sizeof out), "esp32-tailnet-000a"));
    /* Valid saved names, lowercased. */
    assert(!strcmp(name("nas-gateway", a, sizeof out), "nas-gateway"));
    assert(!strcmp(name("Garage-GW2", a, sizeof out), "garage-gw2"));
    assert(!strcmp(name("x", a, sizeof out), "x"));
    char longest[LAN_NAME_MAX + 2]; memset(longest, 'a', LAN_NAME_MAX); longest[LAN_NAME_MAX] = 0;
    assert(!strcmp(name(longest, a, sizeof out), longest));
    longest[LAN_NAME_MAX] = 'a'; longest[LAN_NAME_MAX + 1] = 0;   /* one too long */
    assert(!strcmp(name(longest, a, sizeof out), "esp32-tailnet-c63d"));
    /* Not a DNS label: fall back to the per-board default. */
    const char *bad[] = {"-gw", "gw-", "my gateway", "gw_1", "gw.local", "gw/", "caf\xc3\xa9", "a\tb", "<b>"};
    for (size_t i = 0; i < sizeof bad / sizeof bad[0]; i++)
        assert(!strcmp(name(bad[i], a, sizeof out), "esp32-tailnet-c63d"));
    /* Small output buffers: always terminated, never overrun. */
    assert(!strcmp(name("nas-gateway", a, 12), "nas-gateway"));
    name("nas-gateway", a, 11); assert(!strcmp(out, "esp32-tail") && (unsigned char)out[11] == 0x5a);
    name(NULL, a, 5); assert(!strcmp(out, "esp3") && (unsigned char)out[5] == 0x5a);
    puts("PASS: actual lan_name_from(): per-board esp32-tailnet-xxxx default from the AP MAC, valid saved names lowercased, invalid labels and lengths fall back, small buffers terminated (host)");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='lan-name-') as directory:
    path = Path(directory)
    (path / 'test.c').write_text(program, encoding='utf-8')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
    if os.environ.get('LANNAME_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    binary = path / ('test.exe' if os.name == 'nt' else 'test')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
