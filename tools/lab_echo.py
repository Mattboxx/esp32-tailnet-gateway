"""Lab-only TCP and UDP echo service for Service Gateway end-to-end tests.

Run it on a machine that is a tailnet peer (for example the bench PC) and
bind it to that machine's tailnet address only, so nothing is exposed on the
LAN or the Internet:

    python tools/lab_echo.py --bind <tailnet-ip> --port 47001 --seconds 900

Then create a Service Gateway rule on the board
(`<listen port> -> <tailnet-ip>:47001`, source = the LAN client's /32) and run
`python tools/lab_echo.py --probe <board-lan-ip>:<listen port>` from the LAN
client. The probe sends a random token and requires the identical bytes back,
so a reply proves the payload travelled LAN client -> board -> WireGuard ->
echo service -> back. Counts are printed; payloads are random, not logged.
"""
import argparse
import os
import socket
import threading
import time


def tcp_server(bind, port, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind, port))
    srv.listen(8)
    srv.settimeout(0.5)
    served = 0
    while not stop.is_set():
        try:
            conn, peer = srv.accept()
        except socket.timeout:
            continue
        with conn:
            conn.settimeout(5)
            try:
                data = conn.recv(4096)
                conn.sendall(data)
                served += 1
                print(f'tcp echo #{served} from {peer[0]} ({len(data)} bytes)', flush=True)
            except OSError:
                pass
    srv.close()


def udp_server(bind, port, stop):
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind((bind, port))
    srv.settimeout(0.5)
    served = 0
    while not stop.is_set():
        try:
            data, peer = srv.recvfrom(4096)
        except socket.timeout:
            continue
        srv.sendto(data, peer)
        served += 1
        print(f'udp echo #{served} from {peer[0]} ({len(data)} bytes)', flush=True)
    srv.close()


def probe(target, proto, count):
    host, port = target.rsplit(':', 1)
    ok = 0
    for _ in range(count):
        token = os.urandom(24)
        try:
            if proto == 'tcp':
                with socket.create_connection((host, int(port)), timeout=6) as s:
                    s.sendall(token)
                    s.settimeout(6)
                    reply = s.recv(4096)
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.settimeout(6)
                    s.sendto(token, (host, int(port)))
                    reply, _ = s.recvfrom(4096)
            ok += reply == token
        except OSError as e:
            print(f'{proto} probe error: {e.__class__.__name__}', flush=True)
        time.sleep(0.3)
    print(f'{proto} probe {target}: {ok}/{count} exact echoes')
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bind')
    parser.add_argument('--port', type=int, default=47001)
    parser.add_argument('--seconds', type=float, default=900)
    parser.add_argument('--probe', help='host:port to probe through the board')
    parser.add_argument('--proto', choices=['tcp', 'udp'], default='tcp')
    parser.add_argument('--count', type=int, default=10)
    args = parser.parse_args()
    if args.probe:
        raise SystemExit(0 if probe(args.probe, args.proto, args.count) == args.count else 1)
    if not args.bind:
        parser.error('--bind <tailnet-ip> is required for the server (never bind 0.0.0.0 in the lab)')
    stop = threading.Event()
    threads = [threading.Thread(target=f, args=(args.bind, args.port, stop), daemon=True) for f in (tcp_server, udp_server)]
    for t in threads:
        t.start()
    print(f'echo listening on {args.bind}:{args.port} tcp+udp for {args.seconds:.0f} s', flush=True)
    time.sleep(args.seconds)
    stop.set()


if __name__ == '__main__':
    main()
