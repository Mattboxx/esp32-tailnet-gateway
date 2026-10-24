"""Package an exact, already tested firmware 2.x image for release (local only).

Outputs build/release-v<version>/:
  ESP32-Tailnet-Gateway-v<version>-EASY-INSTALL-Windows-macOS-Linux.zip
      guided scripts for Windows (bundled esptool.exe) and macOS/Linux,
      with every Web UI language image to choose from
  assets/        files to attach to the GitHub release (firmware.bin,
                 firmware-<lang>.bin and firmware-eth.bin keep their names
                 for the updaters)
  web-installer/ files for website/firmware/<version>/ (ESP Web Tools):
                 the standard English image only

Never rebuilds: the tested image must match --tested-sha256 (ADR-026). The
Ethernet image is labelled experimental. No NVS or device data is included.

    python tools/package_v2.py --version 2.0.0-rc.1 --prerelease \
        --wifi-dir build/development-2.0.0-rc.1/target/esp32-s3 \
        --tested-sha256 <sha> [--eth-dir .../esp32-s3-eth] \
        [--lang-dir it=.../esp32-s3-it --lang-sha256 it=<sha> ...] \
        --esptool build/release-0.1.38-Mattboxx-1.13/esptool.exe \
        --esptool-license build/release-0.1.38-Mattboxx-1.13/ESPTOOL-LICENSE.txt
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile

from check_sensitive_data import credential_findings
from package_release import collect_release_notices, validate_build_description

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).resolve().parent / 'easy_install'
PRODUCT = 'ESP32 Tailnet Gateway - Mattboxx Edition'
CURRENT_REPOSITORY = 'Mattboxx/esp32-tailscale-gateway-NAS-recovery'
RENAMED_REPOSITORY = 'Mattboxx/esp32-tailnet-gateway'
# Offsets from sdkconfig (bootloader, partition table) and partitions.csv.
LAYOUT = {'bootloader.bin': 0x0, 'partitions.bin': 0x8000, 'ota_data_initial.bin': 0x19000, 'firmware.bin': 0x20000}
NVS = (0x9000, 0x19000)
FLASH_ARGS = ['--flash-mode', 'dio', '--flash-freq', '80m', '--flash-size', '4MB']
# Web UI language variants of the WiFi image (English plus one language).
LANGUAGES = {'it': 'Italiano', 'es': 'Español', 'zh': '简体中文'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repository_url(repository):
    """Do not ship premature renamed URLs during the bridge migration window."""
    assert repository in (CURRENT_REPOSITORY, RENAMED_REPOSITORY), 'Unknown release repository'
    return 'https://github.com/' + repository


def validate_version(version, project_version, prerelease):
    assert version == project_version, 'Version differs from CMakeLists PROJECT_VER'
    m = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(-(?:dev|alpha|beta|rc)\.\d+)?', version)
    assert m and int(m.group(1)) >= 2, 'Product versions start at 2.0.0'
    assert bool(m.group(4)) == prerelease, 'Use --prerelease exactly for -dev/-alpha/-beta/-rc versions'


def check_partitions():
    rows = {}
    for line in (ROOT / 'partitions.csv').read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.split(',')]
        if len(cells) >= 4 and not cells[0].startswith('#') and cells[3]:
            rows[cells[0]] = int(cells[3], 0)
    assert rows['otadata'] == LAYOUT['ota_data_initial.bin'] and rows['ota_0'] == LAYOUT['firmware.bin']
    assert rows['nvs'] == NVS[0]


def check_variant(folder, eth, version, language='en'):
    config = (folder / 'config/sdkconfig.h').read_text()
    assert '#define CONFIG_LWIP_MAX_SOCKETS 31' in config
    assert ('#define CONFIG_ETH_SPI_ETHERNET_W5500 1' in config) == eth, 'Variant does not match the build'
    assert f'#define CONFIG_TSR_UI_LANGUAGE "{language}"' in config, 'Web UI language does not match the build'
    image = (folder / 'firmware.bin').read_bytes()
    assert version.encode() in image, 'Version missing from the image'
    asset = b'firmware-eth.bin\0' if eth else b'firmware.bin\0'
    assert asset in image, 'Updater asset name missing from the image'
    if eth:
        assert b'firmware-it.bin' not in image, 'The Ethernet image is English only'
    else:
        assert b'firmware-eth.bin' not in image
        assert all(f'firmware-{code}.bin'.encode() in image for code in LANGUAGES), 'Language assets missing from the updater'
    description = json.loads((folder / 'project_description.json').read_text(encoding='utf-8'))
    validate_build_description(description, ROOT, version)
    return description


def merge(esptool, folder, out):
    subprocess.run([str(esptool), '--chip', 'esp32s3', 'merge-bin', *FLASH_ARGS, '-o', str(out),
                    *[x for name, off in LAYOUT.items() for x in (hex(off), str(folder / name))]], check=True)
    full = out.read_bytes()
    assert full[NVS[0]:NVS[1]] == b'\xff' * (NVS[1] - NVS[0]), 'Factory image must not contain settings'
    app = (folder / 'firmware.bin').read_bytes()
    assert full[LAYOUT['firmware.bin']:LAYOUT['firmware.bin'] + len(app)] == app


def write_sums(folder, names):
    # LF line endings on every platform: sha256sum/shasum reject CRLF lists.
    (folder / 'SHA256SUMS.txt').write_bytes(''.join(f'{sha(folder / n)}  {n}\n' for n in sorted(names)).encode('ascii'))


def zip_dir(src, dest, top):
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(p for p in src.rglob('*') if p.is_file()):
            info = zipfile.ZipInfo(f'{top}/{path.relative_to(src).as_posix()}', date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = (0o755 if path.suffix == '.sh' else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())


def language_variants(wifi_dir, dirs, hashes, version):
    """{code: folder} of tested language images that share the English boot files."""
    folders = dict(item.split('=', 1) for item in dirs)
    tested = dict(item.split('=', 1) for item in hashes)
    assert set(folders) == set(tested), 'Give --lang-dir and --lang-sha256 for the same languages'
    assert set(folders) <= set(LANGUAGES), 'Unknown language variant'
    result = {}
    for code in sorted(folders, key=list(LANGUAGES).index):
        folder = Path(folders[code])
        assert sha(folder / 'firmware.bin') == tested[code].lower(), f'Not the tested {code} image (ADR-026)'
        check_variant(folder, False, version, code)
        for name in LAYOUT:
            if name != 'firmware.bin':
                assert (folder / name).read_bytes() == (wifi_dir / name).read_bytes(), f'{code}: {name} differs from the English build'
        result[code] = folder
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--version', required=True)
    p.add_argument('--prerelease', action='store_true')
    p.add_argument('--wifi-dir', type=Path, required=True)
    p.add_argument('--tested-sha256', required=True)
    p.add_argument('--eth-dir', type=Path)
    p.add_argument('--lang-dir', action='append', default=[], metavar='CODE=DIR',
                   help='WiFi image with English plus one language (it, es, zh)')
    p.add_argument('--lang-sha256', action='append', default=[], metavar='CODE=SHA',
                   help='tested firmware.bin hash of that language image')
    p.add_argument('--esptool', type=Path, required=True)
    p.add_argument('--esptool-license', type=Path, required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--repository', choices=(CURRENT_REPOSITORY, RENAMED_REPOSITORY),
                   default=CURRENT_REPOSITORY, help='Use the current repository until the rename really occurs')
    a = p.parse_args()
    project = re.search(r'set\(PROJECT_VER "([^"]+)"\)', (ROOT / 'CMakeLists.txt').read_text())[1]
    validate_version(a.version, project, a.prerelease)
    check_partitions()
    assert sha(a.wifi_dir / 'firmware.bin') == a.tested_sha256.lower(), 'Not the tested image (ADR-026)'
    description = check_variant(a.wifi_dir, False, a.version)
    if a.eth_dir:
        check_variant(a.eth_dir, True, a.version)
    languages = language_variants(a.wifi_dir, a.lang_dir, a.lang_sha256, a.version)
    v = a.version
    out = (a.out or ROOT / 'build' / f'release-v{v}').resolve()
    out.mkdir(parents=True, exist_ok=False)
    stem = f'ESP32-Tailnet-Gateway-v{v}'
    source_url = repository_url(a.repository)
    notes = f'{source_url}/releases/tag/v{v}'
    channel = ' (release candidate, pre-release)' if a.prerelease else ''

    # Easy Install package: shared boot files, the English image and every
    # language image; the scripts write the chosen one to the app slot.
    pkg = out / 'easy-install'
    (pkg / 'firmware').mkdir(parents=True)
    for name in LAYOUT:
        shutil.copyfile(a.wifi_dir / name, pkg / 'firmware' / name)
    for code, folder in languages.items():
        shutil.copyfile(folder / 'firmware.bin', pkg / 'firmware' / f'firmware-{code}.bin')
    factory = out / f'{stem}-WiFi-factory.bin'
    merge(a.esptool, a.wifi_dir, factory)
    shutil.copytree(TEMPLATES / 'windows', pkg / 'windows')
    shutil.copytree(TEMPLATES / 'macos-linux', pkg / 'macos-linux')
    shutil.copyfile(a.esptool, pkg / 'windows' / 'esptool.exe')
    shutil.copyfile(a.esptool_license, pkg / 'windows' / 'ESPTOOL-LICENSE.txt')
    for bat in (pkg / 'windows').glob('*.bat'):
        bat.write_bytes(bat.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
    sh = pkg / 'macos-linux' / 'install.sh'
    sh.write_bytes(sh.read_bytes().replace(b'\r\n', b'\n'))
    start = (TEMPLATES / 'START-HERE.txt').read_text(encoding='utf-8')
    start = start.replace('{VERSION}', v).replace('{CHANNEL}', channel).replace('{NOTES_URL}', notes)
    (pkg / 'START-HERE.txt').write_bytes(start.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    (pkg / 'FIRMWARE-LICENSES.txt').write_text(collect_release_notices(ROOT, a.wifi_dir), encoding='utf-8')
    files = [f'firmware/{n}' for n in LAYOUT] + [f'firmware/firmware-{code}.bin' for code in languages]
    manifest = {'product': PRODUCT, 'version': v, 'channel': 'pre-release' if a.prerelease else 'stable',
                'variant': 'wifi', 'chip': 'esp32s3', 'board': 'ESP32-S3 N16R8 (16MB flash, 8MB octal PSRAM)',
                'app_identity': description.get('project_name'), 'flash': {k: hex(o) for k, o in LAYOUT.items()},
                'flash_args': FLASH_ARGS, 'tested_image_sha256': a.tested_sha256.lower(), 'source': source_url,
                'web_ui_languages': {'en': 'firmware/firmware.bin',
                                     **{code: f'firmware/firmware-{code}.bin' for code in languages}},
                'files': {f: {'sha256': sha(pkg / f), 'bytes': (pkg / f).stat().st_size} for f in files}}
    (pkg / 'release-manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    write_sums(pkg, files + ['release-manifest.json'])
    for path in pkg.rglob('*'):
        if path.is_file() and path.name != 'esptool.exe':
            assert not credential_findings(path.read_bytes(), True), f'Credential pattern in {path.name}'
    easy_zip = out / f'{stem}-EASY-INSTALL-Windows-macOS-Linux.zip'
    zip_dir(pkg, easy_zip, f'{stem}-EASY-INSTALL')

    # Release assets.
    assets = out / 'assets'
    assets.mkdir()
    shutil.copyfile(a.wifi_dir / 'firmware.bin', assets / 'firmware.bin')
    for code, folder in languages.items():
        shutil.copyfile(folder / 'firmware.bin', assets / f'firmware-{code}.bin')
    shutil.copyfile(factory, assets / factory.name)
    shutil.copyfile(easy_zip, assets / easy_zip.name)
    shutil.copyfile(pkg / 'FIRMWARE-LICENSES.txt', assets / 'FIRMWARE-LICENSES.txt')
    if a.eth_dir:
        shutil.copyfile(a.eth_dir / 'firmware.bin', assets / 'firmware-eth.bin')
        merge(a.esptool, a.eth_dir, assets / f'{stem}-Ethernet-EXPERIMENTAL-factory.bin')
    release = dict(manifest, files={n.name: {'sha256': sha(n), 'bytes': n.stat().st_size}
                                    for n in sorted(assets.iterdir())},
                   ethernet='experimental, not hardware-qualified' if a.eth_dir else 'not included')
    (assets / 'release-manifest.json').write_text(json.dumps(release, indent=1) + '\n', encoding='utf-8')
    write_sums(assets, [n.name for n in assets.iterdir()])

    # Browser installer (website/firmware/<version>/ when the release is final).
    web = out / 'web-installer'
    web.mkdir()
    for name in LAYOUT:
        shutil.copyfile(a.wifi_dir / name, web / name)
    ewt = {'name': 'ESP32 Tailnet Gateway', 'version': v, 'new_install_prompt_erase': True,
           'new_install_improv_wait_time': 0,
           'builds': [{'chipFamily': 'ESP32-S3', 'parts': [{'path': n, 'offset': o} for n, o in LAYOUT.items()]}]}
    (web / 'manifest.json').write_text(json.dumps(ewt, indent=1) + '\n', encoding='utf-8')
    write_sums(web, list(LAYOUT))
    for line in (assets / 'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        print(line)
    print(f'-> {out}')


if __name__ == '__main__':
    main()
