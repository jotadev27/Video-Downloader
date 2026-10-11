import unittest

from video_downloader.presentation.text_safety import sanitize_display_text


class TextSafetyTests(unittest.TestCase):
    def test_removes_bidi_overrides_and_control_characters(self) -> None:
        value = "Safe\u202egnp.exe\u202c\x00\n title"

        self.assertEqual(sanitize_display_text(value), "Safegnp.exe title")

    def test_compacts_whitespace_and_limits_length(self) -> None:
        self.assertEqual(sanitize_display_text("  one\t two  ", max_length=6), "one tw")

    def test_uses_fallback_for_empty_metadata(self) -> None:
        self.assertEqual(sanitize_display_text("\u202e\x00", fallback="Video"), "Video")


if __name__ == "__main__":
    unittest.main()
