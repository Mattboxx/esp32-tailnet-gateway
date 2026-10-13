"""Compare ESP32-S3 candidate/stable runtime bytes, excluding build metadata.

Uses the pinned SDK's 256-byte esp_app_desc_t layout. Only the version, compile
time/date and ELF digest may differ; all other segment bytes must match.
"""
import argparse
from pathlib import Path
import struct


def segments(path):
    image = path.read_bytes()
    assert len(image) > 288 and image[0] == 0xe9
    count = image[1]
    assert 0 < count <= 16
    result, offset = [], 24
    for _ in range(count):
        address, length = struct.unpack_from('<II', image, offset)
        offset += 8
        assert 0 < length <= 1966080 and offset + length <= len(image)
        result.append((address, image[offset:offset+length]))
        offset += length
    return image[:24], result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate', type=Path)
    p.add_argument('stable', type=Path)
    p.add_argument('--candidate-version', required=True)
    p.add_argument('--stable-version', required=True)
    args = p.parse_args()
    ch, cs = segments(args.candidate)
    sh, ss = segments(args.stable)
    assert ch == sh and len(cs) == len(ss), 'Image header changed'
    for index, ((ca, cd), (sa, sd)) in enumerate(zip(cs, ss)):
        assert ca == sa and len(cd) == len(sd), 'Runtime segment layout changed'
        if index == 0:
            assert cd[:4] == sd[:4] == struct.pack('<I', 0xabcd5432)
            assert cd[16:48].split(b'\0')[0].decode() == args.candidate_version
            assert sd[16:48].split(b'\0')[0].decode() == args.stable_version
            left, right = bytearray(cd), bytearray(sd)
            for start, end in ((16, 48), (80, 112), (144, 176)):
                left[start:end] = right[start:end] = b'\0'*(end-start)
            assert left == right, 'Runtime/immutable descriptor data changed'
        else:
            assert cd == sd, 'Runtime instruction/data bytes changed'
    print(f'PASS: {len(cs)} segments have identical runtime bytes; only version/build metadata differs')


if __name__ == '__main__':
    main()
