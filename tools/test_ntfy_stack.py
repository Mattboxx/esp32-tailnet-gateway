"""ntfy stack regression guards; optionally inspect the exact Xtensa ELF.

The ELF check detects compiler inlining, not just source-level buffer sizes.
It is not a substitute for HTTPS/info command tests on the actual board.
"""
import argparse
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NtfyStackTests(unittest.TestCase):
    def test_heavy_frames_not_inlined(self):
        source = (ROOT / 'main/ntfy_integration.c').read_text()
        for name in ('publish_message', 'send_info', 'handle_command',
                     'poll_commands', 'send_tailscale_alert', 'save_state'):
            self.assertRegex(source, rf'static NTFY_NOINLINE \w+ {name}\(')
        self.assertIn('#define NTFY_TASK_STACK_BYTES 12288', source)
        self.assertIn('!= pdPASS', source)
        alert = source.split('send_tailscale_alert(', 1)[1].split('static void task_main', 1)[0]
        self.assertNotIn('char logs[', alert)
        self.assertIn('free(logs);', alert)
        self.assertIn('return err;', alert)

    def test_poll_rejects_truncated_response(self):
        source = (ROOT / 'main/ntfy_integration.c').read_text()
        self.assertIn('buffer->overflow = true;', source)
        self.assertIn('status != 200 || rb.overflow', source)
        self.assertIn('err = send_info(c);', source)
        self.assertIn('uxTaskGetStackHighWaterMark(s_task)', source)


def check_elf(objdump, elf):
    disassembly = subprocess.check_output([objdump, '-d', str(elf)], text=True)
    limits = {'task_main': 768, 'poll_commands': 1280, 'send_info': 2048,
              'send_tailscale_alert': 256, 'handle_command': 512,
              'publish_message': 1024, 'save_state': 768}
    frames = {}
    for name, limit in limits.items():
        match = re.search(rf'<{name}>:\s*\n[^\n]*\bentry\s+a1,\s*(0x[\da-f]+|\d+)', disassembly)
        assert match, f'Missing separate frame: {name}'
        size = int(match[1], 0)
        assert size <= limit, f'{name} stack frame {size} exceeds {limit}'
        frames[name] = size
    print('PASS: exact ELF ntfy frame budgets:', frames)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--objdump')
    parser.add_argument('--elf', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(NtfyStackTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.elf:
        assert args.objdump, '--objdump is required for --elf'
        check_elf(args.objdump, args.elf)
