from __future__ import annotations

import unicodedata

# Directional formatting characters can make an untrusted title appear to contain
# different text (including a different-looking filename) than it actually does.
_BIDI_CONTROLS = frozenset(
    {
        "\u061c",  # Arabic Letter Mark
        "\u200e",  # Left-to-Right Mark
        "\u200f",  # Right-to-Left Mark
        "\u202a",  # Left-to-Right Embedding
        "\u202b",  # Right-to-Left Embedding
        "\u202c",  # Pop Directional Formatting
        "\u202d",  # Left-to-Right Override
        "\u202e",  # Right-to-Left Override
        "\u2066",  # Left-to-Right Isolate
        "\u2067",  # Right-to-Left Isolate
        "\u2068",  # First Strong Isolate
        "\u2069",  # Pop Directional Isolate
    }
)


def sanitize_display_text(value: str, *, fallback: str = "", max_length: int = 500) -> str:
    """Return single-line text safe for displaying untrusted source metadata."""

    normalized = unicodedata.normalize("NFC", str(value))
    cleaned = "".join(
        " " if character.isspace() else character
        for character in normalized
        if character not in _BIDI_CONTROLS
        and unicodedata.category(character) not in {"Cc", "Cs"}
    )
    compact = " ".join(cleaned.split())
    return compact[:max_length] or fallback
