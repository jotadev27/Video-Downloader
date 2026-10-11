import socket
import unittest
from unittest.mock import patch

from video_downloader.domain.errors import AppError, ErrorCode
from video_downloader.infrastructure.network_guard import PublicNetworkGuard


class NetworkGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = PublicNetworkGuard()

    @staticmethod
    def _record(address: str):
        return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))

    def test_accepts_global_address(self) -> None:
        with patch("socket.getaddrinfo", return_value=[self._record("93.184.216.34")]):
            self.guard.ensure_public("https://example.com/video")

    def test_rejects_private_dns_resolution(self) -> None:
        with patch("socket.getaddrinfo", return_value=[self._record("192.168.1.20")]):
            with self.assertRaises(AppError) as raised:
                self.guard.ensure_public("https://public-looking.example/video")
        self.assertEqual(raised.exception.code, ErrorCode.INVALID_LINK)

    def test_rejects_mixed_public_and_private_resolution(self) -> None:
        records = [self._record("93.184.216.34"), self._record("127.0.0.1")]
        with patch("socket.getaddrinfo", return_value=records):
            with self.assertRaises(AppError) as raised:
                self.guard.ensure_public("https://mixed.example/video")
        self.assertEqual(raised.exception.code, ErrorCode.INVALID_LINK)

    def test_dns_failure_is_network_error(self) -> None:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("not found")):
            with self.assertRaises(AppError) as raised:
                self.guard.ensure_public("https://missing.example/video")
        self.assertEqual(raised.exception.code, ErrorCode.NETWORK)


if __name__ == "__main__":
    unittest.main()
