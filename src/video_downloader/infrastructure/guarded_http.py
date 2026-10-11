"""Check each HTTP redirect before connecting to its destination."""
from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

from video_downloader.domain.errors import AppError, ErrorCode


def protect_session(session, ensure_public: Callable[[str], None]) -> None:
    original_request = session.request

    def guarded_request(method: str, url: str, **options):
        options = dict(options)
        options["allow_redirects"] = False
        for hop in range(6):
            ensure_public(url)
            response = original_request(method=method, url=url, **options)
            location = response.headers.get("Location")
            if response.status_code not in {301, 302, 303, 307, 308} or not location:
                return response
            try:
                destination = urljoin(url, location)
                ensure_public(destination)
                if hop == 5:
                    raise AppError(ErrorCode.NETWORK, "The source redirected too many times.")
                old_origin = urlsplit(url)
                new_origin = urlsplit(destination)
                if (old_origin.scheme, old_origin.hostname, old_origin.port) != (
                    new_origin.scheme, new_origin.hostname, new_origin.port
                ):
                    options["headers"] = {
                        name: value for name, value in (options.get("headers") or {}).items()
                        if name.lower() not in {"authorization", "cookie", "proxy-authorization"}
                    }
                if (response.status_code == 303 and method.upper() != "HEAD") or (
                    response.status_code in {301, 302} and method.upper() == "POST"
                ):
                    method = "GET"
                    options.pop("data", None)
                    options["headers"] = {
                        name: value for name, value in (options.get("headers") or {}).items()
                        if name.lower() not in {"content-type", "content-length", "transfer-encoding"}
                    }
                url = destination
            finally:
                response.close()
        raise AppError(ErrorCode.NETWORK, "The source redirected too many times.")

    session.request = guarded_request


def configure_guarded_transport(client, ensure_public: Callable[[str], None]) -> None:
    from yt_dlp.networking._curlcffi import CurlCFFIRH
    from yt_dlp.networking.exceptions import RequestError

    class GuardedCurlCFFIRH(CurlCFFIRH):
        def _create_instance(self, cookiejar=None):
            session = super()._create_instance(cookiejar)
            protect_session(session, ensure_public)
            return session

        def _send(self, request):
            try:
                return super()._send(request)
            except AppError as exc:
                # yt-dlp must not treat a blocked redirect as a broken handler
                # and try an alternative transport without the guard.
                raise RequestError(cause=exc) from exc

    # Keep TLS verification, proxy settings, session cookies and impersonation
    # configured by yt-dlp, but prevent unguarded automatic HTTP redirects.
    client._request_director.close()
    client._request_director = client.build_request_director([GuardedCurlCFFIRH])
