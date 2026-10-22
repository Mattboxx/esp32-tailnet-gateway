"""PIO pre-build hook for env:esp32-s3-eth only.

Derive sdkconfig.esp32-s3-eth from the shipped sdkconfig.esp32-s3 plus
sdkconfig.eth.defaults, so the Ethernet build differs from the default image
only by the SPI Ethernet driver options. Regenerated whenever either input is
newer. Never touches sdkconfig.esp32-s3.
"""
import os
Import("env")  # type: ignore  # noqa: F821

root = env["PROJECT_DIR"]  # type: ignore  # noqa: F821
base = os.path.join(root, "sdkconfig.esp32-s3")
extra = os.path.join(root, "sdkconfig.eth.defaults")
target = os.path.join(root, "sdkconfig.esp32-s3-eth")


def options(path):
    found = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("CONFIG_") and "=" in line:
                found[line.split("=", 1)[0]] = line
    return found


if not os.path.exists(base):
    raise SystemExit("sdkconfig.esp32-s3 is required to derive the Ethernet configuration")
newest = max(os.path.getmtime(base), os.path.getmtime(extra))
if not os.path.exists(target) or os.path.getmtime(target) < newest:
    wanted = options(extra)
    lines = []
    with open(base, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            for name, value in list(wanted.items()):
                if stripped in (value, f"# {name} is not set") or stripped.startswith(name + "="):
                    line = value + "\n"
                    wanted.pop(name)
                    break
            lines.append(line)
    lines.extend(value + "\n" for value in wanted.values())
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(lines)
    print("eth_sdkconfig: derived sdkconfig.esp32-s3-eth from sdkconfig.esp32-s3")
