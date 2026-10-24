"""PIO pre-build hook for the derived firmware variants.

env:esp32-s3-eth      sdkconfig.esp32-s3 + sdkconfig.eth.defaults (W5500 driver)
env:esp32-s3-<lang>   sdkconfig.esp32-s3 + CONFIG_TSR_UI_LANGUAGE="<lang>"
                      (Web UI in English plus that language; it, es, zh)

Each variant differs from the standard English image only by those options.
sdkconfig.<env> is regenerated whenever an input is newer. Never touches
sdkconfig.esp32-s3, which the standard env must have generated first.
"""
import os
Import("env")  # type: ignore  # noqa: F821

root = env["PROJECT_DIR"]  # type: ignore  # noqa: F821
name = env["PIOENV"]  # type: ignore  # noqa: F821
base = os.path.join(root, "sdkconfig.esp32-s3")
target = os.path.join(root, "sdkconfig." + name)
LANGUAGES = ("it", "es", "zh")


def options(path):
    found = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith("CONFIG_") and "=" in line:
                found[line.split("=", 1)[0]] = line
    return found


if name == "esp32-s3-eth":
    inputs = [base, os.path.join(root, "sdkconfig.eth.defaults")]
    wanted = options(inputs[1])
elif name.startswith("esp32-s3-") and name[len("esp32-s3-"):] in LANGUAGES:
    inputs = [base]
    wanted = {"CONFIG_TSR_UI_LANGUAGE": 'CONFIG_TSR_UI_LANGUAGE="%s"' % name[len("esp32-s3-"):]}
else:
    raise SystemExit("variant_sdkconfig: no variant defined for env " + name)

if not os.path.exists(base):
    raise SystemExit("sdkconfig.esp32-s3 is required to derive " + target + ": build env esp32-s3 first")
newest = max(os.path.getmtime(path) for path in inputs + [os.path.join(root, "tools", "variant_sdkconfig.py")])
if not os.path.exists(target) or os.path.getmtime(target) < newest:
    lines = []
    with open(base, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            for option, value in list(wanted.items()):
                if stripped in (value, f"# {option} is not set") or stripped.startswith(option + "="):
                    line = value + "\n"
                    wanted.pop(option)
                    break
            lines.append(line)
    lines.extend(value + "\n" for value in wanted.values())
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(lines)
    print("variant_sdkconfig: derived sdkconfig.%s from sdkconfig.esp32-s3" % name)
