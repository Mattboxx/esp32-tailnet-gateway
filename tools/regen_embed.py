"""PIO pre-build hook: regenerate main/index_html_data*.c when index.html
or a translation changed.

The CMakeLists.txt does `file(READ HEX) ...` at configure time and emits
`index_html_data.c`. CMake's CMAKE_CONFIGURE_DEPENDS is supposed to
re-run configure when listed files change, but PIO's SCons wrapper
caches the configure step and the trigger doesn't fire on plain HTML
edits — so the device ends up serving a stale SPA blob.

This pre-build script compares mtimes: if index.html is newer than the
generated .c, delete the .c and touch CMakeLists.txt so CMake
reconfigures cleanly on the next build.

SPDX-License-Identifier: MIT
"""
import glob
import os
Import("env")  # type: ignore  # noqa: F821

PROJECT_DIR = env.subst("$PROJECT_DIR")  # noqa: F821
MAIN        = os.path.join(PROJECT_DIR, "main")
HTML        = os.path.join(MAIN, "index.html")
CMAKELISTS  = os.path.join(MAIN, "CMakeLists.txt")

# One generated page per Web UI variant (index_html_data_<lang>.c); the
# translations in main/i18n/ are inputs as well.
sources = [HTML] + glob.glob(os.path.join(MAIN, "i18n", "*.json"))
generated = glob.glob(os.path.join(MAIN, "index_html_data*.c"))
newest = max((os.path.getmtime(s) for s in sources if os.path.exists(s)), default=0)
stale = [g for g in generated if os.path.getmtime(g) < newest]
if stale:
    print("regen_embed: index.html or translations changed — regenerating the embedded page.")
    for path in stale:
        try:
            os.remove(path)
        except OSError:
            pass
    # Touch CMakeLists.txt so CMake notices and reconfigures.
    os.utime(CMAKELISTS, None)
