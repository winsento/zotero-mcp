"""Unit tests for public attachment API — attach_file_to_item, attach_pdf_from_url.

Style matches tests/test_write_tools_creation.py: monkeypatch + shared
conftest fixtures (ctx), mock at the module/pyzotero boundary.
"""
import pytest

import zotero_mcp.server as server


class TestAttachFileToItem:
    def test_pdf_routes_through_attach_pdf_bytes(self, tmp_path, monkeypatch, ctx):
        pdf = tmp_path / "paper.pdf"
        pdf.write_bytes(b"%PDF-1.4\nfake")

        captured = {}

        def fake_attach(zot, item_key, pdf_bytes, *, filename, ctx, source):
            captured["item_key"] = item_key
            captured["filename"] = filename
            captured["source"] = source
            captured["bytes_len"] = len(pdf_bytes)
            return {
                "success": True,
                "pdf_source": "user_local_file:paper.pdf",
                "message": "PDF attached from user_local_file:paper.pdf",
            }

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: object())
        monkeypatch.setattr(server, "_attach_pdf_bytes", fake_attach)

        result = server.attach_file_to_item(
            item_key="ABC123",
            file_path=str(pdf),
            ctx=ctx,
        )

        assert captured["item_key"] == "ABC123"
        assert captured["filename"] == "paper.pdf"
        assert captured["source"] == "user_local_file:paper.pdf"
        assert captured["bytes_len"] > 0
        assert "✓" in result and "ABC123" in result

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
    def test_delegates_to_private_helper(self, monkeypatch, ctx):
        captured = {}

        def fake_attach(zot, item_key, url, *, ctx, source):
            captured["item_key"] = item_key
            captured["url"] = url
            captured["source"] = source
            return {
                "success": True,
                "pdf_source": f"user_url:{url}",
                "message": f"PDF attached from user_url:{url}",
            }

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: object())
        monkeypatch.setattr(server, "_attach_pdf_from_url", fake_attach)

        result = server.attach_pdf_from_url(
            item_key="ABC123",
            url="http://example.org/paper.pdf",
            ctx=ctx,
        )

        assert captured["item_key"] == "ABC123"
        assert captured["url"] == "http://example.org/paper.pdf"
        assert captured["source"] == "user_url:http://example.org/paper.pdf"
        assert "✓" in result and "ABC123" in result

    def test_propagates_failure_message(self, monkeypatch, ctx):
        def fake_attach(zot, item_key, url, *, ctx, source):
            return {
                "success": False,
                "pdf_source": f"user_url:{url}",
                "message": "download failed: 403 Forbidden",
            }

        monkeypatch.setattr(server, "get_web_zotero_client", lambda: object())
        monkeypatch.setattr(server, "_attach_pdf_from_url", fake_attach)

        result = server.attach_pdf_from_url(
            item_key="ABC123",
            url="http://protected.example/paper.pdf",
            ctx=ctx,
        )

        assert "✗" in result
        assert "403" in result

    def test_no_web_client_returns_error(self, monkeypatch, ctx):
        monkeypatch.setattr(server, "get_web_zotero_client", lambda: None)
        result = server.attach_pdf_from_url(
            item_key="ABC123",
            url="http://example.com/x.pdf",
            ctx=ctx,
        )
        assert "Web API credentials" in result
