from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib.parse import urlsplit

from video_downloader.domain.errors import AppError, ErrorCode


class BidiError(RuntimeError):
    def __init__(self, code: str) -> None:
        # Protocol error messages may contain private URLs; retain only the code.
        self.code = code
        super().__init__(code)


class BidiSession:
    def __init__(self, websocket, request_guard: Callable[[str], None] | None = None) -> None:
        self.websocket = websocket
        self.identifier = 0
        self.request_guard = request_guard
        self.media: list[str] = []
        self.request_cookies: dict[str, list[dict]] = {}
        self.request_headers: dict[str, dict[str, str]] = {}

    def command(self, method: str, params: dict, timeout: float = 15) -> dict:
        self.identifier += 1
        identifier = self.identifier
        self.websocket.send(json.dumps({'id': identifier, 'method': method, 'params': params}))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Browser command timed out')
            response = json.loads(self.websocket.recv(timeout=remaining))
            if response.get('type') == 'event':
                self._event(response)
                continue
            if response.get('id') != identifier:
                continue
            if response.get('type') == 'error':
                raise BidiError(str(response.get('error') or 'unknown error'))
            if response.get('type') != 'success':
                raise BidiError('invalid response')
            return response.get('result') or {}

    def _event(self, event: dict) -> None:
        if event.get('method') == 'network.beforeRequestSent':
            request = event.get('params', {}).get('request', {})
            url = str(request.get('url') or '')
            parsed = urlsplit(url)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                return
            if self.request_guard and event.get('params', {}).get('isBlocked'):
                action = 'network.continueRequest'
                try:
                    self.request_guard(url)
                except AppError as exc:
                    if exc.code not in {ErrorCode.SITE_BLOCKED, ErrorCode.INVALID_LINK, ErrorCode.NETWORK}:
                        raise
                    action = 'network.failRequest'
                self.identifier += 1
                # Don't wait recursively inside the event dispatcher. The next
                # receive loop ignores this acknowledgement's unrelated id.
                self.websocket.send(json.dumps({
                    'id': self.identifier, 'method': action,
                    'params': {'request': request['request']},
                }))
                if action == 'network.failRequest':
                    return
            cookies = request.get('cookies') or []
            if cookies and len(self.request_cookies) < 128:
                # BiDi CookieHeader omits domain/path. Scope it to the exact
                # request host instead of silently dropping session cookies.
                self.request_cookies[url] = [
                    {**cookie, 'domain': cookie.get('domain') or parsed.hostname,
                     'path': cookie.get('path') or '/',
                     'secure': cookie.get('secure', parsed.scheme == 'https')}
                    for cookie in cookies
                ]
            if len(self.request_headers) < 128:
                headers = {}
                for header in request.get('headers') or []:
                    name = str(header.get('name') or '').lower()
                    value = header.get('value') or {}
                    if name in {'referer', 'origin', 'user-agent'} and value.get('type') == 'string':
                        headers[name] = str(value.get('value') or '')
                self.request_headers[url] = headers
            return
        if event.get('method') != 'network.responseCompleted':
            return
        response = event.get('params', {}).get('response', {})
        if response.get('status', 200) >= 400:
            return
        url = str(response.get('url') or '')
        mime = str(response.get('mimeType') or '').split(';')[0].lower()
        path = urlsplit(url).path.lower()
        if not url.startswith(('http://', 'https://')):
            return
        if mime in {'application/vnd.apple.mpegurl', 'application/x-mpegurl',
                    'application/dash+xml', 'video/mp4', 'video/webm'} or path.endswith(
                        ('.m3u8', '.mpd', '.mp4', '.webm')):
            if url not in self.media and len(self.media) < 128:
                self.media.append(url)
