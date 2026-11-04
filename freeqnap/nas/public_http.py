"""Bounded public-internet reads with DNS pinning and redirect revalidation.

No ambient proxy, cookie jar, credentials, private targets or certificate bypass.
"""
import contextlib
import http.client
import ipaddress
import json
import socket
import ssl
import urllib.parse

USER_AGENT = 'FreeQNAP/0.2 (+https://github.com/mastechnica/FreeQNAP)'

def target(url, resolver=socket.getaddrinfo):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError('Enter a public HTTP or HTTPS URL')
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username is not None or p.password is not None or p.fragment:
        raise ValueError('Use a public HTTP(S) URL without embedded login or fragment')
    try:port = p.port or (443 if p.scheme == 'https' else 80)
    except ValueError:raise ValueError('Invalid internet port') from None
    if not 1 <= port <= 65535:raise ValueError('Invalid internet port')
    try:addresses = sorted({r[4][0] for r in resolver(p.hostname, port, type=socket.SOCK_STREAM)})
    except OSError:raise ValueError('The internet host could not be resolved') from None
    def public_address(address):
        ip=ipaddress.ip_address(address)
        if not ip.is_global:return False
        if ip.version==6:
            if ip.ipv4_mapped:return ip.ipv4_mapped.is_global
            if ip.sixtofour or ip.teredo or ip in ipaddress.ip_network('64:ff9b::/96') or ip in ipaddress.ip_network('64:ff9b:1::/48'):return False
        return True
    if not addresses or any(not public_address(a) for a in addresses):
        raise ValueError('Private, local and reserved internet targets are blocked')
    return p, addresses

@contextlib.contextmanager
def open_url(url, *, headers=None, timeout=8, method='GET'):
    if method not in ('GET', 'HEAD'):raise ValueError('Only read requests are supported')
    connection = None
    try:
        for _ in range(5):
            p, addresses = target(url)
            connection = http.client.HTTPConnection(p.hostname, p.port or (443 if p.scheme == 'https' else 80), timeout=timeout)
            def connect():
                last = None
                for address in addresses:
                    try:
                        raw = socket.create_connection((address, connection.port), timeout=timeout)
                        connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname) if p.scheme == 'https' else raw
                        return
                    except OSError as error:
                        if 'raw' in locals():raw.close()
                        last = error
                raise ValueError('The public internet service could not be reached') from last
            connection.connect = connect
            allowed = {'Accept', 'Range', 'If-Range', 'Icy-MetaData'}
            if headers and set(headers) - allowed:raise ValueError('Unsupported public request headers')
            request_headers = {'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity', **(headers or {})}
            try:
                connection.request(method, urllib.parse.urlunsplit(('', '', p.path or '/', p.query, '')), headers=request_headers)
                response = connection.getresponse()
            except (OSError, http.client.HTTPException):raise ValueError('The public internet service did not respond') from None
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                connection.close();connection = None
                if not location:raise ValueError('Invalid internet redirect')
                url = urllib.parse.urljoin(url, location);continue
            if response.status not in (200, 206):raise ValueError('The public internet service returned HTTP ' + str(response.status))
            yield response, url
            return
        raise ValueError('Too many internet redirects')
    finally:
        if connection:connection.close()

def fetch(url, limit=2 * 1024**2):
    with open_url(url) as (response, _):
        raw = response.read(limit + 1)
        if len(raw) > limit:raise ValueError('Internet response exceeded the size limit')
        return raw

def json_fetch(url, limit=2 * 1024**2):
    try:return json.loads(fetch(url, limit))
    except (UnicodeDecodeError, json.JSONDecodeError):raise ValueError('The service returned invalid JSON') from None

def probe_stream(url):
    with open_url(url, headers={'Range': 'bytes=0-511', 'Accept': 'audio/*,application/ogg,*/*;q=0.1'}, timeout=6) as (response, resolved):
        kind = (response.getheader('Content-Type') or '').split(';')[0].lower()
        sample = response.read(512)
        if not sample or sample.lstrip().lower().startswith((b'#extm3u',b'[playlist]',b'<!doctype',b'<html',b'<?xml')) or kind in ('audio/x-mpegurl','audio/mpegurl') or not (kind.startswith('audio/') or kind in ('application/ogg', 'application/octet-stream')):
            raise ValueError('This address did not return a direct audio stream')
        return {'url': resolved, 'content_type': kind, 'sample_bytes': len(sample), 'working': True}
