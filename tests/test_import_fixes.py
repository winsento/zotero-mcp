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
