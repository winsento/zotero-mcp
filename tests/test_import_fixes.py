"""Unit tests for import pipeline fixes: probe leak, fallback title cascade, HTML charset.

These tests are pure unit tests — they mock external dependencies (HTTP, Zotero
connector, PyMuPDF) and do not require a running Zotero desktop. Follow the same
style as tests/test_write_tools_creation.py: use monkeypatch + shared conftest
fixtures (ctx, patch_web_client), and mock at the requests/server boundary
rather than patching private closures directly.
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
            lambda pdf_url, *, ctx=None: (PDF_BYTES_FIXTURE, "application/pdf"),
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
