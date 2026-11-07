"""Distrusted eMudhra intermediates (ml_tls_distrust.c) against the real
mbedTLS 3.6.5 of the pinned SDK and the real certificates, on the host.

The eight compromised intermediate keys have private scalars below 256, so the
test derives them from the public certificates (as an attacker can), forges a
certificate for controlplane.tailscale.com under "EM DV TLS CA - G3B"
cross-signed by AAA Certificate Services, and checks with mbedtls_x509_crt_verify:
- without the wrapper the forged chain is accepted (the exposure is real for a
  store that still holds that root, as the ESP-IDF bundle does);
- with ml_tls_bundle_attach it is refused, also when the bundle callback
  clears the flags of the certificate it anchors;
- a normal chain is still accepted;
- all 16 published certificates are matched by SPKI, the roots and an
  unrelated root are not, NULL/empty/one-bit-changed keys are not;
- attach failure, NULL configuration, a missing bundle callback and a second
  attach behave as documented; the refusal counter counts.
Also checks that every bundle user in the firmware goes through the wrapper.
MBEDTLS_DIR selects the mbedTLS tree (default: the pinned SDK).
"""
import datetime
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import warnings

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
ML = ROOT / 'external/microlink/components/microlink'
MBED = Path(os.environ.get('MBEDTLS_DIR', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/mbedtls/mbedtls')))
# The pinned SDK's certificate bundle (CI: sparse ESP-IDF checkout, CRT_BUNDLE).
BUNDLE = Path(os.environ.get('CRT_BUNDLE', str(MBED.parent / 'esp_crt_bundle/cacrt_all.pem')))
FIXTURE = ROOT / 'tools/fixtures/emudhra-compromised-intermediates.crt'
AAA_SHA256 = 'D7A7A0FB5D7E2731D771E9484EBCDEF71D5F0C3E0A2948782BC83EE0EA699EF4'
EMSIGN_ECC_G3_SHA256 = '86A1ECBA089C4A8D3BBE2734C612BA341D813E043CF9E8A862CD5C57A36BBE6B'
ISRG_X1_SHA256 = '96BCEC06264976F37460779ACF28C5A7CFE8A3C0AAE11A8FFCEE05C0BDDF08C6'

# Every bundle user goes through the wrapper.
sources = list((ROOT / 'main').glob('*.c')) + list((ML / 'src').glob('*.c'))
for path in sources:
    text = path.read_text(encoding='utf-8', errors='replace')
    if path.name != 'ml_tls_distrust.c':
        assert not re.search(r'\besp_crt_bundle_attach\b(?!\.h)', text.replace('esp_crt_bundle.h', '')), path.name
users = [p.name for p in sources if 'ml_tls_bundle_attach' in p.read_text(encoding='utf-8', errors='replace')]
assert {'ml_coord.c', 'ml_derp.c', 'ota_remote.c', 'mqtt_integration.c', 'ntfy_integration.c', 'notify_channels.c',
        'ddns.c', 'layout_migration.c', 'throughput.c'} <= set(users), users
assert '"src/ml_tls_distrust.c"' in (ML / 'CMakeLists.txt').read_text(encoding='utf-8')
assert 'cJSON_AddNumberToObject(td, "refused_chains", ml_tls_distrust_refusals());' in (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')


def pems(text):
    return [m.group(0) for m in re.finditer(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', text, re.S)]


def by_sha(certs, sha):
    for c in certs:
        if hashlib.sha256(c.public_bytes(serialization.Encoding.DER)).hexdigest().upper() == sha:
            return c
    raise AssertionError('certificate not found: ' + sha)


compromised = [x509.load_pem_x509_certificate(p.encode()) for p in pems(FIXTURE.read_text(encoding='utf-8'))]
assert len(compromised) == 16
warnings.filterwarnings('ignore', message='Parsed a serial number')   # one legacy bundle root
bundle = [x509.load_pem_x509_certificate(p.encode()) for p in pems(BUNDLE.read_text(encoding='utf-8'))]
aaa, emsign_g3, isrg = (by_sha(bundle, s) for s in (AAA_SHA256, EMSIGN_ECC_G3_SHA256, ISRG_X1_SHA256))
cross = next(c for c in compromised if 'EM DV TLS CA - G3B' in c.subject.rfc4514_string() and c.issuer == aaa.subject)

# The weak key, recovered from the public certificate.
target = cross.public_key().public_numbers()
weak = next(ec.derive_private_key(d, ec.SECP384R1()) for d in range(1, 256)
            if ec.derive_private_key(d, ec.SECP384R1()).public_key().public_numbers() == target)

now = datetime.datetime.now(datetime.timezone.utc)


def leaf(issuer_name, issuer_key, name):
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
            .issuer_name(issuer_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(issuer_key, hashes.SHA384()))
    return cert


forged = leaf(cross.subject, weak, 'controlplane.tailscale.com')
good_key = ec.generate_private_key(ec.SECP256R1())
good_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test Root')])
good_root = (x509.CertificateBuilder().subject_name(good_name).issuer_name(good_name).public_key(good_key.public_key())
             .serial_number(1).not_valid_before(now - datetime.timedelta(days=1))
             .not_valid_after(now + datetime.timedelta(days=60))
             .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
             .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
             .sign(good_key, hashes.SHA256()))
good_leaf = leaf(good_name, good_key, 'controlplane.tailscale.com')

PROGRAM = r'''
#define ML_TLS_HOST_TEST 1
#include "ml_tls_distrust.c"
#include <assert.h>
#include <stdio.h>
static int attach_rc, bundle_calls, clear_flags, set_callback = 1;
static int bundle_cb(void *ctx, mbedtls_x509_crt *crt, int depth, uint32_t *flags)
{
    (void)crt; (void)depth;
    assert(ctx == (void *)&bundle_calls);
    bundle_calls++;
    if (clear_flags) *flags = 0;
    return 0;
}
esp_err_t esp_crt_bundle_attach(void *conf)
{
    if (attach_rc) return attach_rc;
    if (conf && set_callback) mbedtls_ssl_conf_verify(conf, bundle_cb, &bundle_calls);
    return ESP_OK;
}
static mbedtls_x509_crt load(const char *path)
{
    mbedtls_x509_crt c; mbedtls_x509_crt_init(&c);
    assert(mbedtls_x509_crt_parse_file(&c, path) == 0);
    return c;
}
static int verify(mbedtls_x509_crt *chain, mbedtls_x509_crt *ca, mbedtls_ssl_config *conf, uint32_t *flags)
{
    return mbedtls_x509_crt_verify(chain, ca, NULL, "controlplane.tailscale.com", flags,
                                   conf ? conf->f_vrfy : NULL, conf ? conf->p_vrfy : NULL);
}
int main(int argc, char **argv)
{
    (void)argc;
    mbedtls_x509_crt forged = load(argv[1]), aaa = load(argv[2]), good = load(argv[3]), good_root = load(argv[4]);
    mbedtls_x509_crt compromised = load(argv[5]), roots = load(argv[6]);
    uint32_t flags = 99;
    /* The exposure: real mbedTLS accepts the forged chain under a still-trusted root. */
    assert(verify(&forged, &aaa, NULL, &flags) == 0 && flags == 0);
    mbedtls_ssl_config conf; mbedtls_ssl_config_init(&conf);
    assert(ml_tls_bundle_attach(&conf) == ESP_OK && conf.f_vrfy == distrust_verify && conf.p_vrfy == &bundle_calls);
    flags = 0;
    assert(verify(&forged, &aaa, &conf, &flags) != 0 && (flags & MBEDTLS_X509_BADCERT_NOT_TRUSTED));
    assert(bundle_calls > 0 && ml_tls_distrust_refusals() == 1);
    clear_flags = 1; flags = 0;   /* a bundle callback that clears its anchor's flags cannot undo it */
    assert(verify(&forged, &aaa, &conf, &flags) != 0 && (flags & MBEDTLS_X509_BADCERT_NOT_TRUSTED));
    clear_flags = 0; flags = 99;
    assert(verify(&good, &good_root, &conf, &flags) == 0 && flags == 0);   /* normal chains unaffected */
    assert(ml_tls_distrust_refusals() == 2);
    /* All 16 published certificates match; the roots and an unrelated root do not. */
    unsigned n = 0;
    for (mbedtls_x509_crt *c = &compromised; c && c->raw.len; c = c->next, n++)
        assert(ml_tls_spki_distrusted(c->pk_raw.p, c->pk_raw.len));
    assert(n == 16);
    unsigned r = 0;
    for (mbedtls_x509_crt *c = &roots; c && c->raw.len; c = c->next, r++)
        assert(!ml_tls_spki_distrusted(c->pk_raw.p, c->pk_raw.len));
    assert(r == 4);
    assert(!ml_tls_spki_distrusted(NULL, 10) && !ml_tls_spki_distrusted(compromised.pk_raw.p, 0));
    uint8_t changed[200]; assert(compromised.pk_raw.len <= sizeof changed);
    memcpy(changed, compromised.pk_raw.p, compromised.pk_raw.len); changed[compromised.pk_raw.len - 1] ^= 1;
    assert(!ml_tls_spki_distrusted(changed, compromised.pk_raw.len));
    /* Attach paths. */
    assert(ml_tls_bundle_attach(NULL) == ESP_OK);
    assert(ml_tls_bundle_attach(&conf) == ESP_OK && conf.f_vrfy == distrust_verify);   /* again: no recursion */
    flags = 0; bundle_calls = 0;
    assert(verify(&forged, &aaa, &conf, &flags) != 0 && bundle_calls > 0 && bundle_calls < 10);
    mbedtls_ssl_config other; mbedtls_ssl_config_init(&other);
    attach_rc = ESP_FAIL; assert(ml_tls_bundle_attach(&other) == ESP_FAIL && other.f_vrfy == NULL);
    attach_rc = 0; set_callback = 0; assert(ml_tls_bundle_attach(&other) == ESP_FAIL && other.f_vrfy == NULL);
    /* Everything parsed is released (LeakSanitizer runs on the Linux CI). */
    mbedtls_ssl_config_free(&other);
    mbedtls_ssl_config_free(&conf);
    mbedtls_x509_crt *all[] = {&forged, &aaa, &good, &good_root, &compromised, &roots};
    for (unsigned i = 0; i < sizeof all / sizeof all[0]; i++) mbedtls_x509_crt_free(all[i]);
    puts("PASS: forged controlplane.tailscale.com chain under a compromised eMudhra intermediate (key derived from its "
         "public certificate) is accepted by plain mbedTLS 3.6.5 and refused through ml_tls_bundle_attach, also when the "
         "bundle callback clears flags; normal chains pass; 16/16 published certificates matched by SPKI, 4 roots not; "
         "NULL/empty/changed keys, attach failure, NULL conf, missing callback and re-attach handled; every bundle user "
         "in main and MicroLink uses the wrapper (host)");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='tls-distrust-') as folder:
        path = Path(folder)
        pem = lambda *certs: ''.join(c.public_bytes(serialization.Encoding.PEM).decode() for c in certs)
        (path / 'forged.pem').write_text(pem(forged, cross))
        (path / 'aaa.pem').write_text(pem(aaa))
        (path / 'good.pem').write_text(pem(good_leaf))
        (path / 'good_root.pem').write_text(pem(good_root))
        (path / 'compromised.pem').write_text(pem(*compromised))
        (path / 'roots.pem').write_text(pem(aaa, emsign_g3, isrg, good_root))
        (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n')
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        library = sorted(str(p) for p in (MBED / 'library').glob('*.c'))
        flags = ['-std=c11', '-O1', '-w', '-I', str(path), '-I', str(ML / 'include'), '-I', str(ML / 'src'),
                 '-I', str(MBED / 'include'), '-I', str(MBED / 'library')]
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        libs = ['-lws2_32', '-lbcrypt'] if os.name == 'nt' else []
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), *library, '-o', str(exe), *libs],
                       check=True)
        run = subprocess.run([str(exe)] + [str(path / n) for n in ('forged.pem', 'aaa.pem', 'good.pem', 'good_root.pem',
                                                                   'compromised.pem', 'roots.pem')],
                             capture_output=True, text=True, timeout=60)
        print(run.stdout, end='')
        assert run.returncode == 0, (run.returncode, run.stdout[-2000:], run.stderr[-4000:])


if __name__ == '__main__':
    main()
