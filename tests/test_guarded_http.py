from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.guarded_http import protect_session


def response(status, location=None):
    return SimpleNamespace(status_code=status, headers={"Location": location} if location else {}, close=Mock())


def test_malicious_redirect_is_rejected_before_destination_request():
    redirect = response(302, "http://127.0.0.1/private")
    send = Mock(return_value=redirect)
    session = SimpleNamespace(request=send)

    def guard(url):
        if "127.0.0.1" in url:
            raise AppError(ErrorCode.INVALID_LINK, "Private network")

    protect_session(session, guard)
    with pytest.raises(AppError) as caught:
        session.request("GET", "https://public.example/video")
    assert caught.value.code == ErrorCode.INVALID_LINK
    assert send.call_count == 1
    assert send.call_args.kwargs["allow_redirects"] is False
    redirect.close.assert_called_once()


def test_cross_origin_redirect_strips_explicit_secrets_and_preserves_same_origin_cookie():
    send = Mock(side_effect=[response(302, "/next"), response(302, "https://cdn.example/film"), response(200)])
    session = SimpleNamespace(request=send)
    protect_session(session, lambda _: None)
    session.request("GET", "https://public.example/start", headers={"Authorization": "synthetic", "Cookie": "test=1"})
    assert send.call_args_list[1].kwargs["headers"]["Cookie"] == "test=1"
    assert send.call_args_list[2].kwargs["headers"] == {}


def test_redirect_loop_closes_all_responses_and_has_a_fixed_limit():
    redirects = [response(302, "/again") for _ in range(6)]
    send = Mock(side_effect=redirects)
    session = SimpleNamespace(request=send)
    protect_session(session, lambda _: None)
    with pytest.raises(AppError) as caught:
        session.request("GET", "https://public.example/start")
    assert caught.value.code == ErrorCode.NETWORK
    assert send.call_count == 6
    for redirect in redirects:
        redirect.close.assert_called_once()


@pytest.mark.parametrize("status,method,data", [(302, "GET", None), (303, "GET", None), (307, "POST", b"fixture"), (308, "POST", b"fixture")])
def test_post_redirects_keep_http_method_semantics(status, method, data):
    send = Mock(side_effect=[response(status, "/next"), response(200)])
    session = SimpleNamespace(request=send)
    protect_session(session, lambda _: None)
    session.request("POST", "https://public.example/start", data=b"fixture", headers={"Content-Length": "7"})
    final = send.call_args.kwargs
    assert final["method"] == method
    assert final.get("data") == data
    assert ("Content-Length" in final["headers"]) == (method == "POST")
