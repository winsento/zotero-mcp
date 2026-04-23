"""Unit tests for public attachment API — attach_file_to_item, attach_pdf_from_url.

Style matches tests/test_write_tools_creation.py: monkeypatch + shared
conftest fixtures (ctx), mock at the module/pyzotero boundary.
"""
import pytest

import zotero_mcp.server as server


class TestAttachFileToItem:
    def test_pdf_attach_uses_attachment_simple_not_cascade(
        self, tmp_path, monkeypatch, ctx
    ):
        """PDF attach to an existing Zotero item must call pyzotero
        attachment_simple directly — NOT the _attach_pdf_bytes import cascade.

        The cascade is designed for `add_items_by_*` flows where it creates a
        new item + PDF; applying it to an existing user item can create a
        duplicate local item and trash the original via the
        `_promote_local_copy_over_original` recovery path.
        """
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake")

        calls = {"simple": [], "both": [], "cascade": 0}

        class _FakeZot:
            def attachment_simple(self_inner, files, parent_key):
                calls["simple"].append((tuple(files), parent_key))
                return {"successful": {"0": {"key": "ATT111"}}}

            def attachment_both(self_inner, pairs, parent_key):
                calls["both"].append((tuple(pairs), parent_key))
                return {"successful": {"0": {"key": "SHOULDNOTHAPPEN"}}}

        def fake_cascade(*args, **kwargs):
            calls["cascade"] += 1
            return {"success": True, "pdf_source": "SHOULDNOTHAPPEN", "message": ""}

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: _FakeZot())
        # If the code ever reaches the cascade path, the counter will
        # increment and the assertion below catches it.
        monkeypatch.setattr(server, "_attach_pdf_bytes", fake_cascade)

        result = server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(pdf),
            ctx=ctx,
        )

        assert calls["simple"] == [((str(pdf.resolve()),), "ABC123")]
        assert calls["both"] == []
        assert calls["cascade"] == 0, "PDF attach must bypass _attach_pdf_bytes cascade"
        assert "ATT111" in result

    def test_pdf_attach_does_not_trash_existing_item(
        self, tmp_path, monkeypatch, patch_web_client, ctx
    ):
        """End-to-end-style test with FakeWebZotero: an existing item must
        remain in the library after attach_file_to_item, never appear in
        deleted_items, and get its PDF as a child attachment."""
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake")

        # Seed an existing user item we will attach to.
        patch_web_client._items["USR001"] = {
            "data": {
                "key": "USR001",
                "itemType": "book",
                "title": "Existing user book",
                "collections": [],
            }
        }

        # Wrap FakeWebZotero.attachment_simple so it also returns a realistic
        # response dict (the conftest implementation is a void recorder).
        original_simple = patch_web_client.attachment_simple

        def simple_with_response(files, parent_key):
            original_simple(files, parent_key)
            return {"successful": {"0": {"key": "ATTUSR1"}}}

        monkeypatch.setattr(patch_web_client, "attachment_simple", simple_with_response)

        result = server.attach_file_to_item(
            item_key="USR001",
            file_path=str(pdf),
            ctx=ctx,
        )

        # Original item must still be in library (not trashed).
        assert "USR001" in patch_web_client._items
        assert all(
            (d.get("key") if isinstance(d, dict) else None) != "USR001"
            for d in patch_web_client.deleted_items
        ), "Original item was trashed by cascade recovery path — regression"
        # PDF attached to USR001 (recorded in FakeWebZotero.attached_files).
        assert any(parent == "USR001" for _, parent in patch_web_client.attached_files)
        assert "✓" in result and "USR001" in result

    def test_pdf_with_custom_title_uses_attachment_both(
        self, tmp_path, monkeypatch, ctx
    ):
        """PDF with custom title goes through attachment_both (same as non-PDF)."""
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake")

        calls = {"simple": [], "both": []}

        class _FakeZot:
            def attachment_simple(self_inner, files, parent_key):
                calls["simple"].append((tuple(files), parent_key))
                return {"successful": {"0": {"key": "SHOULDNOTHAPPEN"}}}

            def attachment_both(self_inner, pairs, parent_key):
                calls["both"].append((tuple(pairs), parent_key))
                return {"successful": {"0": {"key": "ATT222"}}}

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: _FakeZot())

        server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(pdf),
            title="My Paper",
            ctx=ctx,
        )

        assert calls["simple"] == []
        assert calls["both"] == [((("My Paper", str(pdf.resolve())),), "ABC123")]

    def test_non_pdf_routes_through_attachment_simple(
        self, tmp_path, monkeypatch, ctx
    ):
        docx = tmp_path / "notes.docx"
        docx.write_bytes(b"PK\x03\x04fake-docx")

        calls = {"simple": [], "both": []}

        class _FakeZot:
            def attachment_simple(self_inner, files, parent_key):
                calls["simple"].append((tuple(files), parent_key))
                return {"successful": {"0": {"key": "ATT456"}}}

            def attachment_both(self_inner, pairs, parent_key):
                calls["both"].append((tuple(pairs), parent_key))
                return {"successful": {"0": {"key": "SHOULDNOTHAPPEN"}}}

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: _FakeZot())

        result = server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(docx),
            ctx=ctx,
        )

        assert calls["simple"] == [((str(docx.resolve()),), "ABC123")]
        assert calls["both"] == []
        assert "ATT456" in result

    def test_non_pdf_with_custom_title_uses_attachment_both(
        self, tmp_path, monkeypatch, ctx
    ):
        docx = tmp_path / "notes.docx"
        docx.write_bytes(b"PK\x03\x04fake-docx")

        calls = {"simple": [], "both": []}

        class _FakeZot:
            def attachment_simple(self_inner, files, parent_key):
                calls["simple"].append((tuple(files), parent_key))
                return {"successful": {"0": {"key": "SHOULDNOTHAPPEN"}}}

            def attachment_both(self_inner, pairs, parent_key):
                calls["both"].append((tuple(pairs), parent_key))
                return {"successful": {"0": {"key": "ATT999"}}}

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: _FakeZot())

        server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(docx),
            title="My Notes",
            ctx=ctx,
        )

        assert calls["simple"] == []
        assert calls["both"] == [((("My Notes", str(docx.resolve())),), "ABC123")]

    def test_missing_file_returns_error(self, ctx):
        result = server.attach_file_to_item(
            item_key="ABC123",
            file_path="/nonexistent/file.pdf",
            ctx=ctx,
        )
        assert result.startswith("Error: file not found")

    def test_no_web_client_returns_error(self, tmp_path, monkeypatch, ctx):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        monkeypatch.setattr(server, "get_web_zotero_client", lambda: None)
        result = server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(pdf),
            ctx=ctx,
        )
        assert "Web API credentials" in result


class TestAttachPdfFromUrl:
    """attach_pdf_from_url must NOT route through `_attach_pdf_from_url`
    helper — that helper calls `_attach_pdf_bytes`, whose recovery path
    (`_promote_local_copy_over_original`) trashes the existing parent item
    that the caller asked us to attach to (same bug as fix.05 for
    attach_file_to_item, observed again on the URL path when M3MCXWKA was
    replaced by FEXMLSHV with the original in trash).

    Correct flow: download bytes via `_download_pdf_bytes` (safe HTTP +
    Playwright helper — no item manipulation), then call pyzotero
    `attachment_simple` directly. No cascade, no recovery.
    """

    _FAKE_PDF = b"%PDF-1.4\nfake downloaded bytes"

    def test_url_download_and_attach_uses_attachment_simple_not_cascade(
        self, monkeypatch, ctx
    ):
        """attach_pdf_from_url must call attachment_simple and never the
        _attach_pdf_from_url / _attach_pdf_bytes cascade."""
        calls = {"download": 0, "simple": [], "cascade": 0}

        def fake_download(url, *, ctx=None):
            calls["download"] += 1
            return (self._FAKE_PDF, "application/pdf", {})

        class _FakeZot:
            def attachment_simple(self_inner, files, parent_key):
                calls["simple"].append((tuple(files), parent_key))
                return {"successful": {"0": {"key": "URLATT1"}}}

            def attachment_both(self_inner, *args, **kwargs):
                return {"successful": {"0": {"key": "SHOULDNOTHAPPEN"}}}

        def fake_cascade(*args, **kwargs):
            calls["cascade"] += 1
            return {"success": True, "pdf_source": "SHOULDNOTHAPPEN", "message": ""}

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: _FakeZot())
        monkeypatch.setattr(server, "_download_pdf_bytes", fake_download)
        monkeypatch.setattr(server, "_attach_pdf_from_url", fake_cascade)

        result = server.attach_pdf_from_url(
            item_key="ABC123",
            url="http://example.org/paper.pdf",
            ctx=ctx,
        )

        assert calls["download"] == 1
        assert len(calls["simple"]) == 1
        _files, parent_key = calls["simple"][0]
        assert parent_key == "ABC123"
        assert calls["cascade"] == 0, (
            "URL attach must bypass _attach_pdf_from_url / _attach_pdf_bytes cascade"
        )
        assert "URLATT1" in result and "ABC123" in result

    def test_url_attach_does_not_trash_existing_item(
        self, monkeypatch, patch_web_client, ctx
    ):
        """End-to-end-style: existing user item stays in the library after
        attach_pdf_from_url, never appears in deleted_items."""
        patch_web_client._items["USRURL"] = {
            "data": {
                "key": "USRURL",
                "itemType": "book",
                "title": "Existing user book with URL attach",
                "collections": [],
            }
        }

        def fake_download(url, *, ctx=None):
            return (self._FAKE_PDF, "application/pdf", {})

        original_simple = patch_web_client.attachment_simple

        def simple_with_response(files, parent_key):
            original_simple(files, parent_key)
            return {"successful": {"0": {"key": "ATTURL1"}}}

        monkeypatch.setattr(server, "_download_pdf_bytes", fake_download)
        monkeypatch.setattr(patch_web_client, "attachment_simple", simple_with_response)

        result = server.attach_pdf_from_url(
            item_key="USRURL",
            url="http://example.org/paper.pdf",
            ctx=ctx,
        )

        assert "USRURL" in patch_web_client._items
        assert all(
            (d.get("key") if isinstance(d, dict) else None) != "USRURL"
            for d in patch_web_client.deleted_items
        ), "Original item was trashed by URL-attach cascade recovery — regression"
        assert any(parent == "USRURL" for _, parent in patch_web_client.attached_files)
        assert "✓" in result and "USRURL" in result

    def test_url_download_failure_propagates_without_item_change(
        self, monkeypatch, patch_web_client, ctx
    ):
        """If the download itself fails, the tool returns an error without
        touching the parent item (no cascade, no trash, no duplicate)."""
        patch_web_client._items["USRURL2"] = {
            "data": {"key": "USRURL2", "itemType": "book", "title": "Untouched"}
        }

        def failing_download(url, *, ctx=None):
            raise RuntimeError("HTTP 403 Forbidden")

        monkeypatch.setattr(server, "_download_pdf_bytes", failing_download)

        result = server.attach_pdf_from_url(
            item_key="USRURL2",
            url="http://protected.example/paper.pdf",
            ctx=ctx,
        )

        # Parent must stay untouched.
        assert "USRURL2" in patch_web_client._items
        assert all(
            (d.get("key") if isinstance(d, dict) else None) != "USRURL2"
            for d in patch_web_client.deleted_items
        )
        # No attach attempts were made.
        assert not any(parent == "USRURL2" for _, parent in patch_web_client.attached_files)
        # Error string propagates 403.
        assert "✗" in result or "Error" in result
        assert "403" in result

    def test_url_attach_no_web_client_returns_error(self, monkeypatch, ctx):
        monkeypatch.setattr(server, "get_web_zotero_client", lambda: None)
        result = server.attach_pdf_from_url(
            item_key="ABC123",
            url="http://example.com/x.pdf",
            ctx=ctx,
        )
        assert "Web API credentials" in result
