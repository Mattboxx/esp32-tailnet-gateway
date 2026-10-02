"""Opt-in SNMP hardware regression. Temporarily enables the agent, restores OFF.

Use only on your own device. TEST_DEVICE_PASSWORD stays in memory, and neither
HTTP cookies, community nor returned MIB values are printed or written to disk.
"""
import argparse
import hashlib
import hmac
import http.cookiejar
import json
import os
import random
import socket
import urllib.error
import urllib.request


def tlv(tag, data):
    size = len(data)
    length = bytes([size]) if size < 128 else bytes([0x82, size >> 8, size & 255])
    return bytes([tag]) + length + data


def oid_encode(arcs):
    result = bytes([arcs[0] * 40 + arcs[1]])
    for value in arcs[2:]:
        groups = [value & 127]
        value >>= 7
        while value:
            groups.insert(0, (value & 127) | 128)
            value >>= 7
        result += bytes(groups)
    return tlv(6, result)


def request(community, oid, version=1, tag=0xa0):
    vb = tlv(0x30, oid_encode(oid) + tlv(5, b''))
    pdu = tlv(tag, tlv(2, b'\x01') + tlv(2, b'\x00') * 2 + tlv(0x30, vb))
    return tlv(0x30, tlv(2, bytes([version])) + tlv(4, community.encode()) + pdu)


def children(data):
    result = []
    while data:
        tag, size = data[0], data[1]
        pos = 2
        if size & 128:
            count = size & 127
            size = int.from_bytes(data[pos:pos + count], 'big')
            pos += count
        if len(data) < pos + size:
            raise AssertionError('Truncated SNMP reply')
        result.append((tag, data[pos:pos + size]))
        data = data[pos + size:]
    return result


def decode_reply(data):
    message = children(children(data)[0][1])
    assert message[2][0] == 0xa2
    pdu = children(message[2][1])
    assert int.from_bytes(pdu[1][1], 'big') == 0
    vb = children(children(pdu[3][1])[0][1])
    raw = vb[0][1]
    arcs = [raw[0] // 40, raw[0] % 40]
    value = 0
    for octet in raw[1:]:
        value = (value << 7) | (octet & 127)
        if not octet & 128:
            arcs.append(value)
            value = 0
    return arcs, vb[1][0], vb[1][1]


def login(host):
    password = os.environ['TEST_DEVICE_PASSWORD']
    base = 'http://' + host
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def api(path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base + path, body,
            headers={'Content-Type': 'application/json'} if body is not None else {})
        with client.open(req, timeout=12) as response:
            return json.load(response)

    challenge = api('/api/auth/challenge')
    assert challenge['supported']
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(challenge['salt']),
                             challenge['iterations'], 32)
    proof = hmac.new(key, challenge['context'].encode() + bytes.fromhex(challenge['nonce']),
                     hashlib.sha256).hexdigest()
    assert api('/api/auth/login', {'nonce': challenge['nonce'], 'proof': proof})['ok']
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--allow-temporary-enable', action='store_true', required=True)
    args = parser.parse_args()
    api = login(args.host)
    limits = api('/api/system/diag')['network_limits']
    assert limits['sockets'] == 26 and limits['active_tcp'] == 24
    print('PASS: authenticated diagnostics report 26 sockets and 24 active TCP slots')
    original = api('/api/snmp')
    assert not original['enabled'], 'Agent already enabled; refusing to change its live state'
    config = {key: original[key] for key in ('enabled', 'community', 'sys_name', 'sys_contact', 'sys_location')}
    assert config['community']
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(1)

    def exchange(packet, expect=True):
        udp.sendto(packet, (args.host, 161))
        try:
            reply, sender = udp.recvfrom(4096)
            assert sender[0] == socket.gethostbyname(args.host)
        except socket.timeout:
            assert not expect, 'SNMP response timed out'
            return None
        assert expect, 'A rejected SNMP request received a reply'
        return decode_reply(reply)

    def wait_running(expected):
        import time
        for attempt in range(20):
            if api('/api/snmp')['running'] == expected:
                return
            time.sleep(0.2)
        raise AssertionError('SNMP did not reach the expected running state')

    try:
        assert api('/api/snmp', dict(config, enabled=True))['ok']
        wait_running(True)
        comm = config['community']
        system_oid = [1, 3, 6, 1, 2, 1, 1, 1, 0]
        for version in (0, 1):
            result = exchange(request(comm, system_oid, version))
            assert result[0] == system_oid and result[1] == 4
            assert b'0.1.28-Mattboxx-1.6' in result[2]
        print('PASS: SNMPv1 and v2c sysDescr identify the installed release')
        for version in (0, 1):
            oid, count = [1, 3, 6, 1, 2, 1], 0
            while count < 100:
                result = exchange(request(comm, oid, version, 0xa1))
                if result[1] in (0x82, 5):
                    break
                assert result[0] > oid, 'Non-advancing GETNEXT walk'
                oid = result[0]
                count += 1
            assert count == 82, f'Expected 82 objects, walked {count}'
        print('PASS: complete 82-object v1/v2c walks terminate correctly')
        for invalid in ('', comm + '-wrong'):
            exchange(request(invalid, system_oid), False)
        exchange(request(comm, system_oid, 3), False)
        exchange(request(comm, system_oid, 1, 0xa3), False)
        print('PASS: empty/wrong communities, unsupported version and SET ignored')
        rng = random.Random(123456)
        valid = request(comm, system_oid)
        for length in (0, 1, 2, 8, 100, 2048, 4096):
            udp.sendto(bytes(rng.randrange(256) for _ in range(length)), (args.host, 161))
        for cut in range(0, len(valid), max(1, len(valid) // 5)):
            udp.sendto(valid[:cut], (args.host, 161))
        exchange(valid)
        print('PASS: listener survives malformed, truncated and oversized datagrams')
        # Every operation retains the existing community and descriptive strings.
        for cycle in range(3):
            assert api('/api/snmp', dict(config, enabled=False))['ok']
            wait_running(False)
            exchange(valid, False)
            assert api('/api/snmp', dict(config, enabled=True))['ok']
            wait_running(True)
            exchange(valid)
        print('PASS: three live disable/enable cycles, no response while disabled')
    finally:
        udp.close()
        assert api('/api/snmp', config)['ok']
        wait_running(False)
        restored = api('/api/snmp')
        assert all(restored[key] == value for key, value in config.items())
        print('PASS: SNMP restored OFF with community/name/contact/location unchanged')


if __name__ == '__main__':
    main()
