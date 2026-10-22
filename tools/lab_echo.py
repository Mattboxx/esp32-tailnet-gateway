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
import ipaddress
import math
import os
import socket
import struct
import sys
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


def client_socket(proto, source_ip=None, interface_index=None, timeout=6):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM if proto=='tcp' else socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        if interface_index is not None:
            if sys.platform!='win32':raise ValueError('--interface-index currently requires Windows')
            # IP_UNICAST_IF uses a DWORD interface index in network byte order:
            # https://learn.microsoft.com/windows/win32/winsock/ipproto-ip-socket-options
            s.setsockopt(socket.IPPROTO_IP,getattr(socket,'IP_UNICAST_IF',31),struct.pack('!I',interface_index))
        if source_ip:s.bind((source_ip,0))
        return s
    except BaseException:
        s.close();raise


def probe(target, proto, count, source_ip=None, interface_index=None, timeout=6):
    host, port = target.rsplit(':', 1)
    ok = 0
    for _ in range(count):
        token = os.urandom(24)
        try:
            with client_socket(proto,source_ip,interface_index,timeout) as s:
                s.connect((host,int(port)))
                if proto == 'tcp':
                    s.sendall(token)
                    reply=b''
                    while len(reply)<len(token):
                        part=s.recv(len(token)-len(reply))
                        if not part:break
                        reply+=part
                else:
                    # Connected UDP accepts only this exact destination tuple.
                    s.send(token);reply=s.recv(4096)
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
    parser.add_argument('--source-ip',help='Bind the existing local LAN address; never creates an address/route')
    parser.add_argument('--interface-index',type=int,help='Windows: force only this probe socket onto a specific interface')
    parser.add_argument('--timeout',type=float,default=6)
    args = parser.parse_args()
    if not 1<=args.count<=1000 or not math.isfinite(args.timeout) or not 0<args.timeout<=30:
        parser.error('count must be 1..1000 and timeout within (0,30] seconds')
    if args.source_ip:ipaddress.IPv4Address(args.source_ip)
    if args.interface_index is not None and not 1<=args.interface_index<=0xffffffff:
        parser.error('interface index must be 1..4294967295')
    if not math.isfinite(args.seconds) or not 0<args.seconds<=86400:parser.error('invalid service duration')
    if args.probe:
        raise SystemExit(0 if probe(args.probe,args.proto,args.count,args.source_ip,args.interface_index,args.timeout)==args.count else 1)
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
