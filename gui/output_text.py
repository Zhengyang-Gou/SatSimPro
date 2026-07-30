"""Decode and clean text received from external commands."""

from __future__ import annotations

import locale
import re
import unicodedata
from typing import Union


_ANSI_ESCAPE_RE = re.compile(
    rb"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[@-_][0-?]*[ -/]*[@-~])"
)
_ANSI_ESCAPE_TEXT_RE = re.compile(
    r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[@-_][0-?]*[ -/]*[@-~])"
)


def decode_external_output(value: Union[bytes, str, None]) -> str:
    """Decode command output without depending on the Windows console code page."""
    if value is None:
        return ""
    if isinstance(value, str):
        return sanitize_external_text(value)

    raw = _ANSI_ESCAPE_RE.sub(b"", value)
    encodings = ["utf-8", "gb18030"]
    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)

    for encoding in dict.fromkeys(encodings):
        try:
            return sanitize_external_text(raw.decode(encoding))
        except (LookupError, UnicodeDecodeError):
            continue
    return sanitize_external_text(raw.decode("utf-8", errors="replace"))


def sanitize_external_text(value: object) -> str:
    """Remove terminal escapes and non-printing characters before GUI display."""
    text = _ANSI_ESCAPE_TEXT_RE.sub("", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    cleaned = "".join(
        character
        for character in text
        if character in "\n\t"
        or not unicodedata.category(character).startswith("C")
    )
    return "\n".join(line.rstrip() for line in cleaned.splitlines()).strip()
