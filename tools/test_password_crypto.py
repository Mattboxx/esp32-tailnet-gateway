"""Check the migrated password and proof code against existing record formats."""

import hashlib
import hmac
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'components/web_password/web_password.c').read_text(encoding='utf-8')
TF = Path(os.environ['MBEDTLS_DIR']) / 'tf-psa-crypto'
BUILD = Path(os.environ.get('TFPSA_BUILD', str(ROOT / 'build/host-crypto')))


def extract(signature):
    start = SOURCE.index(signature)
    body = SOURCE.index('{', start)
    depth = 1
    for index in range(body + 1, len(SOURCE)):
        char = SOURCE[index]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if not depth:
                return SOURCE[start:index + 1]
    raise AssertionError(signature)


header = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mbedtls/md.h"
#include "psa/crypto.h"
#define WEB_PASSWORD_PROOF_LEN 32
static const char *stored_record;
static char *nvs_dup_str(const char *key)
{
    assert(!strcmp(key, "web_password"));
    size_t size = strlen(stored_record) + 1;
    char *value = malloc(size);
    assert(value);
    memcpy(value, stored_record, size);
    return value;
}
'''
definitions = [line for line in SOURCE.splitlines() if line.startswith('#define PW_')]
functions = [extract(signature) for signature in (
    'static int hex_to_bytes(', 'static bool compute_hash(', 'static bool compute_pbkdf2(',
    'static bool hashes_equal(', 'static bool verify_legacy_sha256(',
    'static bool verify_pbkdf2(', 'static bool parse_pbkdf2_record(',
    'bool verify_web_password_proof(',
)]
driver = r'''
int main(int argc, char **argv)
{
    assert(argc == 4 || argc == 5);
    assert(psa_crypto_init() == PSA_SUCCESS);
    stored_record = argv[2];
    bool ok = false;
    if (!strcmp(argv[1], "legacy"))
        ok = verify_legacy_sha256(stored_record, argv[3]);
    else if (!strcmp(argv[1], "password"))
        ok = verify_pbkdf2(stored_record, argv[3]);
    else {
        assert(argc == 5 && strlen(argv[4]) == WEB_PASSWORD_PROOF_LEN * 2);
        uint8_t proof[WEB_PASSWORD_PROOF_LEN];
        assert(!hex_to_bytes(argv[4], proof, sizeof proof));
        ok = verify_web_password_proof((const uint8_t *)argv[3], strlen(argv[3]), proof);
    }
    puts(ok ? "ok" : "denied");
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='pw-crypto-') as temp:
        path = Path(temp)
        source = path / 'test.c'
        source.write_text('\n'.join([header, *definitions, *functions, driver]), encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-O2']
        if os.environ.get('PASSWORD_CRYPTO_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        config = '-DTF_PSA_CRYPTO_CONFIG_FILE="' + str(BUILD / 'crypto-config.h') + '"'
        includes = [TF / 'include', TF / 'drivers/builtin/include', BUILD / 'include']
        command = [os.environ.get('CC', 'gcc'), *flags, config]
        for include in includes:
            command += ['-I', str(include)]
        command += [str(source), str(BUILD / 'core/libtfpsacrypto.a'),
                    str(BUILD / 'platform/libplatform.a'), '-o', str(exe)]
        if os.name == 'nt':
            command += ['-lbcrypt']
        subprocess.run(command, check=True)

        def accepts(*args):
            run = subprocess.run([str(exe), *args], check=True, capture_output=True, text=True, timeout=20)
            return run.stdout.strip() == 'ok'

        password = 'sample passphrase'
        salt = bytes(range(16))
        iterations = 60000
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
        record = f'pbkdf2-sha256${iterations}${salt.hex()}${key.hex()}'
        legacy = f'{salt.hex()}:{hashlib.sha256(salt + password.encode()).hexdigest()}'
        assert accepts('password', record, password)
        assert not accepts('password', record, 'wrong')
        assert not accepts('password', record.replace('$60000$', '$1$'), password)
        assert accepts('legacy', legacy, password)
        assert not accepts('legacy', legacy, 'wrong')
        message = 'test session challenge'
        proof = hmac.new(key, message.encode(), hashlib.sha256).hexdigest()
        assert accepts('proof', record, message, proof)
        assert not accepts('proof', record, 'different challenge', proof)
        assert not accepts('proof', record, message, '00' * 32)
        assert not accepts('proof', legacy, message, proof)
    print('PASS stored PBKDF2, legacy hash and challenge proof against the SDK software crypto')


if __name__ == '__main__':
    main()
