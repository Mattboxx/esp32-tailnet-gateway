"""Manual controlled-network probes, NOT an automatic ACL configuration tool.

Run on each real client separately; no credential/policy/firmware mutations.
A timeout alone does not prove denial by Tailscale. Echo servers are test-host
tools, never installed on the ESP. Default bind is loopback, not all interfaces.
"""
import argparse
import concurrent.futures
import json
import secrets
import socket
import time


def probe(host, port, protocol, kind, timeout=3):
    started = time.monotonic()
    nonce = secrets.token_bytes(24)
    payload = nonce
    if kind == 'dns':
        nonce = secrets.token_bytes(2)
        payload = nonce + bytes.fromhex('01000001000000000000') + b'\x0c_authz-check\x07invalid\x00\x00\x01\x00\x01'
    try:
        if protocol == 'tcp':
            with socket.create_connection((host, port), timeout=timeout) as connection:
                if kind == 'connect':
                    return 'reached', time.monotonic() - started
                connection.sendall(payload)
                data = b''
                while len(data) < len(payload):
                    chunk = connection.recv(len(payload)-len(data))
                    if not chunk:
                        break
                    data += chunk
        else:
            family = socket.AF_INET6 if ':' in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_DGRAM) as connection:
                connection.settimeout(timeout)
                connection.connect((host, port))
                connection.send(payload)
                data = connection.recv(1024)
        matched = (len(data) >= 12 and data[:2] == nonce and bool(data[2] & 0x80)) if kind == 'dns' else data == payload
        return ('reached' if matched else 'unexpected_response'), time.monotonic() - started
    except (TimeoutError, socket.timeout):
        return 'no_response', time.monotonic() - started
    except OSError:
        return 'transport_error', time.monotonic() - started


def serve_one(bind, port, protocol):
    family = socket.AF_INET6 if ':' in bind else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM if protocol == 'tcp' else socket.SOCK_DGRAM) as server:
        server.bind((bind, port))
        if protocol == 'tcp':
            server.listen(4)
        print(json.dumps({'fixture': 'ready', 'protocol': protocol, 'bind': bind, 'port': port}), flush=True)
        while True:
            if protocol == 'udp':
                data, source = server.recvfrom(128)
                server.sendto(data, source)
            else:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(2)
                    try:
                        data = b''
                        while len(data) < 24:
                            chunk = connection.recv(24-len(data))
                            if not chunk:
                                break
                            data += chunk
                        if data:
                            connection.sendall(data)
                    except OSError:
                        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    server = commands.add_parser('serve')
    server.add_argument('--bind', default='127.0.0.1')
    server.add_argument('--tcp', type=int, nargs='*', default=[22222, 22223])
    server.add_argument('--udp', type=int, nargs='*', default=[53530, 53531])
    client = commands.add_parser('probe')
    client.add_argument('--host', required=True)
    client.add_argument('--port', type=int, required=True)
    client.add_argument('--protocol', choices=['tcp', 'udp'], required=True)
    client.add_argument('--kind', choices=['echo', 'connect', 'dns'], default='echo')
    client.add_argument('--expected', choices=['allow', 'deny'], required=True)
    client.add_argument('--client', required=True, help='Real client identifier, e.g. A, B or LAN-C')
    client.add_argument('--phase', required=True)
    client.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if args.command == 'serve':
        ports = [('tcp', p) for p in args.tcp] + [('udp', p) for p in args.udp]
        if not ports or len(ports) > 8 or any(not 1 <= p <= 65535 for _, p in ports) or len(set(ports)) != len(ports):
            parser.error('Choose 1..8 distinct protocol/port pairs, ports 1..65535')
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(ports)) as pool:
            futures = [pool.submit(serve_one, args.bind, port, proto) for proto, port in ports]
            for future in concurrent.futures.as_completed(futures):
                future.result()
    else:
        if not 1 <= args.port <= 65535 or (args.kind == 'connect' and args.protocol != 'tcp') or (args.kind == 'dns' and args.protocol != 'udp'):
            parser.error('Use valid ports; connect is TCP-only, dns is UDP-only')
        observed, seconds = probe(args.host, args.port, args.protocol, args.kind)
        verdict = 'pass' if args.expected == 'allow' and observed == 'reached' else 'inconclusive'
        if args.expected == 'deny' and observed == 'reached':
            verdict = 'fail'
        print(json.dumps({'run_id': args.run_id, 'client': args.client, 'phase': args.phase,
                          'protocol': args.protocol, 'kind': args.kind, 'host': args.host,
                          'port': args.port, 'expected': args.expected, 'observed': observed,
                          'verdict': verdict, 'seconds': round(seconds, 3),
                          'denial_requires': 'live positive control, policy evidence and receiving-side observation'}))
        raise SystemExit(0 if verdict == 'pass' else 1 if verdict == 'fail' else 2)


if __name__ == '__main__':
    main()
