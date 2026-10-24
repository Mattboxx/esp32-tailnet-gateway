"""Package the exact, tested 2.1 migration bridge for release (local only).

The bridge (env esp32-s3-bridge) is what 2.x gateways install through their
GitHub updater; it then moves them to the 3.x flash layout. Output
build/release-v<version>/assets/: firmware.bin (the name 2.x updaters look
for), FIRMWARE-LICENSES.txt, release-manifest.json, SHA256SUMS.txt.

Never rebuilds: the image must match --tested-sha256 (ADR-026). Refuses a
bench build (CONFIG_TSR_MIGRATION_SOURCE_URL set), a non-bridge build, a
non-2.x layout and an image larger than a 2.x slot.

    python tools/package_bridge.py --version 2.1.0 \\
        --bridge-dir build/development-2.1.0/target/esp32-s3-bridge --tested-sha256 <sha>
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil

from package_release import collect_release_notices, validate_build_description
from package_v2 import CURRENT_REPOSITORY, RENAMED_REPOSITORY, PRODUCT, repository_url, sha, write_sums

ROOT = Path(__file__).resolve().parents[1]
SLOT_2X = 1920 * 1024
# ota_1 entry of the 2.x table: magic, app, ota_1, offset 0x200000, size 0x1E0000.
OTA1_2X = bytes.fromhex('aa50001100002000') + (0x1E0000).to_bytes(4, 'little')


def bridge_version():
    return re.search(r'set\(TSR_BRIDGE_VER "([^"]+)"\)', (ROOT / 'CMakeLists.txt').read_text(encoding='utf-8'))[1]


def check_bridge(folder, version):
    config = (folder / 'config/sdkconfig.h').read_text()
    assert '#define CONFIG_TSR_MIGRATION_BRIDGE 1' in config, 'Not a migration bridge build'
    assert '#define CONFIG_TSR_MIGRATION_SOURCE_URL ""' in config, 'Bench build (test source set): never publish it'
    assert '#define CONFIG_ESPTOOLPY_FLASHSIZE "4MB"' in config, 'The bridge keeps the 2.x 4 MB header'
    assert 'CONFIG_ETH_SPI_ETHERNET_W5500 1' not in config and 'CONFIG_LWIP_PPP_SUPPORT 1' not in config
    image = (folder / 'firmware.bin').read_bytes()
    assert len(image) <= SLOT_2X, 'Bridge larger than a 2.x slot'
    assert version.encode() in image, 'Version missing from the image'
    table = (folder / 'partitions.bin').read_bytes()
    assert table[4 * 32:4 * 32 + 12] == OTA1_2X, 'Bridge not built for the 2.x layout'
    description = json.loads((folder / 'project_description.json').read_text(encoding='utf-8'))
    validate_build_description(description, ROOT, version)
    return description


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--version', required=True)
    p.add_argument('--bridge-dir', type=Path, required=True)
    p.add_argument('--tested-sha256', required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--repository', choices=(CURRENT_REPOSITORY, RENAMED_REPOSITORY), default=RENAMED_REPOSITORY)
    a = p.parse_args()
    assert a.version == bridge_version(), 'Version differs from CMakeLists TSR_BRIDGE_VER'
    assert re.fullmatch(r'2\.\d+\.\d+', a.version), 'The bridge is a stable 2.x release'
    assert sha(a.bridge_dir / 'firmware.bin') == a.tested_sha256.lower(), 'Not the tested image (ADR-026)'
    description = check_bridge(a.bridge_dir, a.version)
    out = (a.out or ROOT / 'build' / f'release-v{a.version}').resolve()
    assets = out / 'assets'
    assets.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(a.bridge_dir / 'firmware.bin', assets / 'firmware.bin')
    (assets / 'FIRMWARE-LICENSES.txt').write_text(collect_release_notices(ROOT, a.bridge_dir), encoding='utf-8')
    manifest = {'product': PRODUCT, 'version': a.version, 'channel': 'stable', 'variant': 'migration bridge (2.x layout)',
                'chip': 'esp32s3', 'board': 'ESP32-S3 N8R8 or N16R8 on the 2.x 4 MB layout',
                'app_identity': description.get('project_name'), 'tested_image_sha256': a.tested_sha256.lower(),
                'source': repository_url(a.repository),
                'files': {n.name: {'sha256': sha(n), 'bytes': n.stat().st_size} for n in sorted(assets.iterdir())}}
    (assets / 'release-manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', encoding='utf-8')
    write_sums(assets, [n.name for n in assets.iterdir()])
    print((assets / 'SHA256SUMS.txt').read_text(encoding='ascii'), f'-> {out}', sep='')


if __name__ == '__main__':
    main()
