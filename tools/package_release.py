"""Package a verified ESP32-S3 image; never package NVS or a device flash dump."""
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import zipfile
from check_sensitive_data import credential_findings

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--tested-image', type=Path, required=True)
    parser.add_argument('--tested-sha256', required=True)
    parser.add_argument('--esptool', type=Path, required=True)
    parser.add_argument('--esptool-license', type=Path, required=True)
    args = parser.parse_args()
    version = args.version
    assert version == '0.1.28-Mattboxx-1.6'
    sdkbuild = ROOT / '.pio/build/esp32-s3'
    assert sha(args.tested_image) == args.tested_sha256.lower()
    assert sha(sdkbuild / 'firmware.bin') == args.tested_sha256.lower(), 'Build changed after hardware validation'
    assert version.encode() in args.tested_image.read_bytes()
    assert b'Mattboxx-1.6-dev' not in args.tested_image.read_bytes()
    assert '#define CONFIG_LWIP_MAX_SOCKETS 26' in (sdkbuild / 'config/sdkconfig.h').read_text()
    out = ROOT / 'build' / ('release-' + version)
    out.mkdir(exist_ok=False)
    shutil.copyfile(args.tested_image, out / 'firmware.bin')
    for name in ('bootloader.bin', 'partitions.bin', 'ota_data_initial.bin'):
        shutil.copyfile(sdkbuild / name, out / name)
    shutil.copyfile(args.esptool, out / 'esptool.exe')
    shutil.copyfile(args.esptool_license, out / 'ESPTOOL-LICENSE.txt')
    for path in (ROOT / 'tools/flashing').iterdir():
        # Windows double-click scripts must carry CRLF, also in Linux builds.
        (out / path.name).write_bytes(path.read_text(encoding='utf-8').replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
    subprocess.run([str(args.esptool.resolve()), '--chip', 'esp32s3', 'merge-bin',
        '--flash-mode', 'dio', '--flash-freq', '80m', '--flash-size', '4MB',
        '-o', str(out / 'firmware-factory.bin'),
        '0x0', str(out / 'bootloader.bin'), '0x8000', str(out / 'partitions.bin'),
        '0x19000', str(out / 'ota_data_initial.bin'), '0x20000', str(out / 'firmware.bin')], check=True)
    full = (out / 'firmware-factory.bin').read_bytes()
    # Original 4MB layout: 64KB NVS at 0x9000; factory must contain no settings.
    assert full[0x9000:0x19000] == b'\xff' * 0x10000
    assert full[0x20000:0x20000 + args.tested_image.stat().st_size] == args.tested_image.read_bytes()
    readme = f'''ESP32 TAILSCALE GATEWAY - {version}
Stable community release for ESP32-S3 N16R8 (16MB flash, 8MB octal PSRAM).
Uses the existing 4MB partition layout. NOT for an ESP32-C3, S2, no-PSRAM
board, or an Ethernet-specific wiring configuration.

RECOMMENDED UPDATE: System > Firmware update > select firmware.bin > Upload.
This authenticated OTA update preserves settings and uses the inactive slot.
For USB update: connect the board, close serial monitors, double-click
UPDATE_KEEP_SETTINGS.bat. Optional command: UPDATE_KEEP_SETTINGS.bat COM5
Use your actual COM port. The script checks all package hashes before writing.

CLEAN_INSTALL_ERASE_ALL.bat is for a fresh install ONLY. It requires YES,
erases the entire flash and loses WiFi/passwords/Tailscale identity/all settings.
firmware-factory.bin is the merged fresh-board image, NOT a web OTA image.
Do not unplug during flashing. Use a USB DATA cable, not a charge-only cable.
If detection fails: hold BOOT, tap RESET, release BOOT and retry.

Based on Csontikka/esp32-tailscale-subnet-router v0.1.28 with its following
URI-registration fix. Preserves MQTT/HA, WOL, ntfy, AP policy, LAN-to-Tailnet
forwarding, 4via6, exit advertising, custom web port and password/session policy.
Includes Automation loading fixes, a pinned IDF 5.5.3/26-socket build, read-only
SNMP (OFF by default), malformed-packet hardening and checked HTTP endpoints.
No telemetry, external crash upload, release polling or public speed test.
Optional user-enabled MQTT/ntfy and the VPN still make their configured traffic.

SNMPv1/v2c is unencrypted. Keep it OFF unless needed, choose a private community
and restrict UDP 161 with the firewall. Web UI is HTTP: trusted LAN/tailnet only.
Stable is a release channel, not a security certification; hardware coverage and
limitations: https://github.com/Mattboxx/esp32-tailscale-gateway/blob/Main/docs/RELEASE-1.6.md
Original credits: Csontikka/router, Csontikka/microlink and their contributors.

esptool.exe: Espressif esptool v5.3.1 Windows amd64, GPL-2.0-or-later.
Source: https://github.com/espressif/esptool/tree/v5.3.1
Included license: ESPTOOL-LICENSE.txt. No user configuration or NVS is included.
'''
    (out / 'README.txt').write_bytes(readme.replace('\n', '\r\n').encode('utf-8'))
    names = sorted(path.name for path in out.iterdir())
    for name in names:
        assert not credential_findings((out / name).read_bytes(), True), f'Credential pattern in {name}'
    manifest = ''.join(f'{sha(out / name)}  {name}\n' for name in names)
    (out / 'SHA256SUMS.txt').write_text(manifest, encoding='ascii')
    archive = out / f'ESP32-S3-router-{version}-windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in names + ['SHA256SUMS.txt']:
            z.write(out / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in z.namelist():
            assert not credential_findings(z.read(name), True), f'Credential pattern in ZIP {name}'
        for line in z.read('SHA256SUMS.txt').decode().splitlines():
            digest, name = line.split('  ', 1)
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
    assets = [out / 'firmware.bin', out / 'firmware-factory.bin', archive]
    (out / 'RELEASE-SHA256SUMS.txt').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in assets), encoding='ascii')
    print('PASS: exact tested image, blank NVS, factory application, ZIP CRC, payload hashes and credential patterns')
    for path in assets:
        print(path.name, path.stat().st_size, sha(path))


if __name__ == '__main__':
    main()
