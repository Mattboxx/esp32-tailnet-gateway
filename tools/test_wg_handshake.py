"""WireGuard handshake with the actual MicroLink wireguard.c on both sides.

Since 3.0.9 the static-static DH of a peer is computed at its first
handshake, not when the peer is added (one X25519 is about 15 ms on the
ESP32-S3, in the task that decrypts incoming packets, and every peer of the
Tailnet map is added at start). Checked with real crypto (refc X25519,
BLAKE2s, ChaCha20-Poly1305) and counted X25519 calls:
- adding peers (one, then 12 more) costs no X25519;
- initiation, consumption, response and session start agree on both sides:
  initiator sending key == responder receiving key and vice versa;
- the first handshake computes the static DH once per side, the next one
  reuses it (one X25519 fewer each side);
- a peer with a low-order public key (all zero) is added but its handshake
  fails cleanly, and nothing is marked ready;
- an initiation from an unknown key is refused.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REL = 'external/microlink/components/microlink/components/wireguard_lwip/src'
SRC = ROOT / REL

FAKE_LWIP = {
    'lwip/arch.h': '#pragma once\n#include <stdint.h>\ntypedef uint8_t u8_t; typedef uint16_t u16_t; typedef uint32_t u32_t; typedef int8_t err_t;\n',
    'lwip/ip_addr.h': '#pragma once\n#include "lwip/arch.h"\ntypedef struct { uint32_t addr; uint8_t type; } ip_addr_t;\n',
    'lwip/netif.h': '#pragma once\n#include "lwip/arch.h"\nstruct netif; struct pbuf;\n',
    'lwip/udp.h': '#pragma once\n#include "lwip/ip_addr.h"\nstruct udp_pcb;\n',
}

TEST = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "wireguard.h"
#include "crypto.h"
int x25519_real(uint8_t out[32], const uint8_t s[32], const uint8_t u[32], int clamp);
static int calls;
int x25519(uint8_t out[32], const uint8_t s[32], const uint8_t u[32], int clamp) { calls++; return x25519_real(out, s, u, clamp); }
static uint32_t now_ms = 1000, rng = 12345, tai = 1;
uint32_t wireguard_sys_now(void) { return now_ms; }
void wireguard_random_bytes(void *b, size_t n) { uint8_t *p = b; while (n--) { rng = rng * 1103515245u + 12345u; *p++ = (uint8_t)(rng >> 16); } }
void wireguard_tai64n_now(uint8_t *o) { memset(o, 0, 12); o[7] = (uint8_t)(tai >> 8); o[8] = (uint8_t)tai; tai++; }
bool wireguard_is_under_load(void) { return false; }
static struct wireguard_device A, B;
static void key(uint8_t k[32], uint8_t seed) { for (int i = 0; i < 32; i++) k[i] = (uint8_t)(seed * 31 + i * 7); }
/* The responder keeps its new keys in next_keypair until the first data packet. */
static struct wireguard_keypair *resp_keys(struct wireguard_peer *p) { return p->next_keypair.valid ? &p->next_keypair : &p->curr_keypair; }
static int handshake(struct wireguard_peer *ab, struct wireguard_peer *ba_expected) {
    struct message_handshake_initiation init; struct message_handshake_response resp;
    if (!wireguard_create_handshake_initiation(&A, ab, &init)) return 0;
    struct wireguard_peer *ba = wireguard_process_initiation_message(&B, &init);
    if (ba != ba_expected) return 0;
    if (!wireguard_create_handshake_response(&B, ba, &resp)) return 0;
    if (!wireguard_process_handshake_response(&A, ab, &resp)) return 0;
    if (!wireguard_start_session(ab, true) || !wireguard_start_session(ba, false)) return 0;
    return 1;
}
int main(void) {
    uint8_t ka[32], kb[32];
    key(ka, 1); key(kb, 2);
    assert(wireguard_device_init(&A, ka) && wireguard_device_init(&B, kb));
    int base = calls;
    struct wireguard_peer *ab = &A.peers[0], *ba = &B.peers[0];
    assert(wireguard_peer_init(&A, ab, B.public_key, NULL));
    assert(wireguard_peer_init(&B, ba, A.public_key, NULL));
    for (int i = 1; i < 13; i++) {                 /* the rest of a Tailnet map */
        uint8_t other[32], pub[32]; key(other, (uint8_t)(10 + i));
        x25519_real(pub, other, X25519_BASE_POINT, 1);
        assert(wireguard_peer_init(&A, &A.peers[i], pub, NULL));
    }
    assert(calls == base);                         /* adding peers costs no X25519 */
    assert(!ab->public_key_dh_ready && !ba->public_key_dh_ready);

    int before = calls;
    assert(handshake(ab, ba));
    int first = calls - before;
    assert(ab->public_key_dh_ready && ba->public_key_dh_ready);
    assert(ab->curr_keypair.valid && ab->curr_keypair.initiator && !resp_keys(ba)->initiator);
    assert(!memcmp(ab->curr_keypair.sending_key, resp_keys(ba)->receiving_key, 32));
    assert(!memcmp(ab->curr_keypair.receiving_key, resp_keys(ba)->sending_key, 32));
    assert(memcmp(ab->curr_keypair.sending_key, ab->curr_keypair.receiving_key, 32));

    now_ms += 10000;                                /* past the initiation rate limit */
    before = calls;
    assert(handshake(ab, ba));
    int second = calls - before;
    assert(second == first - 2);                    /* static DH reused on both sides */
    assert(!memcmp(ab->curr_keypair.sending_key, resp_keys(ba)->receiving_key, 32));
    for (int i = 1; i < 13; i++) assert(!A.peers[i].public_key_dh_ready);

    /* low-order key: added, handshake refused, nothing marked ready */
    uint8_t zero[32] = {0};
    struct wireguard_peer *bad = &A.peers[13];
    assert(wireguard_peer_init(&A, bad, zero, NULL));
    struct message_handshake_initiation init;
    assert(!wireguard_create_handshake_initiation(&A, bad, &init));
    assert(!bad->public_key_dh_ready);

    /* initiation from a key B does not know */
    struct wireguard_device C; uint8_t kc[32]; key(kc, 3);
    assert(wireguard_device_init(&C, kc));
    assert(wireguard_peer_init(&C, &C.peers[0], B.public_key, NULL));
    assert(wireguard_create_handshake_initiation(&C, &C.peers[0], &init));
    assert(wireguard_process_initiation_message(&B, &init) == NULL);
    printf("handshake ok: first %d X25519, next %d\n", first, second);
    return 0;
}
'''


def main():
    cc = os.environ.get('CC', 'gcc')
    flags = ['-std=gnu11', '-O1', '-w', '-DWIREGUARD_MAX_PEERS=16', '-DWIREGUARD_MAX_SRC_IPS=2',
             '-DBYTE_ORDER=1234', '-DLITTLE_ENDIAN=1234']
    if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    with tempfile.TemporaryDirectory(prefix='wg-handshake-') as folder:
        tmp = Path(folder)
        for name, text in FAKE_LWIP.items():
            (tmp / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp / name).write_text(text, encoding='utf-8')
        inc = ['-I', str(tmp), '-I', str(SRC), '-I', str(SRC / 'crypto/refc')]
        objects = []
        for rel in ('wireguard.c', 'crypto.c', 'crypto/refc/blake2s.c', 'crypto/refc/chacha20.c',
                    'crypto/refc/chacha20poly1305.c', 'crypto/refc/poly1305-donna.c'):
            obj = tmp / (rel.replace('/', '_') + '.o')
            subprocess.run([cc, *flags, *inc, '-c', str(SRC / rel), '-o', str(obj)], check=True)
            objects.append(obj)
        obj = tmp / 'x25519.o'
        subprocess.run([cc, *flags, *inc, '-Dx25519=x25519_real', '-c', str(SRC / 'crypto/refc/x25519.c'), '-o', str(obj)], check=True)
        objects.append(obj)
        (tmp / 'test.c').write_text(TEST, encoding='utf-8')
        exe = tmp / ('t.exe' if os.name == 'nt' else 't')
        subprocess.run([cc, *flags, *inc, str(tmp / 'test.c'), *map(str, objects), '-o', str(exe)], check=True)
        out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0 and 'handshake ok' in out.stdout, (out.returncode, out.stdout, out.stderr)
        print('wg handshake: actual wireguard.c both sides, keys agree; peers added without X25519; ' + out.stdout.strip().split(': ', 1)[1] +
              '; low-order and unknown keys refused')


if __name__ == '__main__':
    main()
