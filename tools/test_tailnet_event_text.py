"""Tailnet event texts with their cause (main/history.c) and how notifications
recognise them (main/notify_channels.c), actual code compiled on the host.

Covers:
- a loss with a newly recorded cause;
- a second loss with no new cause (the uplink case);
- no MicroLink diagnostics;
- a reconnect after failed attempts, and a clean reconnect;
- text truncation at the event limit;
- the notification matcher accepting the base text and its detail forms but
  not a different word that starts with the same letters;
- control-plane loss while the last policy is kept and the relay is up
  (keep/bounded mode): an informational event that is not an outage, its
  restore, the later loss when the grace ends, traffic resuming before the
  control plane (no event, outage stays open) and the initial down state.
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
transition = between(hist, 'enum { TAILNET_DOWN = 0', '    *warn = to != TAILNET_UP;\n    return true;\n}\n')
task = between(hist, 'if (state == tailnet_seen && state != tailnet_state) {', 'tailnet_seen = state;')
assert 'microlink_get_diag(ml, &diag) == ESP_OK' in task
assert 'tailnet_transition(tailnet_state, state, have ? &diag : NULL, &seen_losses, text, sizeof text, &warn)' in task
assert 'history_event(HIST_EV_TAILNET, warn ? HIST_WARN : HIST_INFO, text);' in task
assert '} else if (state != TAILNET_STALE) {' in task
assert 'int state = tailnet_link_state(connected, stale, have && diag.derp_connected);' in hist
assert 'stale = policy.control_stale;' in hist
for cause in ('control-plane watchdog (no data)', 'control-plane map stream silent', 'control-plane PING send failed',
              'node key expired, re-registering'):
    assert f'note_ctrl_loss(ml, "{cause}");' in coord, cause
# The long-poll loss carries what ended it, with its code.
for close in ('control server closed the connection', 'control connection error (errno)',
              'control server ended the map session', 'control server sent GOAWAY',
              'control server reset the map stream', 'map stream out of frame', 'map message buffer full'):
    assert f'note_poll_close(ml, "{close}", ' in coord, close
assert 'ml->ctrl_loss_code = ml->ctrl_close_detail ? ml->ctrl_close_code : -1;' in coord
assert coord.count('note_ctrl_retry(ml, "') == 8

PROGRAM = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define HIST_TEXT_MAX 160
typedef struct { char ctrl_loss_reason[48]; int32_t ctrl_loss_code; uint32_t ctrl_loss_count; char ctrl_retry_reason[48]; uint32_t ctrl_retry_failures; } microlink_diag_t;
''' + event_text + transition + matcher + r'''
int main(void) {
    microlink_diag_t d = {0};
    d.ctrl_loss_code = -1;
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
    /* A loss with an HTTP/2 error code or errno shows the code. */
    strcpy(d.ctrl_loss_reason, "control server sent GOAWAY"); d.ctrl_loss_code = 0; d.ctrl_loss_count = 7;
    tailnet_event_text(false, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connection lost: control server sent GOAWAY (code 0)") && seen == 7);
    strcpy(d.ctrl_loss_reason, "control connection error (errno)"); d.ctrl_loss_code = 113; d.ctrl_loss_count = 8;
    tailnet_event_text(false, &d, &seen, t, sizeof t);
    assert(!strcmp(t, "Tailnet connection lost: control connection error (errno) (code 113)"));
    strcpy(d.ctrl_loss_reason, "control-plane map stream silent"); d.ctrl_loss_code = -1;
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
    /* Event state: connected, control loss with policy kept and relay up, down. */
    assert(tailnet_link_state(true, false, false) == TAILNET_UP && tailnet_link_state(true, true, true) == TAILNET_UP);
    assert(tailnet_link_state(false, true, true) == TAILNET_STALE);
    assert(tailnet_link_state(false, true, false) == TAILNET_DOWN && tailnet_link_state(false, false, true) == TAILNET_DOWN);
    bool warn = true;
    /* Control loss with the last policy kept: informational, never the outage text. */
    strcpy(d.ctrl_loss_reason, "control server sent GOAWAY"); d.ctrl_loss_code = 0; d.ctrl_loss_count = 9;
    assert(tailnet_transition(TAILNET_UP, TAILNET_STALE, &d, &seen, t, sizeof t, &warn) && !warn && seen == 9);
    assert(!strcmp(t, "Tailnet control connection lost: control server sent GOAWAY (code 0) (traffic continues with the last policy)"));
    assert(!event_text_is(t, "Tailnet connection lost") && !event_text_is(t, "Tailnet connected"));
    assert(tailnet_transition(TAILNET_STALE, TAILNET_UP, &d, &seen, t, sizeof t, &warn) && !warn);
    assert(!strcmp(t, "Tailnet control connection restored") && !event_text_is(t, "Tailnet connected"));
    /* No new cause recorded: plain stale text. */
    assert(tailnet_transition(TAILNET_UP, TAILNET_STALE, &d, &seen, t, sizeof t, &warn) && !warn);
    assert(!strcmp(t, "Tailnet control connection lost (traffic continues with the last policy)"));
    /* Bounded grace over (or relay lost): now an outage, with the outage text. */
    assert(tailnet_transition(TAILNET_STALE, TAILNET_DOWN, &d, &seen, t, sizeof t, &warn) && warn);
    assert(!strcmp(t, "Tailnet connection lost") && event_text_is(t, "Tailnet connection lost"));
    /* Traffic resumes on the last policy before the control plane: no event;
     * the caller keeps the down state, so the recovery is "Tailnet connected". */
    assert(!tailnet_transition(TAILNET_DOWN, TAILNET_STALE, &d, &seen, t, sizeof t, &warn));
    assert(!tailnet_transition(-1, TAILNET_STALE, &d, &seen, t, sizeof t, &warn));
    d.ctrl_retry_failures = 0;
    assert(tailnet_transition(TAILNET_DOWN, TAILNET_UP, &d, &seen, t, sizeof t, &warn) && !warn && !strcmp(t, "Tailnet connected"));
    /* Initial down state is not recorded; a direct loss keeps its old text. */
    assert(!tailnet_transition(-1, TAILNET_DOWN, &d, &seen, t, sizeof t, &warn));
    d.ctrl_loss_count = 10; strcpy(d.ctrl_loss_reason, "control-plane map stream silent"); d.ctrl_loss_code = -1;
    assert(tailnet_transition(TAILNET_UP, TAILNET_DOWN, &d, &seen, t, sizeof t, &warn) && warn);
    assert(!strcmp(t, "Tailnet connection lost: control-plane map stream silent"));
    /* A long cause still fits as a valid, truncated string. */
    memset(d.ctrl_loss_reason, 'x', 47); d.ctrl_loss_reason[47] = 0; d.ctrl_loss_count = 11; d.ctrl_loss_code = 2147483647;
    /* The longest cause and code fit whole: nothing is cut at the event limit. */
    assert(tailnet_transition(TAILNET_UP, TAILNET_STALE, &d, &seen, t, sizeof t, &warn));
    assert(strlen(t) < sizeof t - 1 && strstr(t, "x (code 2147483647) (traffic continues with the last policy)"));
    d.ctrl_loss_count = 12; d.ctrl_loss_code = 2147483647;
    char mid[100];
    assert(tailnet_transition(TAILNET_UP, TAILNET_STALE, &d, &seen, mid, sizeof mid, &warn));
    assert(strlen(mid) == sizeof mid - 1 && !strncmp(mid, "Tailnet control connection lost: xxx", 36));
    puts("PASS: Tailnet event texts (new cause, repeated loss, no diag, failed attempts, clean reconnect, truncation); "
         "notification matcher accepts base and detail forms only; control loss with the last policy kept is "
         "informational (restore, grace end, resume before control, initial state); history uses microlink_get_diag; MicroLink records "
         "5 loss causes (long-poll with 7 specific close details and codes) and 8 attempt failures");
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
