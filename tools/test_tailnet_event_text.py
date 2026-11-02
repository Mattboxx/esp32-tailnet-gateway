"""Tailnet event texts with their cause (main/history.c) and how notifications
recognise them (main/notify_channels.c), actual code compiled on the host.

Covers:
- a loss with a newly recorded cause;
- a second loss with no new cause (the uplink case);
- no MicroLink diagnostics;
- a reconnect after failed attempts, and a clean reconnect;
- text truncation at the event limit;
- the notification matcher accepting the base text and its detail forms but
  not a different word that starts with the same letters.
Also checks structurally that the history task builds the text from
microlink_get_diag() and that MicroLink records each cause.
"""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
hist = (ROOT / 'main/history.c').read_text(encoding='utf-8').replace('\r\n', '\n')
notify = (ROOT / 'main/notify_channels.c').read_text(encoding='utf-8').replace('\r\n', '\n')
coord = (ROOT / 'external/microlink/components/microlink/src/ml_coord.c').read_text(encoding='utf-8').replace('\r\n', '\n')


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i) + len(end)]


event_text = between(hist, 'static void tailnet_event_text(', '        snprintf(out, n, "Tailnet connected");\n    }\n}\n')
matcher = between(notify, 'static bool event_text_is(', "text[n] == ' ');\n}\n")
task = between(hist, 'if (state == tailnet_seen && state != tailnet_state) {', 'tailnet_state = state;')
assert 'microlink_get_diag(ml, &diag) == ESP_OK' in task and 'tailnet_event_text(state, have ? &diag : NULL' in task
for cause in ('control-plane watchdog (no data)', 'control-plane map stream silent', 'control-plane PING send failed',
              'control-plane connection closed or failed', 'node key expired, re-registering'):
    assert f'note_ctrl_loss(ml, "{cause}");' in coord, cause
assert coord.count('note_ctrl_retry(ml, "') == 8

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct { char ctrl_loss_reason[48]; uint32_t ctrl_loss_count; char ctrl_retry_reason[48]; uint32_t ctrl_retry_failures; } microlink_diag_t;
''' + event_text + matcher + r'''
int main(void) {
    microlink_diag_t d = {0};
    uint32_t seen = 0;
    char t[161];
    /* A new loss with its cause. */
    strcpy(d.ctrl_loss_reason, "control-plane map stream silent"); d.ctrl_loss_count = 1;
    tailnet_event_text(false, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connection lost: control-plane map stream silent") && seen == 1);
    /* Second loss without a new cause (the uplink went first): plain text. */
    tailnet_event_text(false, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connection lost"));
    tailnet_event_text(false, NULL, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connection lost"));
    /* Reconnect after failed attempts, then a clean one. */
    strcpy(d.ctrl_retry_reason, "registration failed"); d.ctrl_retry_failures = 3;
    tailnet_event_text(true, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connected after 3 failed attempts (last: registration failed)"));
    d.ctrl_retry_failures = 0;
    tailnet_event_text(true, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connected"));
    tailnet_event_text(true, NULL, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connected"));
    /* Truncation stays a valid string. */
    char small[24];
    d.ctrl_loss_count = 2;
    tailnet_event_text(false, &d, &seen, small, sizeof small);
    assert(strlen(small) == sizeof small - 1 && !strncmp(small, "Tailnet connection lost", 23));
    /* The notification matcher recognises base and detailed forms only. */
    assert(event_text_is("Tailnet connection lost", "Tailnet connection lost"));
    assert(event_text_is("Tailnet connection lost: control-plane map stream silent", "Tailnet connection lost"));
    assert(event_text_is("Tailnet connected", "Tailnet connected"));
    assert(event_text_is("Tailnet connected after 3 failed attempts (last: registration failed)", "Tailnet connected"));
    assert(!event_text_is("Tailnet connectedness", "Tailnet connected"));
    assert(!event_text_is("Tailnet connection lostX", "Tailnet connection lost"));
    assert(!event_text_is("Tailnet", "Tailnet connected"));
    puts("PASS: Tailnet event texts (new cause, repeated loss, no diag, failed attempts, clean reconnect, truncation); "
         "notification matcher accepts base and detail forms only; history uses microlink_get_diag; MicroLink records "
         "5 loss causes and 8 attempt failures");
    return 0;
}
'''


def main():
    with tempfile.TemporaryDirectory(prefix='tailnet-events-') as folder:
        path = Path(folder)
        (path / 'test.c').write_text(PROGRAM, encoding='utf-8')
        exe = path / ('test.exe' if os.name == 'nt' else 'test')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-format-truncation']
        if os.environ.get('HOTLOOP_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run([os.environ.get('CC', 'gcc'), *flags, str(path / 'test.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    main()
