"""WireGuard data-path zeroing (3.0.7-beta.9): actual MicroLink C on the host.

- wg_tx_zero_unwritten(): the bytes that reach the encryption are identical
  to the former "zero everything, then copy" for every plaintext length,
  keepalives and a pbuf longer than the message; the plaintext area is not
  written twice.
Also checks that decryption no longer zeroes the plaintext first, that a
short pbuf copy on transmit cannot leave stale bytes, and that the measured
but rejected RX variants (zero-copy hand-off, DCache preload) are not built.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
mgr = (ML / 'src/ml_wg_mgr.c').read_text(encoding='utf-8').replace('\r\n', '\n')
wg = (ML / 'components/wireguard_lwip/src/wireguardif.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]


zero = function(wg, 'static void wg_tx_zero_unwritten(')
rx = wg[wg.index('static void wireguardif_process_data_message('):]
rx = rx[:rx.index('\n}\n')]
assert 'memset(pbuf->payload, 0, pbuf->tot_len)' not in wg, 'whole-buffer zeroing is gone'
assert 'bool decrypt_ok = wireguard_decrypt_packet(pbuf->payload, src, src_len, nonce, keypair);' in rx
assert 'if (copied < unpadded_len) memset(dst + copied, 0, unpadded_len - copied);' in wg
assert 'wg_tx_zero_unwritten(pbuf->payload, header_len, unpadded_len, padded_len, pbuf->tot_len);' in wg
process = function(mgr, 'static void process_wg_packet(')
assert 'Cache_Start_DCache_Preload' not in mgr and 'PBUF_REF);' not in process
assert 'pbuf_alloc(PBUF_RAW, pkt->len, PBUF_RAM);' in process and 'pbuf_take(p, pkt->data, pkt->len);' in process

PROGRAM = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define WIREGUARD_AUTHTAG_LEN 16
''' + zero + r'''
int main(void) {
    /* TX zeroing equals the former full zeroing for what is encrypted and sent. */
    for (size_t plain = 0; plain <= 70; plain++) {
        for (size_t extra = 0; extra <= 8; extra += 8) {
            size_t padded = (plain + 15) & ~(size_t)15, out_len = 16 + padded + 16, tot = out_len + extra;
            uint8_t before[128], after[128], text[80];
            for (size_t i = 0; i < plain; i++) text[i] = (uint8_t)(i * 7 + 3);
            memset(before, 0, tot); memcpy(before + 16, text, plain);
            memset(after, 0xaa, tot);
            wg_tx_zero_unwritten(after, 16, plain, padded, tot);
            for (size_t i = 16; i < 16 + plain; i++) assert(after[i] == 0xaa);   /* not written twice */
            memcpy(after + 16, text, plain);
            assert(!memcmp(before, after, 16 + padded));                         /* header + plaintext + padding */
            assert(!memcmp(before + out_len, after + out_len, extra));           /* past the tag */
        }
    }
    puts("PASS: TX zeroing equal to full zeroing for 0-70 byte plaintexts, keepalives and longer pbufs; no "
         "pre-decrypt zeroing; short TX copy padded; rejected RX variants absent (host)");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='wg-rx-path-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror']
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
