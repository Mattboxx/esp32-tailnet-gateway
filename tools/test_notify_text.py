"""Shared notification wording (main/notify_text.c, 3.0.12) on the host.

ntfy, Telegram and email word every event the same way:
- the reset-cause numbers equal the pinned SDK's esp_reset_reason_t, so the
  host-buildable module and the firmware agree;
- boot (power-on with and without the blackout opt-in, restart, brownout,
  unknown cause), Tailscale problem/restored, Wi-Fi problem/restored and
  update available compose to ntfy's title and message; the boot detail line
  keeps the history text; other events keep their text under a title by kind;
- malformed link notes (no number, other suffix) fall back to the raw text;
- MQTT publishes the same reset cause text (reset_cause) besides the code;
- every output is bounded by the caller's capacity (small buffers, long
  texts) and always terminated.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SDK_HDR = Path(os.environ.get('ESP_SYSTEM_H', str(Path.home() / '.platformio/packages/framework-espidf@3.50503.0/components/esp_system/include/esp_system.h')))
SRC = (ROOT / 'main/notify_text.c').read_text(encoding='utf-8')
# MQTT/Home Assistant reports the same readable cause next to the numeric code
MQTT = (ROOT / 'main/mqtt_integration.c').read_text(encoding='utf-8')
assert 'cJSON_AddStringToObject(root, "reset_cause", notify_text_reset_cause((int)esp_reset_reason(), false));' in MQTT
assert '"reset_cause", "Reset cause", s_state_topic' in MQTT and '"reset_reason", "Reset reason code"' in MQTT
mine = re.search(r'enum \{\s*(RST_UNKNOWN[^}]*)\}', SRC).group(1)
mine = [x.strip() for x in mine.replace('\n', ' ').split(',') if x.strip()]
if SDK_HDR.is_file():
    hdr = SDK_HDR.read_text(encoding='utf-8')
    body = re.search(r'typedef enum \{(.*?)\} esp_reset_reason_t;', hdr, re.S).group(1)
    sdk = re.findall(r'\b(ESP_RST_[A-Z_0-9]+)\b', re.sub(r'//[^\n]*|/\*.*?\*/', '', body, flags=re.S))
    assert ['RST_' + s[len('ESP_RST_'):] for s in sdk[:len(mine)]] == mine, (sdk, mine)

PROGRAM = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "notify_text.h"
#include "history.h"
static char t[NOTIFY_TITLE_MAX], m[NOTIFY_MESSAGE_MAX];
static void c(unsigned k, unsigned l, const char *x, int r, bool po) { notify_text_compose(k, l, x, "3.0.12", r, po, t, m, sizeof m); }
int main(void) {
    c(HIST_EV_BOOT, HIST_INFO, "Power-on start 3.0.12 from ota_0, reset POWERON", 1, true);
    assert(!strcmp(t, "ESP32 power-on detected"));
    assert(!strcmp(m, "Gateway powered on: firmware 3.0.12; reset cause: power restored or first power-up (possible blackout).\nDetails: Power-on start 3.0.12 from ota_0, reset POWERON"));
    c(HIST_EV_BOOT, HIST_INFO, "Power-on start 3.0.12 from ota_0, reset POWERON", 1, false);
    assert(strstr(m, "power restored or first power-up.") && !strstr(m, "blackout"));
    c(HIST_EV_BOOT, HIST_ERROR, "Started 3.0.12 from ota_1, reset BROWNOUT", 9, true);
    assert(!strcmp(t, "ESP32 gateway restarted") && strstr(m, "Gateway restarted: firmware 3.0.12; reset cause: supply voltage drop (brownout).") && !strstr(m, "blackout"));
    c(HIST_EV_BOOT, HIST_INFO, "Started 3.0.12 from ota_1, reset SW", 3, false);
    assert(strstr(m, "software-requested restart"));
    c(HIST_EV_BOOT, HIST_INFO, "Started x", 77, false);
    assert(strstr(m, "unknown reset cause"));
    /* the same boot words as ntfy's own builder */
    char nt[NOTIFY_TITLE_MAX], nm[NOTIFY_MESSAGE_MAX];
    notify_text_boot(nt, nm, sizeof nm, "3.0.12", 4, false);
    c(HIST_EV_BOOT, HIST_ERROR, "Started 3.0.12 from ota_1, reset PANIC", 4, false);
    assert(!strcmp(t, nt) && !strncmp(m, nm, strlen(nm)) && m[strlen(nm)] == '\n');
    c(HIST_EV_TAILNET, HIST_WARN, "Tailnet connection unavailable for at least 120 seconds.", 3, false);
    notify_text_tailscale_problem(nt, nm, sizeof nm);
    assert(!strcmp(t, nt) && !strncmp(m, nm, strlen(nm)) && strstr(m, "\nUnavailable for at least 120 s."));
    c(HIST_EV_TAILNET, HIST_WARN, "Tailnet connection recovered after 300 seconds.", 3, false);
    notify_text_tailscale_restored(nt, nm, sizeof nm, 300);
    assert(!strcmp(t, nt) && !strcmp(m, nm));
    c(HIST_EV_UPLINK, HIST_WARN, "Wi-Fi uplink unavailable for at least 60 seconds.", 3, false);
    assert(!strcmp(t, "ESP32 Wi-Fi uplink problem") && !strcmp(m, "The Wi-Fi uplink has been unavailable for at least 60 s."));
    c(HIST_EV_UPLINK, HIST_WARN, "Wi-Fi uplink recovered after 65 seconds.", 3, false);
    assert(!strcmp(t, "ESP32 Wi-Fi uplink restored") && !strcmp(m, "Wi-Fi uplink restored after about 65 s."));
    notify_text_update_available(nt, nm, sizeof nm, "9.9.9");
    c(HIST_EV_UPDATE, HIST_INFO, nm, 3, false);
    assert(!strcmp(t, nt) && !strcmp(m, nm));
    /* malformed link notes and other events keep their text */
    c(HIST_EV_TAILNET, HIST_WARN, "Tailnet connection unavailable for at least many seconds.", 3, false);
    assert(!strcmp(t, "ESP32 gateway warning") && !strcmp(m, "Tailnet connection unavailable for at least many seconds."));
    c(HIST_EV_TAILNET, HIST_WARN, "Tailnet connection recovered after 5 minutes.", 3, false);
    assert(!strcmp(m, "Tailnet connection recovered after 5 minutes."));
    c(HIST_EV_SERVICE, HIST_INFO, "WOL nas: sent", 3, false); assert(!strcmp(t, "ESP32 operational result"));
    c(HIST_EV_CRASH, HIST_ERROR, "Crash: x", 4, false); assert(!strcmp(t, "ESP32 firmware crash"));
    c(HIST_EV_SECURITY, HIST_WARN, "Login refused", 3, false); assert(!strcmp(t, "ESP32 security event"));
    c(HIST_EV_SETTINGS, HIST_INFO, "Saved", 3, false); assert(!strcmp(t, "ESP32 gateway event"));
    c(HIST_EV_STORAGE, HIST_ERROR, "Disk", 3, false); assert(!strcmp(t, "ESP32 gateway error"));
    c(HIST_EV_SETTINGS, HIST_INFO, NULL, 3, false); assert(!strcmp(m, ""));
    /* bounded outputs */
    char big[1000]; memset(big, 'y', sizeof big - 1); big[sizeof big - 1] = 0;
    char small[24];
    notify_text_compose(HIST_EV_BOOT, HIST_INFO, "Started yyyyyyyyyyyyyyyyyyyyyyyyyy", "v", 3, false, t, small, sizeof small);
    assert(strlen(small) == sizeof small - 1);
    notify_text_compose(HIST_EV_SERVICE, HIST_INFO, big, "v", 3, false, t, m, sizeof m);
    assert(strlen(m) == sizeof m - 1);
    notify_text_boot(t, small, sizeof small, NULL, 1, true); assert(strlen(small) < sizeof small);
    char longv[80]; memset(longv, 'v', 79); longv[79] = 0;
    notify_text_boot(t, m, sizeof m, longv, 1, true); assert(!strstr(m, "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv"));
    puts("notify text ok");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='notify-text-') as folder:
    path = Path(folder)
    (path / 'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n', encoding='utf-8')
    (path / 'esp_http_server.h').write_text('#pragma once\ntypedef void *httpd_handle_t;\n', encoding='utf-8')
    (path / 't.c').write_text(PROGRAM, encoding='utf-8')
    exe = path / ('t.exe' if os.name == 'nt' else 't')
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-format-truncation', '-I', str(path), '-I', str(ROOT / 'main')]
    if os.name != 'nt' and os.environ.get('HOTLOOP_SANITIZE') == '1':
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 't.c'), str(ROOT / 'main/notify_text.c'), '-o', str(exe)], check=True)
    out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and 'notify text ok' in out.stdout, (out.returncode, out.stdout, out.stderr)
print('notify text: reset causes equal the SDK enum; boot, Tailscale, Wi-Fi and update events worded as ntfy; '
      'raw fallbacks and titles by kind; bounded outputs')
