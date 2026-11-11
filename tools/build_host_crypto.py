"""Build the pinned SDK's software crypto for offline protocol tests.

This host build enables only the algorithms used by the setup/password tests.
It does not qualify the ESP hardware crypto drivers, radio or memory budget.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

CONFIG = """#ifndef TSR_HOST_PSA_CONFIG_H
#define TSR_HOST_PSA_CONFIG_H
#define PSA_WANT_ALG_GCM 1
#define PSA_WANT_ALG_SHA_256 1
#define PSA_WANT_ALG_HMAC 1
#define PSA_WANT_KEY_TYPE_HMAC 1
#define PSA_WANT_KEY_TYPE_AES 1
#define PSA_WANT_KEY_TYPE_RAW_DATA 1
#define MBEDTLS_MD_C
#define MBEDTLS_PLATFORM_C
#define MBEDTLS_PSA_CRYPTO_C
#define MBEDTLS_CTR_DRBG_C
#define MBEDTLS_PSA_BUILTIN_GET_ENTROPY
#endif
"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mbedtls-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("build/host-crypto"))
    parser.add_argument("--sanitizers", action="store_true")
    args = parser.parse_args()
    source = args.mbedtls_dir.resolve() / "tf-psa-crypto"
    if not (source / "CMakeLists.txt").is_file():
        parser.error("Provide the ESP-IDF 6.1 Mbed TLS tree")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = output / "crypto-config.h"
    config.write_text(CONFIG, encoding="utf-8")
    configure = ["cmake", "-S", str(source), "-B", str(output), "-G", "Ninja",
                    "-DENABLE_PROGRAMS=OFF", "-DENABLE_TESTING=OFF", "-DGEN_FILES=OFF",
                                     "-DTF_PSA_CRYPTO_CONFIG_FILE=" + str(config)]
    if args.sanitizers:
        configure += ["-DCMAKE_C_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer"]
    subprocess.run(configure, check=True)
    subprocess.run(["cmake", "--build", str(output), "--parallel", "8"], check=True)
    assert (output / "core/libtfpsacrypto.a").is_file()
    (output / "host-crypto-manifest.json").write_text(json.dumps({
        "source": str(source), "config": str(config),
        "cflags": os.environ.get("CFLAGS", ""),
        "ldflags": os.environ.get("LDFLAGS", ""),
        "sanitizers": args.sanitizers,
        "hardware_drivers_tested": False,
    }, indent=2) + "\n", encoding="utf-8")
    print("PASS: SDK TF-PSA-Crypto software host build")

if __name__ == "__main__":
    main()
