"""Read-only ESP32-S3 ELF gate for the experimental selective-IRAM build."""
import argparse
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    with args.elf.open('rb') as stream:
        elf = ELFFile(stream)
        iram = elf.get_section_by_name('.iram0.text')
        if iram is None:
            raise ValueError('Expected ESP32-S3 IRAM section not found')
        start, end = iram['sh_addr'], iram['sh_addr']+iram['sh_size']
        symbols = elf.get_section_by_name('.symtab')
        # The WG poly1305_blocks is in IRAM; chacha20 deliberately stays in flash
        # since 2026-10-31 (measured trade-off, see the performance roadmap).
        found = {name: [] for name in ('chacha20','poly1305_blocks')}
        for symbol in symbols.iter_symbols():
            if symbol.name in found:
                found[symbol.name].append(dict(address=symbol['st_value'], bytes=symbol['st_size'],
                    iram=start <= symbol['st_value'] < end))
        if not found['chacha20'] or any(x['iram'] for x in found['chacha20']):
            raise ValueError('ChaCha20 data path expected in flash')
        # A separate unrelated crypto implementation can retain a same-named
        # static Poly1305 function in flash. Require the moved WG copy too.
        if not any(x['iram'] for x in found['poly1305_blocks']):
            raise ValueError('WG Poly1305 loop not placed in IRAM')
        print(json.dumps(dict(placement_pass=True, iram_text_bytes=iram['sh_size'],symbols=found),indent=2))


if __name__ == '__main__': main()
