"""Package a verified ESP32-S3 image; never package NVS or a device flash dump."""
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import zipfile
import re
import json
from check_sensitive_data import credential_findings

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_release_version(version, current, prerelease):
    suffix = r'-dev(?:\.\d+)?' if prerelease else ''
    assert version == current and re.fullmatch(r'0\.1\.\d+-Mattboxx-\d+\.\d+' + suffix, version), \
        'Version must match the current project and the explicitly selected release channel'


def upstream_release_reference(version):
    base = version.split('-Mattboxx-', 1)[0]
    assert re.fullmatch(r'0\.1\.\d+', base), 'Invalid upstream release version'
    return f'Based on Csontikka/esp32-tailscale-subnet-router v{base}.'


def validate_build_description(description, root, version):
    assert description.get('project_name') == 'esp32_tsr', 'Unrelated project'
    assert description.get('project_version') == version, 'Stale build version'
    project = description.get('project_path') or description.get('project_dir')
    assert project and Path(project).resolve() == root.resolve(), 'Unrelated build directory'


def collect_release_notices(root, sdkbuild):
    """Carry original notices into binary distributions without local paths."""
    root = root.resolve()
    description = json.loads((sdkbuild / 'project_description.json').read_text(encoding='utf-8'))
    idf = Path(description['idf_path']).resolve()
    files = {root / 'LICENSE', root / 'NOTICE.md', idf / 'LICENSE',
             root / 'external/microlink/LICENSE', root / 'external/microlink/x25519-license.txt',
             root / 'external/microlink/components/microlink/components/wireguard_lwip/LICENSE'}
    assert all(path.is_file() for path in files), 'Required upstream license missing'
    for directory in description['build_component_paths']:
        if not directory:
            continue
        component = Path(directory).resolve()
        assert component.is_relative_to(root) or component.is_relative_to(idf), 'Unknown component origin'
        for path in component.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('', '.txt', '.md', '.rst') and \
                    path.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                files.add(path.resolve())
    records = []
    for path in files:
        if path.is_relative_to(idf):
            label = 'ESP-IDF/' + path.relative_to(idf).as_posix()
        else:
            label = 'project/' + path.relative_to(root).as_posix()
        records.append((label, path.read_text(encoding='utf-8')))
    header = ('Original authors retain their copyrights. This is ESP32 Tailnet Gateway, the Mattboxx custom edition.\n'
              'Optional tips support the mod; they do not purchase features or imply upstream endorsement.\n'
              'Source: ' + SOURCE_URL + '\n'
              'The following unmodified license/notice texts accompany the firmware distribution.\n')
    return header + ''.join('\n\n===== ' + label + ' =====\n\n' + content for label, content in sorted(records))


VARIANTS = {
    # name: (PlatformIO environment, update asset, factory image, package suffix)
    'wifi': ('esp32-s3', 'firmware.bin', 'firmware-factory.bin', ''),
    'eth': ('esp32-s3-eth', 'firmware-eth.bin', 'firmware-eth-factory.bin', '-eth'),
}
# The current repository name keeps working after the rename (GitHub redirects).
SOURCE_URL = 'https://github.com/Mattboxx/esp32-tailscale-gateway-NAS-recovery'


def release_readme(version, prerelease, variant):
    _, ota, factory, _ = VARIANTS[variant]
    channel = 'Development candidate (pre-release)' if prerelease else 'Stable community release'
    if variant == 'eth':
        board = ('ETHERNET VARIANT: only for an ESP32-S3 N16R8 with a W5500 SPI module wired\n'
                 'as documented in docs/ETHERNET.md. Experimental: not validated on real\n'
                 'W5500 hardware. It updates only from firmware-eth.bin. Use the normal\n'
                 'WiFi package unless the module is really fitted.')
    else:
        board = ('WIFI VARIANT (default) for ESP32-S3 N16R8 (16MB flash, 8MB octal PSRAM).\n'
                 'NOT for ESP32-C3/S2, boards without PSRAM, or the Ethernet wiring.')
    notes = f"{SOURCE_URL}/blob/Main/docs/RELEASE-{version.split('-Mattboxx-', 1)[1]}.md"
    title = f"ESP32 TAILNET GATEWAY - MATTBOXX EDITION - {version}" + (' (Ethernet)' if variant == 'eth' else '')
    lines = [
        title,
        'One ESP32. Multiple Tailnet roles. Enable only what you need.',
        f'{channel}. Community firmware, not an official Tailscale client.',
        '',
        board,
        '',
        'FILES',
        f'  {ota:<28} update image: Web UI (System > Firmware) or opt-in updater',
        f'  {factory:<28} fresh install at offset 0x0 - ERASES ALL SETTINGS',
        '  UPDATE_KEEP_SETTINGS.bat     Windows USB update, keeps settings',
        '  CLEAN_INSTALL_ERASE_ALL.bat  Windows fresh install, asks for YES',
        '  SHA256SUMS.txt               checksums; VERIFY_FILES.ps1 checks them',
        '  release-manifest.json        machine-readable build and file metadata',
        '',
        'UPDATE (keeps settings): back up first (System > Backup). Then Web UI >',
        f'System > Firmware > choose {ota} > Upload. A failed boot returns to the',
        'previous image. Or connect USB and double-click UPDATE_KEEP_SETTINGS.bat',
        '(optional: UPDATE_KEEP_SETTINGS.bat COM5).',
        '',
        'FRESH INSTALL (erases everything): CLEAN_INSTALL_ERASE_ALL.bat, or on Linux/macOS:',
        '  python3 -m pip install esptool',
        '  sha256sum -c SHA256SUMS.txt       (macOS: shasum -a 256 -c SHA256SUMS.txt)',
        f'  esptool.py --chip esp32s3 --baud 921600 write_flash 0x0 {factory}',
        '',
        'Use a USB DATA cable. If the port is not detected: hold BOOT, tap RESET,',
        'release BOOT and retry. Do not unplug while flashing.',
        '',
        f'RECOVERY: keep the previous release. Upload its {ota} the same way, or do a',
        'fresh install and restore your configuration backup.',
        '',
        f'{upstream_release_reference(version)} Highlights: selective LAN-to-Tailnet',
        'Service Gateway, subnet router, AP gateway, exit node, Wake-on-LAN and bounded',
        'recovery, optional MQTT/Home Assistant/ntfy/SNMP, simple and advanced modes,',
        'Web UI in English, Italian, Spanish and Simplified Chinese.',
        'No telemetry or crash upload. GitHub update checks are opt-in and contact only',
        "the project's release repository and GitHub's asset CDN.",
        '',
        'The Web UI is HTTP: administer from a trusted LAN or over the tailnet.',
        'SNMPv1/v2c is unencrypted and OFF by default. A release channel is not a',
        'guarantee that every configuration was tested; see the release notes:',
        notes,
        'Original credits: Csontikka/esp32-tailscale-subnet-router, Csontikka/microlink',
        'and their contributors. Notices: FIRMWARE-LICENSES.txt.',
        'Optional support for the Mattboxx edition: https://ko-fi.com/mattboxx',
        '',
        'esptool.exe: Espressif esptool v5.3.1 Windows amd64, GPL-2.0-or-later.',
        'Source: https://github.com/espressif/esptool/tree/v5.3.1',
        'Included license: ESPTOOL-LICENSE.txt. No user configuration or NVS is included.',
    ]
    return '\n'.join(lines) + '\n'


def release_manifest(version, prerelease, variant, files, description):
    env, ota, factory, _ = VARIANTS[variant]
    return {
        'product': 'ESP32 Tailnet Gateway - Mattboxx Edition',
        'version': version,
        'channel': 'pre-release' if prerelease else 'stable',
        'variant': variant,
        'platformio_env': env,
        'chip': 'esp32s3',
        'board': 'ESP32-S3 N16R8 (16MB flash, 8MB octal PSRAM)' + (', W5500 SPI Ethernet' if variant == 'eth' else ''),
        'app_identity': description.get('project_name'),
        'update_asset': ota,
        'factory_asset': factory,
        'flash': {'bootloader': '0x0', 'partitions': '0x8000', 'otadata': '0x19000', 'app': '0x20000', 'app_slot_bytes': 1966080},
        'files': files,
        'source': SOURCE_URL,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--prerelease', action='store_true',
                        help='Explicitly package a development candidate, never label it stable')
    parser.add_argument('--tested-image', type=Path, required=True)
    parser.add_argument('--tested-sha256', required=True)
    parser.add_argument('--esptool', type=Path, required=True)
    parser.add_argument('--esptool-license', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path,
                        help='Exact PlatformIO environment directory, if built outside .pio')
    parser.add_argument('--variant', choices=sorted(VARIANTS), default='wifi',
                        help='wifi (default image) or eth (W5500 build, separate assets)')
    args = parser.parse_args()
    version = args.version
    project_version = re.search(r'set\(PROJECT_VER "([^"]+)"\)', (ROOT / 'CMakeLists.txt').read_text())[1]
    validate_release_version(version, project_version, args.prerelease)
    env, ota_name, factory_name, suffix = VARIANTS[args.variant]
    sdkbuild = (args.build_dir or ROOT / '.pio/build' / env).resolve()
    description = json.loads((sdkbuild / 'project_description.json').read_text(encoding='utf-8'))
    validate_build_description(description, ROOT, version)
    assert sha(args.tested_image) == args.tested_sha256.lower()
    assert sha(sdkbuild / 'firmware.bin') == args.tested_sha256.lower(), 'Build changed after hardware validation'
    assert version.encode() in args.tested_image.read_bytes()
    if not args.prerelease:
        assert (version + '-dev').encode() not in args.tested_image.read_bytes()
    config = (sdkbuild / 'config/sdkconfig.h').read_text()
    assert '#define CONFIG_LWIP_MAX_SOCKETS 31' in config
    # The image must be the variant it claims and update only from its own asset.
    assert ('#define CONFIG_ETH_SPI_ETHERNET_W5500 1' in config) == (args.variant == 'eth'), 'Variant does not match the build'
    image_bytes = args.tested_image.read_bytes()
    assert ('/' + ota_name).encode() in image_bytes, 'Updater asset name missing from the image'
    if args.variant == 'wifi':
        assert b'firmware-eth.bin' not in image_bytes
    out = ROOT / 'build' / ('release-' + version + suffix)
    out.mkdir(exist_ok=False)
    shutil.copyfile(args.tested_image, out / ota_name)
    for name in ('bootloader.bin', 'partitions.bin', 'ota_data_initial.bin'):
        shutil.copyfile(sdkbuild / name, out / name)
    shutil.copyfile(args.esptool, out / 'esptool.exe')
    shutil.copyfile(args.esptool_license, out / 'ESPTOOL-LICENSE.txt')
    (out / 'FIRMWARE-LICENSES.txt').write_text(collect_release_notices(ROOT, sdkbuild), encoding='utf-8')
    for path in (ROOT / 'tools/flashing').iterdir():
        # Windows double-click scripts must carry CRLF, also in Linux builds.
        text = path.read_text(encoding='utf-8').replace('firmware-factory.bin', factory_name).replace('firmware.bin', ota_name)
        (out / path.name).write_bytes(text.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8'))
    subprocess.run([str(args.esptool.resolve()), '--chip', 'esp32s3', 'merge-bin',
        '--flash-mode', 'dio', '--flash-freq', '80m', '--flash-size', '4MB',
        '-o', str(out / factory_name),
        '0x0', str(out / 'bootloader.bin'), '0x8000', str(out / 'partitions.bin'),
        '0x19000', str(out / 'ota_data_initial.bin'), '0x20000', str(out / ota_name)], check=True)
    full = (out / factory_name).read_bytes()
    # Original 4MB layout: 64KB NVS at 0x9000; factory must contain no settings.
    assert full[0x9000:0x19000] == b'\xff' * 0x10000
    assert full[0x20000:0x20000 + args.tested_image.stat().st_size] == args.tested_image.read_bytes()
    readme = release_readme(version, args.prerelease, args.variant)
    (out / 'README.txt').write_bytes(readme.replace('\n', '\r\n').encode('utf-8'))
    payload = sorted(path.name for path in out.iterdir())
    files = {name: {'sha256': sha(out / name), 'bytes': (out / name).stat().st_size} for name in payload}
    manifest_data = release_manifest(version, args.prerelease, args.variant, files, description)
    (out / 'release-manifest.json').write_text(json.dumps(manifest_data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    names = sorted(path.name for path in out.iterdir())
    for name in names:
        assert not credential_findings((out / name).read_bytes(), True), f'Credential pattern in {name}'
    manifest = ''.join(f'{sha(out / name)}  {name}\n' for name in names)
    (out / 'SHA256SUMS.txt').write_text(manifest, encoding='ascii')
    archive = out / f'ESP32-Tailnet-Gateway-{version}{suffix}-windows.zip'
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
    assets = [out / ota_name, out / factory_name, archive, out / 'FIRMWARE-LICENSES.txt', out / 'release-manifest.json']
    (out / 'RELEASE-SHA256SUMS.txt').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in assets), encoding='ascii')
    print('PASS: exact tested image, blank NVS, factory application, ZIP CRC, payload hashes and credential patterns')
    for path in assets:
        print(path.name, path.stat().st_size, sha(path))


if __name__ == '__main__':
    main()
