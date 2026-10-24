"""PIO pre-build hook for env:esp32-s3-bridge (the 2.1 migration bridge).

Derives sdkconfig.esp32-s3-bridge from sdkconfig.esp32-s3: the 2.x 4 MB flash
layout (partitions-2x.csv), English-only page, no Ethernet or PPP driver (to
fit a 1920 KiB 2.x slot), writes to the bootloader and partition table
allowed (the migration rewrites them) and CONFIG_TSR_MIGRATION_BRIDGE.
Optional: TSR_MIGRATION_SOURCE_URL in the environment selects a plain-HTTP
bench source; release builds must not set it.
"""
import os
Import("env")  # type: ignore  # noqa: F821

root = env["PROJECT_DIR"]  # type: ignore  # noqa: F821
name = env["PIOENV"]  # type: ignore  # noqa: F821
base = os.path.join(root, "sdkconfig.esp32-s3")
target = os.path.join(root, "sdkconfig." + name)
source_url = os.environ.get("TSR_MIGRATION_SOURCE_URL", "")
if '"' in source_url or "\\" in source_url:
    raise SystemExit("bridge_sdkconfig: invalid TSR_MIGRATION_SOURCE_URL")

SET = {
    "CONFIG_ESPTOOLPY_FLASHSIZE_4MB": "CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y",
    "CONFIG_ESPTOOLPY_FLASHSIZE_8MB": "# CONFIG_ESPTOOLPY_FLASHSIZE_8MB is not set",
    "CONFIG_ESPTOOLPY_FLASHSIZE": 'CONFIG_ESPTOOLPY_FLASHSIZE="4MB"',
    "CONFIG_PARTITION_TABLE_CUSTOM_FILENAME": 'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-2x.csv"',
    "CONFIG_PARTITION_TABLE_FILENAME": 'CONFIG_PARTITION_TABLE_FILENAME="partitions-2x.csv"',
    "CONFIG_ETH_SPI_ETHERNET_W5500": "# CONFIG_ETH_SPI_ETHERNET_W5500 is not set",
    "CONFIG_LWIP_PPP_SUPPORT": "# CONFIG_LWIP_PPP_SUPPORT is not set",
    "CONFIG_SPI_FLASH_DANGEROUS_WRITE_ABORTS": "# CONFIG_SPI_FLASH_DANGEROUS_WRITE_ABORTS is not set",
    "CONFIG_SPI_FLASH_DANGEROUS_WRITE_ALLOWED": "CONFIG_SPI_FLASH_DANGEROUS_WRITE_ALLOWED=y",
    "CONFIG_TSR_MIGRATION_BRIDGE": "CONFIG_TSR_MIGRATION_BRIDGE=y",
    "CONFIG_TSR_MIGRATION_SOURCE_URL": 'CONFIG_TSR_MIGRATION_SOURCE_URL="%s"' % source_url,
}


def option_name(line):
    line = line.strip()
    if line.startswith("# CONFIG_") and line.endswith(" is not set"):
        return line[2:-len(" is not set")]
    if line.startswith("CONFIG_") and "=" in line:
        return line.split("=", 1)[0]
    return None


if not os.path.exists(base):
    raise SystemExit("sdkconfig.esp32-s3 is required to derive the bridge: build env esp32-s3 first")
script = os.path.join(root, "tools", "bridge_sdkconfig.py")
newest = max(os.path.getmtime(base), os.path.getmtime(script))
current = ""
if os.path.exists(target):
    with open(target, encoding="utf-8") as handle:
        current = handle.read()
stale = not current or os.path.getmtime(target) < newest or SET["CONFIG_TSR_MIGRATION_SOURCE_URL"] not in current
if stale:
    wanted = dict(SET)
    lines = []
    with open(base, encoding="utf-8") as handle:
        for line in handle:
            name_ = option_name(line)
            if name_ in wanted:
                line = wanted.pop(name_) + "\n"
            elif name_ and name_.startswith("CONFIG_LWIP_PPP_"):
                continue  # PPP sub-options vanish with PPP support
            lines.append(line)
    lines.extend(value + "\n" for value in wanted.values())
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(lines)
    print("bridge_sdkconfig: derived sdkconfig.%s from sdkconfig.esp32-s3" % name)
