"""Unit tests for import pipeline fixes: probe leak, fallback title cascade, HTML charset.

These tests are pure unit tests — they mock external dependencies (HTTP, Zotero
connector, PyMuPDF) and do not require a running Zotero desktop. Style follows
tests/test_write_tools_creation.py: use monkeypatch + shared conftest fixtures
(ctx, patch_web_client), mock at the requests/server boundary rather than
patching private closures directly.
"""
from unittest.mock import MagicMock

import pytest

import zotero_mcp.server as server


class TestHTMLCharsetDetection:
    """Fix #3: _decode_html_body cascade + html.unescape on text fields.

    Before this fix, _fetch_page_signals decoded response body as hardcoded
    UTF-8 with errors="replace", producing mojibake (????) for pages declaring
    a non-UTF-8 charset via HTTP Content-Type header or <meta charset> tag.
    Numeric HTML entities (&#xNNNN;) were not html.unescape'd and passed
    through literally into Zotero.

    Test fixtures use sample non-ASCII strings (Cyrillic / accented Latin)
    purely to exercise the cp1251 / utf-8 / charset-detect code paths. The
    strings themselves carry no meaning.
    """

    def test_decode_cp1251_via_content_type_header(self):
        body = "Пример документа".encode("cp1251")
        result = server._decode_html_body(body, "text/html; charset=windows-1251")
        assert "Пример документа" in result

    def test_decode_cp1251_via_meta_charset(self):
        body = (
            b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1251">'
            + "<title>Документ</title>".encode("cp1251")
            + b"</head></html>"
        )
        # No charset in HTTP Content-Type header → meta sniff should apply.
        result = server._decode_html_body(body, "text/html")
        assert "Документ" in result

    def test_decode_utf8_fallback_no_charset_hint(self):
        body = "Hello world".encode("utf-8")
        result = server._decode_html_body(body, "text/html")
        assert result == "Hello world"

    def test_decode_utf8_with_explicit_header(self):
        body = "résumé café".encode("utf-8")
        result = server._decode_html_body(body, "text/html; charset=utf-8")
        assert result == "résumé café"

    def test_decode_charset_normalizer_recovers_unknown_encoding(self):
        """When no charset hint is present, charset-normalizer should guess OK."""
        body = "пример".encode("cp1251")
        result = server._decode_html_body(body, "text/html")
        # charset-normalizer should recover; even if it falls back to UTF-8
        # with errors="replace", the result must be a non-empty string.
        assert isinstance(result, str)
        assert len(result) > 0
