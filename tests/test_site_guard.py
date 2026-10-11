import os
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.network_guard import PublicNetworkGuard
from video_downloader.infrastructure.site_guard import SiteGuard
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


def feed(*extra):
    domains = [f"threat-{number}.example" for number in range(60)] + list(extra)
    return ("# Title: HaGeZi's Threat Intelligence Feeds - test fixture\n" +
            "\n".join(domains)).encode()


@pytest.fixture
def guard(tmp_path):
    bundled = tmp_path / "bundled.txt"
    bundled.write_bytes(feed("blocked.example", "xn--fa-hia.de"))
    return SiteGuard(tmp_path / "cache", bundled)


def test_blocked_domain_subdomains_case_trailing_dot_and_idn_are_rejected(guard):
    for url in ("https://blocked.example/video", "https://video.BLOCKED.example./video",
                "https://faß.de/video"):
        with pytest.raises(AppError) as caught:
            guard.ensure_allowed(url)
        assert caught.value.code == ErrorCode.SITE_BLOCKED
    guard.ensure_allowed("https://blocked.example.safe.example/video")
    guard.ensure_allowed("https://notblocked.example/video")


def test_known_threat_is_rejected_before_dns_or_site_contact(guard):
    network = PublicNetworkGuard(guard)
    with patch("socket.getaddrinfo") as dns:
        with pytest.raises(AppError):
            network.ensure_public("https://blocked.example/video")
    dns.assert_not_called()


def test_fresh_bundled_list_does_not_fetch_or_submit_video_url(guard):
    with patch.object(guard, "_fetch") as fetch:
        guard.prepare()
        guard.ensure_allowed("https://safe.example/private-video?token=secret")
    fetch.assert_not_called()


def test_update_atomically_adds_new_threats_and_preserves_old_list_on_bad_response(guard):
    with patch.object(guard, "_fetch", return_value=feed("new-threat.example")):
        guard.prepare(force=True)
    with pytest.raises(AppError) as caught:
        guard.ensure_allowed("https://new-threat.example/video")
    assert caught.value.code == ErrorCode.SITE_BLOCKED
    cached = guard._cache.read_bytes()
    with patch.object(guard, "_fetch", return_value=b"<html>Unavailable</html>"):
        with pytest.raises(AppError) as caught:
            guard.prepare(force=True)
    assert caught.value.code == ErrorCode.PROTECTION_UNAVAILABLE
    assert guard._cache.read_bytes() == cached
    assert "cached" in guard.status


def test_failed_background_update_uses_cached_list_with_visible_status(guard):
    old = time.time() - 86400
    os.utime(guard._bundled, (old, old))
    with patch.object(guard, "_fetch", side_effect=OSError("offline")) as fetch:
        guard.prepare()
        guard.prepare()
    assert fetch.call_count == 1
    assert "update unavailable" in guard.status
    with pytest.raises(AppError):
        guard.ensure_allowed("https://blocked.example/video")


def test_no_list_and_failed_update_never_claims_site_is_checked(tmp_path):
    guard = SiteGuard(tmp_path / "cache", tmp_path / "missing.txt")
    with patch.object(guard, "_fetch", side_effect=OSError("offline")):
        with pytest.raises(AppError) as caught:
            guard.prepare()
    assert caught.value.code == ErrorCode.PROTECTION_UNAVAILABLE
    assert "unavailable" in guard.status


def test_engine_subrequests_and_redirect_responses_are_checked(guard):
    gateway = YtDlpGateway(network_guard=PublicNetworkGuard(guard))
    response = SimpleNamespace(url="https://blocked.example/redirect", close=Mock())
    client = SimpleNamespace(urlopen=Mock(return_value=response))
    original_open = client.urlopen
    gateway._guard_client(client)
    with pytest.raises(AppError):
        client.urlopen(SimpleNamespace(url="https://blocked.example/video"))
    original_open.assert_not_called()
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
        with pytest.raises(AppError):
            client.urlopen(SimpleNamespace(url="https://safe.example/video"))
    response.close.assert_called_once()
