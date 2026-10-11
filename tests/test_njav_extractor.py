from unittest.mock import Mock, patch

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError

from video_downloader.infrastructure.njav_extractor import NjavIE
from video_downloader.infrastructure.yt_dlp_gateway import YtDlpGateway


def packed_page(source='https://media.example/master.m3u8'):
    # Synthetic page containing only a packed source assignment, no remote URL.
    return "<script>eval(function(p,a,c,k,e,d){}('0=\\'1\\';',2,2,'source|" + source + "'.split('|')))</script>"


def test_packed_source_is_decoded_as_text_without_executing_scripts():
    page = packed_page() + '<script>throw new Error("must not execute")</script>'
    assert NjavIE.manifest_from_page(page) == 'https://media.example/master.m3u8'


@pytest.mark.parametrize('page', [
    '<video src="https://media.example/ad.mp4"></video>',
    packed_page('javascript:alert(1)'),
    packed_page('https://media.example/not-a-manifest'),
    "<script>}('0=1;',36,999999,'source|https'.split('|'))</script>",
    '<html>' + 'x' * (2 * 1024 * 1024),
], ids=['unrelated-video', 'javascript-url', 'non-manifest', 'oversized-dictionary', 'oversized-page'])
def test_invalid_or_unrelated_sources_are_rejected(page):
    with pytest.raises(ExtractorError):
        NjavIE.manifest_from_page(page)


def test_site_support_is_restricted_to_exact_known_hosts():
    assert NjavIE.supports('https://njavtv.com/en/synthetic-video')
    assert NjavIE.supports('https://www.njavtv.com/synthetic-video')
    assert not NjavIE.supports('https://njavtv.com.attacker.example/en/video')
    assert not NjavIE.supports('https://another.example/en/video')


def test_inspection_and_direct_download_share_site_dispatch():
    client = Mock()
    raw = {'id': 'synthetic-video', 'formats': [{'height': 720}]}
    with patch.object(NjavIE, 'extract', return_value=raw):
        for download in (False, True):
            YtDlpGateway._extract_info(client, 'https://njavtv.com/en/synthetic-video', download)
            client.process_ie_result.assert_called_with(raw, download=download)
    client.extract_info.assert_not_called()
    YtDlpGateway._extract_info(client, 'https://another.example/video', False)
    client.extract_info.assert_called_once_with('https://another.example/video', download=False)


def test_formats_keep_page_referer_for_manifest_and_fragments():
    url = 'https://njavtv.com/en/synthetic-video'
    extractor = NjavIE(YoutubeDL({"quiet": True}))
    html = '<meta property="og:title" content="Synthetic video">' + packed_page()
    with patch.object(extractor, '_download_webpage', return_value=html), patch.object(
        extractor, '_extract_m3u8_formats', return_value=[{'url': 'https://media.example/720.m3u8',
                                                         'height': 720}]
    ) as manifest:
        info = extractor._real_extract(url)
    assert info['title'] == 'Synthetic video'
    assert info['formats'][0]['http_headers']['Referer'] == url
    assert manifest.call_args.kwargs['headers'] == {'Referer': url}
