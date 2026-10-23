"""Minimal MQTT 3.1.1 broker for bench tests only (standard library).

Supports what the firmware and a test client need: CONNECT/CONNACK,
SUBSCRIBE/SUBACK (+ and # wildcards), PUBLISH QoS 0/1 with retain and PUBACK,
UNSUBSCRIBE, PINGREQ and DISCONNECT. No authentication, persistence or TLS:
bind it only to a private bench address (for example the bench PC's tailnet
address) and stop it after the test.

CONNECT payloads (client id, username, password) are parsed only to skip
them; they are never stored, printed or logged. Topics and payload sizes are
counted; payload contents are kept in memory for the test client only.

    python tools/lab_mqtt_broker.py --bind <bench-ip> --port 18883 --seconds 900
"""
import argparse
import selectors
import socket
import time

sel = selectors.DefaultSelector()


def read_varint(buf, i):
    value, mult = 0, 1
    for _ in range(4):
        if i >= len(buf):
            return None, i
        b = buf[i]; i += 1
        value += (b & 0x7F) * mult
        if not b & 0x80:
            return value, i
        mult *= 128
    raise ValueError('malformed remaining length')


def encode_len(n):
    out = bytearray()
    while True:
        b = n % 128; n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def string(s):
    b = s.encode('utf-8')
    return len(b).to_bytes(2, 'big') + b


def matches(filt, topic):
    f, t = filt.split('/'), topic.split('/')
    for i, part in enumerate(f):
        if part == '#':
            return True
        if i >= len(t) or (part != '+' and part != t[i]):
            return False
    return len(f) == len(t)


class Broker:
    def __init__(self):
        self.clients = {}      # sock -> {'buf': bytearray, 'subs': set()}
        self.retained = {}     # topic -> payload
        self.stats = {'connects': 0, 'publishes': 0, 'topics': set()}

    def send(self, sock, data):
        try:
            sock.sendall(data)
        except OSError:
            self.drop(sock)

    def drop(self, sock):
        if sock in self.clients:
            sel.unregister(sock)
            del self.clients[sock]
            sock.close()

    def publish(self, topic, payload, retain):
        self.stats['publishes'] += 1
        self.stats['topics'].add(topic)
        if retain:
            if payload:
                self.retained[topic] = payload
            else:
                self.retained.pop(topic, None)
        packet = bytes([0x30]) + encode_len(2 + len(topic.encode()) + len(payload)) + string(topic) + payload
        for sock, c in list(self.clients.items()):
            if any(matches(f, topic) for f in c['subs']):
                self.send(sock, packet)

    def handle(self, sock, ptype, flags, body):
        c = self.clients[sock]
        if ptype == 1:  # CONNECT: skip protocol name/level/flags/keepalive and payload
            self.stats['connects'] += 1
            self.send(sock, b'\x20\x02\x00\x00')
        elif ptype == 3:  # PUBLISH
            qos = (flags >> 1) & 3
            tl = int.from_bytes(body[0:2], 'big'); topic = body[2:2 + tl].decode('utf-8', 'replace'); i = 2 + tl
            pid = None
            if qos:
                pid = body[i:i + 2]; i += 2
            self.publish(topic, bytes(body[i:]), bool(flags & 1))
            if qos == 1:
                self.send(sock, b'\x40\x02' + pid)
            elif qos == 2:
                self.send(sock, b'\x50\x02' + pid)
        elif ptype == 6:  # PUBREL
            self.send(sock, b'\x70\x02' + body[0:2])
        elif ptype == 8:  # SUBSCRIBE
            pid = body[0:2]; i = 2; codes = bytearray(); new = []
            while i < len(body):
                tl = int.from_bytes(body[i:i + 2], 'big'); f = body[i + 2:i + 2 + tl].decode('utf-8', 'replace'); i += 2 + tl
                i += 1  # requested QoS
                c['subs'].add(f); new.append(f); codes.append(0)
            self.send(sock, b'\x90' + encode_len(2 + len(codes)) + pid + bytes(codes))
            for topic, payload in list(self.retained.items()):
                if any(matches(f, topic) for f in new):
                    self.send(sock, bytes([0x31]) + encode_len(2 + len(topic.encode()) + len(payload)) + string(topic) + payload)
        elif ptype == 10:  # UNSUBSCRIBE
            pid = body[0:2]; i = 2
            while i < len(body):
                tl = int.from_bytes(body[i:i + 2], 'big'); c['subs'].discard(body[i + 2:i + 2 + tl].decode()); i += 2 + tl
            self.send(sock, b'\xb0\x02' + pid)
        elif ptype == 12:
            self.send(sock, b'\xd0\x00')
        elif ptype == 14:
            self.drop(sock)

    def readable(self, sock):
        try:
            data = sock.recv(65536)
        except OSError:
            data = b''
        if not data:
            return self.drop(sock)
        c = self.clients[sock]; c['buf'] += data
        while len(c['buf']) >= 2:
            try:
                length, i = read_varint(c['buf'], 1)
            except ValueError:
                return self.drop(sock)
            if length is None or len(c['buf']) < i + length:
                return
            header = c['buf'][0]; body = bytes(c['buf'][i:i + length]); del c['buf'][:i + length]
            self.handle(sock, header >> 4, header & 0x0F, body)
            if sock not in self.clients:
                return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bind', required=True)
    ap.add_argument('--port', type=int, default=18883)
    ap.add_argument('--seconds', type=float, default=900)
    a = ap.parse_args()
    if a.bind in ('0.0.0.0', ''):
        ap.error('bind a specific private bench address, never all interfaces')
    broker = Broker()
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((a.bind, a.port)); srv.listen(16); srv.setblocking(False)
    sel.register(srv, selectors.EVENT_READ)
    print(f'lab broker on {a.bind}:{a.port} for {a.seconds:.0f} s', flush=True)
    end = time.monotonic() + a.seconds
    while time.monotonic() < end:
        for key, _ in sel.select(timeout=0.5):
            if key.fileobj is srv:
                conn, _ = srv.accept(); conn.setblocking(True); conn.settimeout(5)
                broker.clients[conn] = {'buf': bytearray(), 'subs': set()}
                sel.register(conn, selectors.EVENT_READ)
            else:
                broker.readable(key.fileobj)
    print(f"connects={broker.stats['connects']} publishes={broker.stats['publishes']} "
          f"topics={len(broker.stats['topics'])} retained={len(broker.retained)}", flush=True)


if __name__ == '__main__':
    main()
