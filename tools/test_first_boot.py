"""First-boot setup: actual firmware code against an independent client.

Compiles main/first_boot_core.c, MicroLink's ml_x25519.c and the crypto glue
of main/first_boot.c (pinned SDK mbedTLS GCM/SHA-256) on the host and drives
them with Python `cryptography` acting as the browser: pairing, presence,
setup code lockout, expiry, re-pairing, sealed requests, replay, tampering,
size limits and low-order keys. A second program covers activation, field
checks, setup-AP isolation and the captive DNS answer from dns_relay.c.
Host fixtures only: no radio, no device. FIRSTBOOT_SANITIZE=1 adds ASan/UBSan.
MBEDTLS_DIR overrides the pinned SDK mbedTLS tree.
"""
from pathlib import Path
import os
import subprocess
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
MBED = Path(os.environ.get('MBEDTLS_DIR', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/mbedtls/mbedtls')))
ML = ROOT / 'external/microlink/components/microlink/src'
fb_source = (ROOT / 'main/first_boot.c').read_text(encoding='utf-8')
glue = fb_source.split('/* ---------------------------------------------------------------- crypto */', 1)[1].split(
    '/* ------------------------------------------------------------- lifecycle */', 1)[0]
dns_source = (ROOT / 'components/dns_relay/dns_relay.c').read_text(encoding='utf-8')
def c_func(src, signature):
    body = signature + src.split(signature, 1)[1]
    depth, out = 0, []
    for i, ch in enumerate(body):
        out.append(ch)
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return ''.join(out)
    raise AssertionError(signature)
dns_funcs = '\n'.join(c_func(dns_source, s) for s in (
    'static int dns_question_len(const uint8_t *p, int len)',
    'static bool dns_is_std_query(const uint8_t *p, int len)',
    'static int dns_captive_answer(const uint8_t *q, int qlen, uint32_t ip_nbo, uint8_t *out, int cap)'))
key_max = dns_source.split('#define DNS_CACHE_KEY_MAX', 1)[1].split('\n', 1)[0].strip().split()[0]

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "first_boot_core.h"
#include "mbedtls/gcm.h"
#include "mbedtls/sha256.h"
int ml_x25519(unsigned char out[32], const unsigned char scalar[32], const unsigned char base[32], int clamp);
static uint64_t rng = 0x9e3779b97f4a7c15ull;
static void esp_fill_random(void *p, size_t n) { uint8_t *b = p; while (n--) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; *b++ = (uint8_t)rng; } }
''' + glue + r'''
static fb_ctx_t ctx;
static void hexout(const uint8_t *b, size_t n) { for (size_t i = 0; i < n; i++) printf("%02x", b[i]); }
static int unhex(const char *h, uint8_t *o, size_t n) { return fb_hex_decode(h, o, n); }
int main(int argc, char **argv) {
    if (argc > 1) rng ^= strtoull(argv[1], NULL, 10);
    fb_init(&ctx, &s_crypto);
    static char line[8192], a[4096], b[4096], c[4096], d[4096];
    while (fgets(line, sizeof line, stdin)) {
        unsigned long long now = 0; unsigned ip = 0; unsigned long seq = 0; int r;
        uint8_t sid[16], pub[32], iv[12], tag[16], ct[2048];
        static char pt[2049];
        if (sscanf(line, "begin %u %64s %llu", &ip, a, &now) == 3) {
            if (unhex(a, pub, 32)) { puts("ERR hex"); fflush(stdout); continue; }
            r = fb_begin(&ctx, ip, pub, now);
            if (r) printf("ERR %d\n", r); else { printf("OK "); hexout(ctx.s.sid, 16); printf(" "); hexout(ctx.s.device_pub, 32); printf("\n"); }
        } else if (sscanf(line, "presence %llu", &now) == 1) {
            printf("R %d\n", fb_presence(&ctx, now));
        } else if (sscanf(line, "code %32s %15s %llu", a, b, &now) == 3) {
            unhex(a, sid, 16); printf("R %d\n", fb_claim_code(&ctx, sid, b, now));
        } else if (!strncmp(line, "getcode", 7)) {
            printf("C %s\n", ctx.code);
        } else if (sscanf(line, "state %32s %llu", a, &now) == 2) {
            unhex(a, sid, 16); fb_tick(&ctx, now); printf("S %d\n", fb_session_state(&ctx, sid));
        } else if (sscanf(line, "open %32s %lu %24s %4095s %32s %llu", a, &seq, b, c, d, &now) == 6) {
            size_t n = strlen(c) / 2;
            if (n > sizeof ct || unhex(a, sid, 16) || unhex(b, iv, 12) || unhex(c, ct, n) || unhex(d, tag, 16)) { puts("ERR hex"); fflush(stdout); continue; }
            r = fb_open(&ctx, sid, (uint32_t)seq, iv, ct, n, tag, pt, now);
            if (r) printf("ERR %d\n", r); else { printf("OK "); hexout((uint8_t *)pt, strlen(pt)); printf("\n"); }
        } else puts("ERR cmd");
        fflush(stdout);
    }
    fb_wipe(&ctx);
    return 0;
}
'''

UNIT = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "first_boot_core.h"
#define DNS_CACHE_KEY_MAX ''' + key_max + '\n' + dns_funcs + r'''
static int query(uint8_t *q, const char *name, uint16_t type) {
    memset(q, 0, 12); q[0] = 0x12; q[1] = 0x34; q[2] = 0x01; q[5] = 1;
    int n = 12; const char *s = name;
    while (*s) { const char *dot = strchr(s, '.'); int l = dot ? (int)(dot - s) : (int)strlen(s);
        q[n++] = (uint8_t)l; memcpy(q + n, s, l); n += l; s += l; if (*s) s++; }
    q[n++] = 0; q[n++] = type >> 8; q[n++] = type & 255; q[n++] = 0; q[n++] = 1; return n;
}
static int frame(uint8_t *f, uint16_t type, uint8_t ver_ihl, const uint8_t dst[4]) {
    memset(f, 0, 64); f[12] = type >> 8; f[13] = type & 255; f[14] = ver_ihl; memcpy(f + 14 + 16, dst, 4); return 64;
}
int main(void) {
    /* Activation: only a device with no setting at all. */
    assert(fb_should_activate(false, false, 0, false));
    assert(!fb_should_activate(true, false, 0, false));
    assert(!fb_should_activate(false, true, 0, false));
    assert(!fb_should_activate(false, false, 1, false));
    assert(!fb_should_activate(false, false, 0, true));
    /* Field checks. */
    assert(fb_check_admin_password(NULL, NULL) && fb_check_admin_password("short7!", NULL));
    assert(fb_check_admin_password("aaaaaaaaaa", NULL) && fb_check_admin_password("HomeNet01", "homenet01"));
    assert(!fb_check_admin_password("correct horse", "HomeNet") && fb_check_admin_password("bad\x01pass8", NULL));
    char big[80]; memset(big, 'x', 65); big[0] = 'y'; big[65] = 0; assert(fb_check_admin_password(big, NULL));
    assert(fb_check_wifi("", "") && !fb_check_wifi("Open", "") && fb_check_wifi("Net", "1234567"));
    assert(!fb_check_wifi("Net", "12345678") && fb_check_wifi("123456789012345678901234567890123", "12345678"));
    char hex64[65]; memset(hex64, 'a', 64); hex64[64] = 0; assert(!fb_check_wifi("Net", hex64)); hex64[3] = 'z'; assert(fb_check_wifi("Net", hex64));
    assert(fb_check_ap_password("1234567") && !fb_check_ap_password("12345678"));
    assert(!fb_check_auth_key("") && fb_check_auth_key("tskey") && fb_check_auth_key("tskey-auth with space") && !fb_check_auth_key("synthetic-preauth-0123456789"));
    assert(!fb_check_login_server("") && !fb_check_login_server("https://hs.example.com") && fb_check_login_server("ftp://x") && fb_check_login_server("https://a b"));
    assert(!fb_check_hostname("") && !fb_check_hostname("tailnet-gateway") && fb_check_hostname("-x") && fb_check_hostname("Upper") && fb_check_hostname("a_b"));
    /* Hex helpers. */
    uint8_t h[2]; assert(!fb_hex_decode("0aFf", h, 2) && h[0] == 10 && h[1] == 255 && fb_hex_decode("0g00", h, 2) && fb_hex_decode("00", h, 2));
    char out[5]; fb_hex_encode(h, 2, out); assert(!strcmp(out, "0aff"));
    /* Setup-AP isolation: ARP and IPv4 to the AP or broadcast only. */
    uint8_t f[64]; const uint8_t ap[4] = {192, 168, 4, 1}, lan[4] = {192, 168, 1, 1}, bc[4] = {255, 255, 255, 255};
    uint32_t ap_nbo; memcpy(&ap_nbo, ap, 4);
    assert(fb_ap_frame_allowed(f, frame(f, 0x0806, 0, lan), ap_nbo));
    assert(fb_ap_frame_allowed(f, frame(f, 0x0800, 0x45, ap), ap_nbo));
    assert(fb_ap_frame_allowed(f, frame(f, 0x0800, 0x45, bc), ap_nbo));
    assert(!fb_ap_frame_allowed(f, frame(f, 0x0800, 0x45, lan), ap_nbo));
    assert(!fb_ap_frame_allowed(f, frame(f, 0x86dd, 0x60, ap), ap_nbo));
    assert(!fb_ap_frame_allowed(f, frame(f, 0x8100, 0x45, ap), ap_nbo));
    assert(!fb_ap_frame_allowed(f, frame(f, 0x0800, 0x44, ap), ap_nbo));
    assert(!fb_ap_frame_allowed(f, 20, ap_nbo) && !fb_ap_frame_allowed(f, 13, ap_nbo) && !fb_ap_frame_allowed(NULL, 64, ap_nbo));
    /* Captive DNS: A -> AP address, other types empty NOERROR, junk dropped. */
    uint8_t q[600], r[700]; int n = query(q, "connectivitycheck.gstatic.com", 1);
    int rl = dns_captive_answer(q, n, ap_nbo, r, sizeof r);
    assert(rl == n + 16 && r[0] == 0x12 && r[1] == 0x34 && (r[2] & 0x80) && (r[2] & 0x04) && (r[2] & 0x01) && (r[3] & 0x0f) == 0);
    assert(r[7] == 1 && !memcmp(r + n, "\xc0\x0c\x00\x01\x00\x01", 6) && !memcmp(r + rl - 4, ap, 4) && !memcmp(r + 12, q + 12, n - 12));
    n = query(q, "captive.apple.com", 28); rl = dns_captive_answer(q, n, ap_nbo, r, sizeof r);
    assert(rl == n && r[7] == 0 && (r[3] & 0x0f) == 0);
    n = query(q, "captive.apple.com", 1); q[2] |= 0x80; assert(!dns_captive_answer(q, n, ap_nbo, r, sizeof r)); /* a response */
    q[2] &= 0x7f; q[5] = 2; assert(!dns_captive_answer(q, n, ap_nbo, r, sizeof r));                           /* two questions */
    q[5] = 1; assert(!dns_captive_answer(q, 11, ap_nbo, r, sizeof r) && !dns_captive_answer(q, n - 3, ap_nbo, r, sizeof r));
    assert(!dns_captive_answer(q, n, ap_nbo, r, n + 15));                                                      /* no room */
    q[12] = 0xc0; assert(!dns_captive_answer(q, n, ap_nbo, r, sizeof r));                                      /* compression */
    for (int len = 0; len < (int)sizeof q; len++) { for (int i = 0; i < len; i++) q[i] = (uint8_t)(i * 37 + len); (void)dns_captive_answer(q, len, ap_nbo, r, sizeof r); }
    puts("PASS: first-boot activation, field checks, setup-AP isolation, captive DNS answer and malformed queries (host)");
    return 0;
}
'''

LABEL = b'mattboxx-tailnet-gateway-setup-v1'


class Device:
    def __init__(self, exe, seed):
        self.p = subprocess.Popen([str(exe), str(seed)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def cmd(self, line):
        self.p.stdin.write(line + '\n'); self.p.stdin.flush()
        return self.p.stdout.readline().strip()
    def close(self):
        self.p.stdin.close(); assert self.p.wait(10) == 0


def raw(pub):
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class Client:
    def __init__(self, dev, ip):
        self.dev, self.ip, self.k = dev, ip, X25519PrivateKey.generate()
        self.seq = 0
    def begin(self, now):
        out = self.dev.cmd(f'begin {self.ip} {raw(self.k.public_key()).hex()} {now}')
        if not out.startswith('OK'):
            return out
        _, self.sid, dpub = out.split()
        shared = self.k.exchange(X25519PublicKey.from_public_bytes(bytes.fromhex(dpub)))
        h = hashes.Hash(hashes.SHA256()); h.update(LABEL + shared + bytes.fromhex(dpub) + raw(self.k.public_key()))
        self.key = h.finalize()
        return 'OK'
    def seal(self, seq, data, key=None, sid=None):
        sid = sid or self.sid
        iv = os.urandom(12)
        out = AESGCM(key or self.key).encrypt(iv, data, bytes.fromhex(sid) + seq.to_bytes(4, 'big'))
        return sid, iv.hex(), out[:-16].hex(), out[-16:].hex()
    def open(self, seq, data, now, tamper=False, key=None):
        sid, iv, ct, tag = self.seal(seq, data, key)
        if tamper:
            tag = ('0' if tag[0] != '0' else '1') + tag[1:]
        return self.dev.cmd(f'open {sid} {seq} {iv} {ct} {tag} {now}')


S = 1_000_000
def scenarios(exe):
    d = Device(exe, 1)
    a, b = Client(d, 0x0204A8C0), Client(d, 0x0304A8C0)
    assert a.begin(10 * S) == 'OK'
    assert d.cmd(f'state {a.sid} {10 * S}') == 'S 1'
    assert a.open(1, b'{"action":"x"}', 11 * S) == 'ERR 4'          # not claimed
    assert b.begin(12 * S) == 'ERR 1'                                # busy
    assert d.cmd(f'presence {13 * S}') == 'R 0'
    assert d.cmd(f'state {a.sid} {13 * S}') == 'S 2'
    assert b.begin(14 * S) == 'ERR 2'                                # claimed by another client
    msg = '{"action":"finish","admin_password":"pässword ✓"}'.encode()
    assert a.open(1, msg, 15 * S) == 'OK ' + msg.hex()
    assert a.open(1, msg, 16 * S) == 'ERR 9'                         # replay
    assert a.open(0, msg, 16 * S) == 'ERR 9'
    assert a.open(2, msg, 17 * S, tamper=True) == 'ERR 8'            # forged tag
    assert a.open(2, msg, 17 * S, key=bytes(32)) == 'ERR 8'          # wrong key
    assert a.open(2, msg, 18 * S) == 'OK ' + msg.hex()               # failures did not advance
    assert a.open(3, b'a\x00b', 18 * S) == 'ERR 10'                  # embedded NUL
    assert a.open(4, b'x' * 1537, 18 * S) == 'ERR 10'                # oversized
    assert a.open(4, b'x' * 1536, 18 * S) == 'OK ' + (b'x' * 1536).hex()
    assert d.cmd(f'open {"00" * 16} 9 {"00" * 12} 00 {"00" * 16} {19 * S}') == 'ERR 3'
    # Idle claimed session expires after 30 minutes.
    assert d.cmd(f'state {a.sid} {(18 + 1800) * S}') == 'S 0'
    assert a.open(9, msg, (18 + 1801) * S) == 'ERR 3'
    # Pending pairing expires after 10 minutes; presence then finds nothing.
    assert b.begin(4000 * S) == 'OK'
    assert d.cmd(f'presence {(4000 + 601) * S}') == 'R 3'
    assert d.cmd(f'state {b.sid} {(4000 + 601) * S}') == 'S 0'
    # Same client may re-pair (lost page); the old key stops working.
    assert a.begin(5000 * S) == 'OK'; assert d.cmd(f'presence {5001 * S}') == 'R 0'
    old_key, old_sid = a.key, a.sid
    assert a.begin(5002 * S) == 'OK' and a.sid != old_sid
    assert d.cmd(f'open {old_sid} 1 {"00"*12} 00 {"00"*16} {5003 * S}') == 'ERR 3'
    assert a.open(1, msg, 5003 * S) == 'ERR 4'                       # needs presence again
    # Low-order client keys are refused (all-zero shared secret).
    z = d.cmd(f'begin {0x0904A8C0} {"00" * 32} {9000 * S}')
    assert z == 'ERR 5', z                                           # pending from a expired; bad key
    d.close()
    d = Device(exe, 2)
    assert d.cmd(f'begin 7 {"00" * 32} {S}') == 'ERR 5'
    assert d.cmd(f'begin 7 {"01" + "00" * 31} {S}') == 'ERR 5'
    # Setup code: wrong codes are limited, then even the right code is refused.
    c = Client(d, 7); assert c.begin(2 * S) == 'OK'
    code = d.cmd('getcode').split()[1]
    assert len(code) == 8 and code.isdigit()
    wrong = ('1' if code[0] != '1' else '2') + code[1:]
    assert d.cmd(f'code {"ff" * 16} {code} {3 * S}') == 'R 3'         # unknown session
    for _ in range(4):
        assert d.cmd(f'code {c.sid} {wrong} {3 * S}') == 'R 7'
    assert d.cmd(f'code {c.sid} {code[:7]} {3 * S}') == 'R 6'        # fifth failure locks
    assert d.cmd(f'code {c.sid} {code} {3 * S}') == 'R 6'
    d.close()
    d = Device(exe, 3)
    c = Client(d, 7); assert c.begin(2 * S) == 'OK'
    code = d.cmd('getcode').split()[1]
    assert d.cmd(f'code {c.sid} {code} {3 * S}') == 'R 0'
    assert d.cmd(f'code {c.sid} {code} {3 * S}') == 'R 0'            # idempotent once claimed
    assert c.open(1, b'{}', 4 * S) == 'OK ' + b'{}'.hex()
    d.close()
    codes = set()
    for seed in range(40):
        d = Device(exe, 100 + seed); codes.add(d.cmd('getcode')); d.close()
    assert len(codes) > 35, 'setup codes must vary per boot'


with tempfile.TemporaryDirectory(prefix='first-boot-', ignore_cleanup_errors=True) as directory:
    path = Path(directory)
    (path / 'cfg.h').write_text('#define MBEDTLS_AES_C\n#define MBEDTLS_GCM_C\n#define MBEDTLS_CIPHER_C\n#define MBEDTLS_SHA256_C\n#define MBEDTLS_PLATFORM_C\n')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-I', str(path), '-I', str(ROOT / 'main')]
    if os.environ.get('FIRSTBOOT_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    mbed = [str(MBED / 'library' / (n + '.c')) for n in ('aes', 'gcm', 'cipher', 'cipher_wrap', 'sha256', 'platform_util',
                                                         'constant_time', 'block_cipher', 'platform')]
    exe = path / ('harness.exe' if os.name == 'nt' else 'harness')
    (path / 'harness.c').write_text(HARNESS, encoding='utf-8')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, '-DMBEDTLS_CONFIG_FILE="cfg.h"', '-I', str(MBED / 'include'), '-I', str(MBED / 'library'),
                    '-I', str(ML), str(path / 'harness.c'), str(ROOT / 'main/first_boot_core.c'), str(ML / 'ml_x25519.c'),
                    *mbed, '-Wno-error', '-o', str(exe)], check=True)
    scenarios(exe)
    print('PASS: actual first-boot pairing/presence/code lockout/expiry/re-pairing and sealed requests (X25519 + AES-256-GCM) interoperate with Python cryptography; replay, tampering, size and low-order keys refused (host)')
    unit = path / ('unit.exe' if os.name == 'nt' else 'unit')
    (path / 'unit.c').write_text(UNIT, encoding='utf-8')
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'unit.c'), str(ROOT / 'main/first_boot_core.c'), '-o', str(unit)], check=True)
    subprocess.run([str(unit)], check=True)
