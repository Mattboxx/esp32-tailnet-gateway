"""Response headers of the Web UI fit the HTTP server's limit.

esp_http_server keeps at most conf.max_resp_headers additional headers per
response and silently drops the rest. 3.0.1-beta.1 added an ETag to the
page: with the default limit of 8 the Content-Encoding header was dropped and
browsers showed the gzip bytes as text. This counts, in the actual
main/web_ui.c, the headers every handler sets (the shared security headers
included) and checks the limit, and that gzip responses declare their
encoding before the optional headers. Host only.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / 'main/web_ui.c').read_text(encoding='utf-8')

m = re.search(r'conf\.max_resp_headers\s*=\s*(\d+);', src)
limit = int(m.group(1)) if m else 8          # esp_http_server default
sec = re.search(r'static void set_browser_security_headers\(httpd_req_t \*req\)\n\{(.*?)\n\}', src, re.S).group(1)
shared = sec.count('httpd_resp_set_hdr(')
assert shared >= 6, shared

checked = 0
for m in re.finditer(r'\nstatic esp_err_t (\w+)\(httpd_req_t \*req\)\n\{(.*?)\n\}', src, re.S):
    name, body = m.group(1), m.group(2)
    own = len(re.findall(r'httpd_resp_set_hdr\(', body))
    total = own + (shared if 'set_browser_security_headers(req)' in body else 0)
    assert total <= limit, f'{name}: {total} response headers, server keeps {limit}'
    if '"Content-Encoding", "gzip"' in body and 'set_browser_security_headers(req)' in body:
        assert body.index('"Content-Encoding", "gzip"') < body.index('set_browser_security_headers(req)'), \
            f'{name}: Content-Encoding must be set before the optional headers'
    checked += 1
assert checked > 20, checked
for handler in ('index_handler', 'i18n_handler'):
    assert re.search(r'static esp_err_t ' + handler + r'\(', src), handler
print(f'PASS: {checked} handlers in web_ui.c stay within max_resp_headers={limit} (shared security headers {shared}); '
      'gzip encoding declared before optional headers (host)')
