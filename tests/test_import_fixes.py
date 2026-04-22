"""Unit tests for import pipeline fixes: probe leak, fallback title cascade, HTML charset.

These tests are pure unit tests — they mock external dependencies (HTTP, Zotero
connector, PyMuPDF) and do not require a running Zotero desktop. Style follows
tests/test_write_tools_creation.py: use monkeypatch + shared conftest fixtures
(ctx, patch_web_client), and mock at the requests/server boundary rather than
patching private closures directly.
"""
import sys
import types

import pytest

import zotero_mcp.server as server


PDF_BYTES_FIXTURE = b"%PDF-1.4\nfake pdf content"


class _UninformativeFakeDoc:
    """PyMuPDF doc with empty metadata and no page text — simulates a PDF
    whose XMP contains nothing useful (no DOI/arXiv/title)."""

    metadata = {"title": "", "author": ""}

    def __len__(self):
        return 0

    def load_page(self, _page_index):
        raise IndexError("no pages")

    def close(self):
        pass


class TestProbeLeakFix:
    """Fix #1: connector probe must not be called after successful direct download.

    Before this fix, `_probe_identifier_from_direct_pdf_url` called
    `_probe_via_local_connector` as a "second attempt" even when the direct
    download succeeded but PyMuPDF found no DOI/arXiv/title. The connector
    would create a temporary Zotero item via `/connector/saveItems`, and its
    cleanup in the finally block used `suppress(Exception)`, which silently
    dropped sync-delay errors — leaking probe items
    (titles like `zotero-mcp-pdf-probe-<uuid>`) into collections.
    """

    def test_successful_direct_download_skips_connector_probe(
        self, monkeypatch, patch_web_client, ctx
    ):
        """After a successful direct download yielding no DOI/arXiv/title,
        no POST to /connector/saveItems must be made."""
        connector_hits = {"save_items": 0, "save_attachment": 0}

        def forbidden_post(url, json=None, params=None, data=None, headers=None, timeout=None):
            if url.endswith("/connector/saveItems"):
                connector_hits["save_items"] += 1
            if url.endswith("/connector/saveAttachment"):
                connector_hits["save_attachment"] += 1
            raise AssertionError(
                f"connector endpoint should not be called on success path: {url}"
            )

        monkeypatch.setattr(
            server,
            "_download_pdf_bytes",
            lambda pdf_url, *, ctx=None: (PDF_BYTES_FIXTURE, "application/pdf", {}),
        )
        monkeypatch.setattr(server.requests, "post", forbidden_post)
        monkeypatch.setitem(
            sys.modules,
            "fitz",
            types.SimpleNamespace(open=lambda stream, filetype: _UninformativeFakeDoc()),
        )

        result = server._probe_identifier_from_direct_pdf_url(
            "https://example.com/test.pdf", ctx=ctx
        )

        # Evidence that the connector closure was never entered: the
        # forbidden-post did not fire and counters stayed at zero.
        assert connector_hits["save_items"] == 0
        assert connector_hits["save_attachment"] == 0
        # The function should return the signals dict (possibly empty of
        # identifiers) so the caller's fallback title cascade can read
        # pdf_signals.get("title") etc. in subsequent fixes.
        assert isinstance(result, dict)

    def test_failed_direct_download_still_uses_connector_fallback(
        self, monkeypatch, patch_web_client, ctx
    ):
        """When the direct download raises, the except-branch must still
        invoke the connector probe as a legitimate fallback."""
        connector_hits = {"save_items": 0}

        def fake_post(url, json=None, params=None, data=None, headers=None, timeout=None):
            if url.endswith("/connector/saveItems"):
                connector_hits["save_items"] += 1
                raise RuntimeError("simulated: connector endpoint is also down in this test")
            raise AssertionError(f"unexpected POST: {url}")

        class _FakeLocalZot:
            client = object()

            def items(self, **_kw):
                return []

        monkeypatch.setattr(
            server,
            "_download_pdf_bytes",
            lambda pdf_url, *, ctx=None: (_ for _ in ()).throw(
                RuntimeError("simulated 403 Forbidden on direct download")
            ),
        )
        monkeypatch.setattr(server, "get_local_zotero_client", lambda: _FakeLocalZot())
        monkeypatch.setattr(server.requests, "post", fake_post)

        result = server._probe_identifier_from_direct_pdf_url(
            "https://example.com/test.pdf", ctx=ctx
        )

        assert connector_hits["save_items"] == 1, (
            "except-branch should have tried the connector exactly once"
        )
        assert result is None  # connector also failed → probe returns None


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

    # ----- cascade: _build_direct_pdf_fallback_title -----

    def test_cascade_xmp_title_wins(self, ctx):
        signals = {"title": "Official XMP Title"}
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/files/abc.pdf",
            signals,
            None,
            ctx=ctx,
        )
        assert title == "Official XMP Title"

    def test_cascade_landing_page_fallback_when_xmp_empty(self, monkeypatch, ctx):
        signals = {"title": None}
        monkeypatch.setattr(
            server,
            "_fetch_page_signals",
            lambda url, *, ctx: {"title": "From HTML Landing Page"},
        )
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/docs/2018/doc.pdf",
            signals,
            None,
            ctx=ctx,
        )
        assert title == "From HTML Landing Page"

    def test_cascade_content_disposition_fallback(self, monkeypatch, ctx):
        signals = {"title": None}
        headers = {
            "Content-Disposition": "attachment; filename*=UTF-8''%C3%A4bc.pdf",
        }
        monkeypatch.setattr(
            server,
            "_fetch_page_signals",
            lambda url, *, ctx: (_ for _ in ()).throw(RuntimeError("no landing page")),
        )
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/files/hash123.pdf",
            signals,
            headers,
            ctx=ctx,
        )
        assert title == "äbc.pdf"

    def test_cascade_content_disposition_skipped_if_same_as_url_filename(
        self, monkeypatch, ctx
    ):
        """If Content-Disposition filename matches URL filename, skip it (no new info)."""
        signals = {"title": None}
        headers = {"Content-Disposition": 'attachment; filename="abc.pdf"'}
        monkeypatch.setattr(
            server,
            "_fetch_page_signals",
            lambda url, *, ctx: (_ for _ in ()).throw(RuntimeError("no landing page")),
        )
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/files/abc.pdf",
            signals,
            headers,
            ctx=ctx,
        )
        assert title == "abc.pdf"  # from URL filename fallback, not from CD

    def test_cascade_url_filename_final_fallback(self, monkeypatch, ctx):
        signals = {"title": None}
        monkeypatch.setattr(
            server,
            "_fetch_page_signals",
            lambda url, *, ctx: (_ for _ in ()).throw(RuntimeError("no landing page")),
        )
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/files/abc.pdf",
            signals,
            None,
            ctx=ctx,
        )
        assert title == "abc.pdf"

    def test_cascade_handles_none_signals(self, monkeypatch, ctx):
        monkeypatch.setattr(
            server,
            "_fetch_page_signals",
            lambda url, *, ctx: (_ for _ in ()).throw(RuntimeError("no landing page")),
        )
        title = server._build_direct_pdf_fallback_title(
            "https://gov.example/files/abc.pdf",
            None,
            None,
            ctx=ctx,
        )
        assert title == "abc.pdf"
