"""Host-side primitives for an explicitly authorized Service Gateway benchmark.

Importing this module performs no device or network operations. Reports contain
private network data and must stay under ignored build/private-device/.
"""
import copy
import hashlib
import http.server
import math
import secrets
import threading
import time

from cleanup_gateway_lab_device import FIELDS


def configs(rows):
    return [{key: row[key] for key in FIELDS} for row in rows]


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))]


class TemporaryRule:
    """Preserve unrelated rules, including edits made by the owner during a run.

    The current device API has no atomic compare-and-swap. A second read detects
    observed drift but cannot eliminate a simultaneous administrator-write race.
    Never use this tool while another administrator edits forwarding rules.
    """
    def __init__(self, api, row, save=lambda: None):
        self.api, self.row, self.save = api, copy.deepcopy(row), save
        self.original = configs(api('/api/tailnet-forward')['rules'])
        self.original_leases = api('/api/service-leases')
        self.attempted = False

    def replace(self, expected, desired):
        if configs(self.api('/api/tailnet-forward')['rules']) != expected:
            raise RuntimeError('Concurrent forwarding edit; refusing stale write')
        if not self.api('/api/tailnet-forward', {'rules': desired}).get('ok'):
            raise RuntimeError('Forwarding save rejected')

    def install(self, seconds):
        if type(seconds) is not int or not 60 <= seconds <= 604800:
            raise ValueError('Lease seconds must be 60..604800')
        state = self.api('/api/tailnet-forward')
        if configs(state['rules']) != self.original:
            raise RuntimeError('Forwarding changed before setup')
        if len(self.original) >= state['max']:
            raise RuntimeError('No free forwarding rule slot')
        if any(r['name'] == self.row['name'] or
               (r['protocol'] == self.row['protocol'] and
                r['listen_port'] == self.row['listen_port']) for r in self.original):
            raise RuntimeError('Benchmark rule name/port conflict')
        self.attempted = True  # Persist intent before a possibly ambiguous write.
        self.save()
        self.replace(self.original, self.original + [self.row])
        rows = self.api('/api/tailnet-forward')['rules']
        if configs(rows) != self.original + [self.row]:
            raise RuntimeError('Rule installation did not match the request')
        index = len(self.original)
        lease = next(x for x in self.api('/api/service-leases') if x['index'] == index)
        result = self.api('/api/operations', dict(action='lease', index=index,
            rule_token=lease['rule_token'], seconds=seconds, permanent=False,
            delete_on_expiry=True))
        if not result.get('ok'):
            raise RuntimeError('Temporary lease rejected')

    def cleanup(self):
        rows = configs(self.api('/api/tailnet-forward')['rules'])
        matches = [r for r in rows if r['name'] == self.row['name']]
        if len(matches) > 1 or (matches and matches[0] != self.row):
            raise RuntimeError('Benchmark rule modified; refusing to delete owner work')
        if matches:
            self.replace(rows, [r for r in rows if r['name'] != self.row['name']])
        after = configs(self.api('/api/tailnet-forward')['rules'])
        if any(r['name'] == self.row['name'] for r in after):
            raise RuntimeError('Temporary rule still present')
        leases = self.api('/api/service-leases')
        return dict(temporary_rule_removed=True,
            original_rules_unchanged=all(r in after for r in self.original),
            original_leases_unchanged=all(any(
                l['rule_token'] == old['rule_token'] and
                l['effective_enabled'] == old['effective_enabled'] and
                l['temporary'] == old['temporary'] for l in leases)
                for old in self.original_leases))


def restore_console(api, original, last_owned, attempted):
    """Restore only a setting still matching the benchmark's last write intent."""
    current = api('/api/sdlog')['console_level']
    if attempted and current == last_owned and current != original:
        api('/api/sdlog', {'console_level': original})
    return api('/api/sdlog')['console_level'] == original


class FileService:
    """Bound owned-peer file server: one path, one source, bounded concurrency."""
    def __init__(self, bind, allowed_source, path, port=0):
        self.file, self.allowed_source = path, allowed_source
        self.url_path = '/' + secrets.token_urlsafe(24) + '/payload.bin'
        self.records, self.record_lock = [], threading.Lock()
        self.slot = threading.BoundedSemaphore(1)
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.client_address[0] != outer.allowed_source or self.path != outer.url_path:
                    self.close_connection = True
                    self.send_error(403)
                    return
                if not outer.slot.acquire(blocking=False):
                    self.close_connection = True
                    self.send_error(429)
                    return
                record = dict(source=self.client_address[0], bytes_written=0,
                              started_epoch=time.time())
                with outer.record_lock:
                    outer.records.append(record)
                try:
                    self.connection.settimeout(15)
                    size = outer.file.stat().st_size
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/octet-stream')
                    self.send_header('Content-Length', str(size))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    with outer.file.open('rb') as stream:
                        while chunk := stream.read(65536):
                            self.wfile.write(chunk)
                            record['bytes_written'] += len(chunk)
                except OSError as error:
                    record['error'] = type(error).__name__
                finally:
                    self.close_connection = True
                    record['finished_epoch'] = time.time()
                    outer.slot.release()

            def do_PUT(self):
                # Upload direction (LAN client -> ESP -> Tailnet server): the
                # server hashes what it received; nothing is stored on disk.
                if self.client_address[0] != outer.allowed_source or self.path != outer.url_path:
                    self.close_connection = True
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get('Content-Length', ''))
                except ValueError:
                    length = -1
                if length != outer.file.stat().st_size:
                    self.close_connection = True
                    self.send_error(411 if length < 0 else 413)
                    return
                if not outer.slot.acquire(blocking=False):
                    self.close_connection = True
                    self.send_error(429)
                    return
                record = dict(source=self.client_address[0], method='PUT', bytes_read=0,
                              started_epoch=time.time())
                with outer.record_lock:
                    outer.records.append(record)
                digest = hashlib.sha256()
                try:
                    self.connection.settimeout(15)
                    while record['bytes_read'] < length:
                        chunk = self.rfile.read(min(65536, length - record['bytes_read']))
                        if not chunk:
                            break
                        digest.update(chunk)
                        record['bytes_read'] += len(chunk)
                    record['sha256'] = digest.hexdigest()
                    body = ('{"bytes":%d,"sha256":"%s"}' % (record['bytes_read'], record['sha256'])).encode()
                    self.send_response(200 if record['bytes_read'] == length else 400)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(body)
                except OSError as error:
                    record['error'] = type(error).__name__
                finally:
                    self.close_connection = True
                    record['finished_epoch'] = time.time()
                    outer.slot.release()

        # Base server dispatch is serial: no unbounded per-connection threads.
        # A stalled client is bounded by the socket timeout; shutdown waits for it.
        self.server = http.server.HTTPServer((bind, port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=17)


def transfer(opener, url, output, expected_size, expected_hash, *, timeout=15,
             total_timeout=180, progress=lambda row: None, cancelled=lambda: False):
    """One actual on-disk HTTP transfer; never retries or resumes silently."""
    import urllib.request
    start = time.monotonic()
    digest, count, windows = hashlib.sha256(), 0, []
    last_time, last_count = start, 0
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity'})
    with opener.open(request, timeout=timeout) as response, output.open('wb') as stream:
        if response.status != 200 or int(response.headers.get('Content-Length', '-1')) != expected_size:
            raise ValueError('Unexpected HTTP status or file length')
        while True:
            if cancelled():
                raise RuntimeError('Cancelled or resource guard stopped transfer')
            now = time.monotonic()
            if now - start >= total_timeout:
                raise TimeoutError('Total transfer deadline')
            # read1 returns after one underlying read. A trickling response must
            # not keep read(65536) inside a single iteration past the deadline.
            chunk = response.read1(min(65536, expected_size - count + 1))
            if not chunk:
                break
            stream.write(chunk)
            digest.update(chunk)
            count += len(chunk)
            if count > expected_size:
                raise ValueError('Response exceeded expected file size')
            now = time.monotonic()
            if now - last_time >= 5:
                row = dict(bytes=count, elapsed_s=now-start,
                           mbps=(count-last_count)*8/(now-last_time)/1e6)
                windows.append(row)
                progress(row)
                last_time, last_count = now, count
    elapsed = time.monotonic() - start
    if count != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError('Incomplete or corrupted file')
    return dict(bytes=count, elapsed_s=elapsed, mbps=count*8/elapsed/1e6,
                sha256=digest.hexdigest(), integrity_pass=True, windows=windows,
                retries=0, resumed=False)


class _UploadBody:
    """File-like PUT body: enforces cancel/deadline per read and records windows."""
    def __init__(self, path, size, start, total_timeout, progress, cancelled):
        self.stream, self.size, self.start = path.open('rb'), size, start
        self.total_timeout, self.progress, self.cancelled = total_timeout, progress, cancelled
        self.count, self.windows, self.digest = 0, [], hashlib.sha256()
        self.last_time, self.last_count = start, 0

    def read(self, amount=65536):
        if self.cancelled():
            raise RuntimeError('Cancelled or resource guard stopped transfer')
        now = time.monotonic()
        if now - self.start >= self.total_timeout:
            raise TimeoutError('Total transfer deadline')
        chunk = self.stream.read(min(amount if amount and amount > 0 else 65536, 65536))
        self.digest.update(chunk)
        self.count += len(chunk)
        if self.count > self.size:
            raise ValueError('Source grew beyond the expected size')
        if now - self.last_time >= 5:
            row = dict(bytes=self.count, elapsed_s=now-self.start,
                       mbps=(self.count-self.last_count)*8/(now-self.last_time)/1e6)
            self.windows.append(row)
            self.progress(row)
            self.last_time, self.last_count = now, self.count
        return chunk

    def close(self):
        self.stream.close()


def upload(opener, url, source, expected_size, expected_hash, *, timeout=15,
           total_timeout=180, progress=lambda row: None, cancelled=lambda: False):
    """One actual HTTP PUT of an on-disk file; the receiving server's SHA-256 must
    match. Like transfer(), it never retries or resumes silently."""
    import json
    import urllib.request
    start = time.monotonic()
    body = _UploadBody(source, expected_size, start, total_timeout, progress, cancelled)
    request = urllib.request.Request(url, data=body, method='PUT', headers={
        'Content-Type': 'application/octet-stream', 'Content-Length': str(expected_size)})
    try:
        with opener.open(request, timeout=timeout) as response:
            reply = response.read(4096)
            status = response.status
    finally:
        body.close()
    elapsed = time.monotonic() - start
    if status != 200:
        raise ValueError('Unexpected HTTP status')
    received = json.loads(reply)
    if (body.count != expected_size or body.digest.hexdigest() != expected_hash
            or received.get('bytes') != expected_size or received.get('sha256') != expected_hash):
        raise ValueError('Incomplete or corrupted upload')
    return dict(bytes=body.count, elapsed_s=elapsed, mbps=body.count*8/elapsed/1e6,
                sha256=expected_hash, integrity_pass=True, windows=body.windows,
                retries=0, resumed=False, direction='upload')
