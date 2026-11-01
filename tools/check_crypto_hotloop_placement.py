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
        # The WG data path is in IRAM (speed first, 2026-11-01): the ChaCha20
        # and Poly1305 dispatchers plus their Xtensa assembly block functions;
        # both C fallbacks stay in flash.
        found = {name: [] for name in ('chacha20','chacha20_blocks_xtensa','chacha20_c',
                                       'poly1305_blocks','poly1305_blocks_xtensa','poly1305_blocks_c')}
        for symbol in symbols.iter_symbols():
            if symbol.name in found:
                found[symbol.name].append(dict(address=symbol['st_value'], bytes=symbol['st_size'],
                    iram=start <= symbol['st_value'] < end))
        if not any(x['iram'] for x in found['chacha20']):
            raise ValueError('WG ChaCha20 dispatcher not placed in IRAM')
        if not found['chacha20_blocks_xtensa'] or not all(x['iram'] for x in found['chacha20_blocks_xtensa']):
            raise ValueError('ChaCha20 assembly block function not placed in IRAM')
        if any(x['iram'] for x in found['chacha20_c']):
            raise ValueError('ChaCha20 C fallback expected in flash')
        # A separate unrelated crypto implementation can retain a same-named
        # static Poly1305 function in flash. Require the moved WG copy too.
        if not any(x['iram'] for x in found['poly1305_blocks']):
            raise ValueError('WG Poly1305 loop not placed in IRAM')
        if not found['poly1305_blocks_xtensa'] or not all(x['iram'] for x in found['poly1305_blocks_xtensa']):
            raise ValueError('Poly1305 assembly block function not placed in IRAM')
        if any(x['iram'] for x in found['poly1305_blocks_c']):
            raise ValueError('Poly1305 C fallback expected in flash')
        print(json.dumps(dict(placement_pass=True, iram_text_bytes=iram['sh_size'],symbols=found),indent=2))


if __name__ == '__main__': main()
