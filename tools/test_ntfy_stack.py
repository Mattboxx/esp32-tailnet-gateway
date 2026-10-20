"""ntfy stack regression guards; optionally inspect the exact Xtensa ELF.

The ELF check detects compiler inlining, not just source-level buffer sizes.
It is not a substitute for HTTPS/info command tests on the actual board.
"""
import argparse
from pathlib import Path
import re
import subprocess
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]


def entry_stack_size(data):
    """Decode Xtensa windowed-ABI ENTRY a1, imm12*8, not arbitrary opcodes."""
    assert len(data) == 3, 'Truncated ENTRY instruction'
    instruction = int.from_bytes(data, 'little')
    assert instruction & 0xfff == 0x136, 'Function does not begin with ENTRY a1'
    return (instruction >> 12) * 8


def elf_entry_frames(elf, names):
    """Read actual ELF32 Xtensa function bytes when objdump lacks a decoder."""
    data = elf.read_bytes()
    assert data[:6] == b'\x7fELF\x01\x01' and struct.unpack_from('<H', data, 18)[0] == 94
    section_offset = struct.unpack_from('<I', data, 32)[0]
    entry_size, count = struct.unpack_from('<HH', data, 46)
    assert entry_size == 40 and 0 < count < 4096 and section_offset + count * 40 <= len(data)
    sections = [struct.unpack_from('<10I', data, section_offset + i*40) for i in range(count)]
    result = {}
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB
            continue
        assert section[9] == 16 and section[6] < count
        strings = sections[section[6]]
        table = data[strings[4]:strings[4]+strings[5]]
        assert section[4] + section[5] <= len(data)
        for offset in range(section[4], section[4]+section[5], 16):
            name_offset, address, size, info, _, index = struct.unpack_from('<IIIBBH', data, offset)
            if info & 15 != 2 or index >= count:  # STT_FUNC
                continue
            assert name_offset < len(table)
            name = table[name_offset:].split(b'\0', 1)[0].decode('ascii')
            if name not in names:
                continue
            assert name not in result and size >= 3, 'Duplicate/truncated heavy function'
            body = sections[index]
            start = body[4] + address - body[3]
            assert body[4] <= start and start+3 <= body[4]+body[5] <= len(data)
            result[name] = entry_stack_size(data[start:start+3])
    assert set(result) == set(names), 'Missing separate ntfy function symbol'
    return result


class NtfyStackTests(unittest.TestCase):
    def test_entry_instruction_decoder(self):
        self.assertEqual(entry_stack_size(bytes.fromhex('36e103')), 496)
        self.assertEqual(entry_stack_size(bytes.fromhex('360104')), 512)
        for data in (b'', b'\x00\x00\x00', bytes.fromhex('36e003')):
            with self.assertRaises(AssertionError):
                entry_stack_size(data)

    def test_heavy_frames_not_inlined(self):
        source = (ROOT / 'main/ntfy_integration.c').read_text()
        for name in ('publish_message', 'send_info', 'handle_command',
                     'poll_commands', 'send_tailscale_alert', 'save_state', 'read_command_batch'):
            self.assertRegex(source, rf'static NTFY_NOINLINE \w+ {name}\(')
        self.assertIn('#define NTFY_TASK_STACK_BYTES 12288', source)
        self.assertIn('!= pdPASS', source)
        alert = source.split('send_tailscale_alert(', 1)[1].split('static void task_main', 1)[0]
        self.assertNotIn('char logs[', alert)
        self.assertNotIn('log_capture_read(', alert)
        self.assertNotIn('malloc(', alert)
        self.assertIn('return err;', alert)

    def test_poll_uses_bounded_nonrecursive_stream(self):
        source = (ROOT / 'main/ntfy_integration.c').read_text()
        self.assertIn('#define NTFY_POLL_BATCH 32', source)
        self.assertIn('ntfy_json_parser_t parser;', source)
        self.assertIn('calloc(1, sizeof *batch)', source)
        self.assertIn('esp_http_client_is_complete_data_received(client)', source)
        self.assertIn('err = send_info(c);', source)
        self.assertIn('uxTaskGetStackHighWaterMark(s_task)', source)


def check_elf(objdump, elf):
    disassembly = subprocess.check_output([objdump, '-d', str(elf)], text=True)
    limits = {'task_main': 768, 'poll_commands': 1280, 'send_info': 2048,
              'send_tailscale_alert': 256, 'handle_command': 512,
              'publish_message': 1024, 'save_state': 768, 'read_command_batch': 256}
    frames = {}
    # Some Windows objdump packages emit undecoded words for Xtensa. Inspect
    # the same function's real entry opcode instead; never skip the budgets.
    if not all(re.search(rf'<{name}>:\s*\n[^\n]*\bentry\s+a1,', disassembly) for name in limits):
        frames = elf_entry_frames(elf, limits)
        for name, limit in limits.items():
            assert frames[name] <= limit, f'{name} stack frame {frames[name]} exceeds {limit}'
        print('PASS: exact ELF ntfy ENTRY budgets (raw instruction decoder):', frames)
        return
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
