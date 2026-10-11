import json
import unittest
from http.cookiejar import CookieJar
from urllib.request import Request

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.bidi import BidiError, BidiSession
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


class Socket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    def send(self, data):
        self.sent.append(json.loads(data))

    def recv(self, timeout):
        return json.dumps(next(self.messages))


class BrowserProtocolTests(unittest.TestCase):
    def test_intercept_blocks_threat_without_retaining_cookies(self):
        def reject(url):
            raise AppError(ErrorCode.SITE_BLOCKED, 'Known threat')

        socket = Socket([])
        session = BidiSession(socket, request_guard=reject)
        session._event({'method': 'network.beforeRequestSent', 'params': {
            'isBlocked': True, 'request': {'request': 'blocked-request',
                'url': 'https://malware.example/video', 'cookies': [{'name': 'secret'}]}}})
        self.assertEqual(socket.sent, [{'id': 1, 'method': 'network.failRequest',
                                       'params': {'request': 'blocked-request'}}])
        self.assertEqual(session.request_cookies, {})

    def test_intercept_acknowledgement_does_not_lose_navigation_reply(self):
        checked = []
        socket = Socket([
            {'type': 'event', 'method': 'network.beforeRequestSent', 'params': {
                'isBlocked': True, 'request': {'request': 'safe-request',
                                              'url': 'https://safe.example/video'}}},
            {'type': 'success', 'id': 2, 'result': {}},
            {'type': 'success', 'id': 1, 'result': {'navigation': 'complete'}},
        ])
        session = BidiSession(socket, request_guard=checked.append)
        self.assertEqual(session.command('browsingContext.navigate', {}),
                         {'navigation': 'complete'})
        self.assertEqual(checked, ['https://safe.example/video'])
        self.assertEqual(socket.sent[1]['method'], 'network.continueRequest')
        self.assertEqual(session.identifier, 2)

    def test_events_and_unrelated_replies_do_not_replace_command_response(self):
        socket = Socket([
            {'type': 'event', 'method': 'network.responseCompleted', 'params': {
                'response': {'url': 'https://example.com/media', 'mimeType': 'video/webm'}}},
            {'type': 'success', 'id': 99, 'result': {'wrong': True}},
            {'type': 'success', 'id': 1, 'result': {'correct': True}},
        ])
        session = BidiSession(socket)
        self.assertEqual(session.command('test', {}), {'correct': True})
        self.assertEqual(session.media, ['https://example.com/media'])

    def test_protocol_error_does_not_reveal_page_url(self):
        session = BidiSession(Socket([{'type': 'error', 'id': 1, 'error': 'no such frame',
                                      'message': 'Private page https://example.com/secret'}]))
        with self.assertRaises(BidiError) as caught:
            session.command('test', {})
        self.assertEqual(str(caught.exception), 'no such frame')

    def test_private_cookie_remains_session_only_and_domain_scoped(self):
        client = type('Client', (), {'cookiejar': CookieJar()})()
        YtDlpGateway._load_session_cookies(client, ({
            'name': 'session', 'value': {'type': 'string', 'value': 'temporary'},
            'domain': 'video.example.com', 'path': '/', 'secure': True,
        },))
        cookie = next(iter(client.cookiejar))
        self.assertTrue(cookie.discard)
        self.assertIsNone(cookie.expires)
        allowed = Request('https://video.example.com/stream')
        client.cookiejar.add_cookie_header(allowed)
        self.assertEqual(allowed.get_header('Cookie'), 'session=temporary')
        unrelated = Request('https://unrelated.example.org/')
        client.cookiejar.add_cookie_header(unrelated)
        self.assertIsNone(unrelated.get_header('Cookie'))

    def test_cookie_events_are_kept_by_request_url(self):
        session = BidiSession(Socket([]))
        cookie = {'name': 'test', 'value': {'type': 'string', 'value': 'value'}}
        session._event({'method': 'network.beforeRequestSent', 'params': {
            'request': {'url': 'https://example.com/v.mp4', 'cookies': [cookie]}}})
        self.assertEqual(session.request_cookies['https://example.com/v.mp4'], [
            {**cookie, 'domain': 'example.com', 'path': '/', 'secure': True},
        ])

    def test_rejected_media_response_is_not_selected(self):
        session = BidiSession(Socket([]))
        session._event({'method': 'network.responseCompleted', 'params': {'response': {
            'url': 'https://example.com/rejected.mp4', 'mimeType': 'video/mp4', 'status': 401,
        }}})
        self.assertEqual(session.media, [])

    def test_request_headers_preserve_iframe_referer(self):
        session = BidiSession(Socket([]))
        session._event({'method': 'network.beforeRequestSent', 'params': {'request': {
            'url': 'https://cdn.example.com/video.mp4', 'headers': [
                {'name': 'Referer', 'value': {'type': 'string', 'value': 'https://player.example.com/embed'}},
                {'name': 'Cookie', 'value': {'type': 'string', 'value': 'secret'}},
            ],
        }}})
        self.assertEqual(session.request_headers['https://cdn.example.com/video.mp4'], {
            'referer': 'https://player.example.com/embed',
        })
