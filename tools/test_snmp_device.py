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

    def send(path, payload=None, *, raw=False, timeout=12):
        if raw:
            assert isinstance(payload, bytes), 'Raw API bodies must be bytes'
        body = payload if raw else (None if payload is None else json.dumps(payload).encode())
        req = urllib.request.Request(base + path, body,
            headers={'Content-Type': 'application/octet-stream' if raw else 'application/json'} if body is not None else {})
        with client.open(req, timeout=timeout) as response:
            return json.load(response)

    def authenticate():
        challenge = send('/api/auth/challenge')
        assert challenge['supported']
        key = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(challenge['salt']),
                                 challenge['iterations'], 32)
        proof = hmac.new(key, challenge['context'].encode() + bytes.fromhex(challenge['nonce']),
                         hashlib.sha256).hexdigest()
        assert send('/api/auth/login', {'nonce': challenge['nonce'], 'proof': proof})['ok']

    def api(path, payload=None, *, raw=False, timeout=12):
        try:
            return send(path, payload, raw=raw, timeout=timeout)
        except urllib.error.HTTPError as error:
            # An explicit 401 means require_auth rejected the request before
            # mutation. Renew once; never retry ambiguous network/write errors.
            # Callers retain their uptime/reset checks across reauthentication.
            if error.code != 401 or path.startswith('/api/auth/'):
                raise
            authenticate()
            return send(path, payload, raw=raw, timeout=timeout)

    authenticate()
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--allow-temporary-enable', action='store_true', required=True)
    parser.add_argument('--expected-version', default='0.1.29-Mattboxx-1.7')
    parser.add_argument('--expected-sockets', type=int, default=31)
    parser.add_argument('--expected-active-tcp', type=int, default=24)
    parser.add_argument('--soak-seconds', type=int, default=0,
                        help='Keep SNMP enabled through multiple telemetry/forwarding refreshes')
    parser.add_argument('--tailnet-host', help='Also query the same agent over its reachable Tailnet IP')
    args = parser.parse_args()
    api = login(args.host)
    limits = api('/api/system/diag')['network_limits']
    assert limits['sockets'] == args.expected_sockets and limits['active_tcp'] == args.expected_active_tcp
    print(f'PASS: authenticated diagnostics report {args.expected_sockets} sockets and {args.expected_active_tcp} active TCP slots')
    original = api('/api/snmp')
    assert not original['enabled'], 'Agent already enabled; refusing to change its live state'
    config = {key: original[key] for key in ('enabled', 'community', 'sys_name', 'sys_contact', 'sys_location')}
    assert config['community']
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(1)
    lan_retries = 0

    def exchange(packet, expect=True):
        nonlocal lan_retries
        # UDP delivery is not guaranteed, especially during concurrent TLS.
        # Retry only valid read-only requests, at most three transmissions.
        for attempt in range(3 if expect else 1):
            udp.sendto(packet, (args.host, 161))
            try:
                reply, sender = udp.recvfrom(4096)
                assert sender[0] == socket.gethostbyname(args.host)
            except socket.timeout:
                if not expect:
                    return None
                if attempt == 2:
                    raise AssertionError('SNMP response timed out after three transmissions')
                lan_retries += 1
                continue
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
            assert args.expected_version.encode() in result[2]
        print('PASS: SNMPv1 and v2c sysDescr identify the installed release')
        if args.tailnet_host:
            tailnet = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tailnet.settimeout(5)
            try:
                import time
                # Span several independent 3-second forwarding / 5-second SNMP ticks.
                for sample in range(12):
                    for attempt in range(3):
                        tailnet.sendto(request(comm, system_oid, sample % 2), (args.tailnet_host, 161))
                        try:
                            reply, sender = tailnet.recvfrom(4096)
                            break
                        except socket.timeout:
                            if attempt == 2:
                                raise
                            print('Retrying a lost Tailnet UDP query (bounded)', flush=True)
                    assert sender[0] == socket.gethostbyname(args.tailnet_host)
                    result = decode_reply(reply)
                    assert result[0] == system_oid and args.expected_version.encode() in result[2]
                    time.sleep(2)
                print('PASS: 12 actual Tailnet SNMP v1/v2c replies across repeated installer ticks', flush=True)
            finally:
                tailnet.close()
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
        if args.soak_seconds:
            import time
            assert 30 <= args.soak_seconds <= 3600, 'Soak must be 30..3600 seconds'
            previous = api('/api/status')['uptime_s']
            start = time.monotonic()
            samples = 0
            while time.monotonic() - start < args.soak_seconds:
                time.sleep(5)
                state = api('/api/status')
                assert state['uptime_s'] > previous, 'Unexpected restart/frozen uptime'
                previous = state['uptime_s']
                assert state['sta']['connected'] and state['tailscale']['connected']
                assert api('/api/snmp')['running']
                exchange(valid)
                samples += 1
            print(f'PASS: SNMP enabled for {time.monotonic()-start:.0f}s across '
                  f'{samples} live queries; WiFi/Tailscale connected, no observed restart', flush=True)
    finally:
        udp.close()
        assert api('/api/snmp', config)['ok']
        wait_running(False)
        restored = api('/api/snmp')
        assert all(restored[key] == value for key, value in config.items())
        print('PASS: SNMP restored OFF with community/name/contact/location unchanged')
        print(f'LAN UDP retransmissions during checks: {lan_retries}', flush=True)


if __name__ == '__main__':
    main()
