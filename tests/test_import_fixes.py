"""Unit tests for import pipeline fixes: probe leak, fallback title cascade, HTML charset.

These tests are pure unit tests — they mock external dependencies (HTTP, Zotero
connector, PyMuPDF) and do not require a running Zotero desktop. Style follows
tests/test_write_tools_creation.py: use monkeypatch + shared conftest fixtures
(ctx, patch_web_client), mock at the requests/server boundary rather than
patching private closures directly.
"""
import sys
import types

import pytest

import zotero_mcp.server as server


class TestFallbackTitleCascade:
    """Fix #2: fallback title uses XMP → landing page → Content-Disposition → filename.

    Before this fix, add_items_by_identifier used Path(urlparse(url).path).name as
    the title for direct PDF URLs, ignoring PDF XMP metadata (already extracted by
    _extract_pdf_probe_signals) and HTTP Content-Disposition header. This resulted
    in opaque titles like 'abc123def4567890.pdf' for CDN-style URLs with
    hash-style filenames.
    """

    def test_guess_landing_page_for_deep_path(self):
        assert (
            server._guess_landing_page_url("https://gov.example/docs/2018/doc.pdf")
            == "https://gov.example/docs/2018/"
        )

    def test_guess_landing_page_strips_query_and_fragment(self):
        assert (
            server._guess_landing_page_url(
                "https://gov.example/docs/doc.pdf?ref=rss#section"
            )
            == "https://gov.example/docs/"
        )

    def test_guess_landing_page_returns_none_at_root(self):
        assert server._guess_landing_page_url("https://gov.example/doc.pdf") is None

    def test_guess_landing_page_returns_none_for_non_pdf(self):
        assert server._guess_landing_page_url("https://gov.example/index.html") is None
        assert server._guess_landing_page_url("https://gov.example/api/v1/items") is None

    def test_parse_content_disposition_rfc5987_utf8(self):
        # RFC 5987 encoded filename, UTF-8, non-ASCII characters (Latin-1 accents
        # used here are arbitrary — only the decode pathway is under test).
        header = "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9.pdf"
        assert server._parse_content_disposition_filename(header) == "résumé.pdf"

    def test_parse_content_disposition_plain_quoted(self):
        assert (
            server._parse_content_disposition_filename(
                'attachment; filename="report.pdf"'
            )
            == "report.pdf"
        )

    def test_parse_content_disposition_plain_unquoted(self):
        assert (
            server._parse_content_disposition_filename("inline; filename=report.pdf")
            == "report.pdf"
        )

    def test_parse_content_disposition_prefers_rfc5987_over_plain(self):
        # When both filename= and filename*= are present, RFC 5987 form wins.
        header = (
            'attachment; filename="fallback.pdf"; '
            "filename*=UTF-8''%C3%A4bc.pdf"
        )
        assert server._parse_content_disposition_filename(header) == "äbc.pdf"

    def test_parse_content_disposition_empty_or_missing(self):
        assert server._parse_content_disposition_filename("") is None
        assert server._parse_content_disposition_filename("inline") is None
        assert server._parse_content_disposition_filename("attachment") is None
