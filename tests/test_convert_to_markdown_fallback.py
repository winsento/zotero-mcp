from __future__ import annotations

import sys
import types
from pathlib import Path


def test_convert_to_markdown_pdf_fallback_when_markitdown_fails(
    tmp_path: Path, monkeypatch
) -> None:
    from zotero_mcp import client

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-stub")

    class _BadMarkItDown:
        def __init__(self, *_a, **_k):
            raise ImportError("markitdown init failed")

    bad_markitdown_mod = types.SimpleNamespace(MarkItDown=_BadMarkItDown)
    monkeypatch.setitem(sys.modules, "markitdown", bad_markitdown_mod)

    class _FakeDoc:
        def __iter__(self):
            return iter([types.SimpleNamespace(get_text=lambda *_: "PDF_FALLBACK_TEXT")])

        def close(self) -> None:
            return None

    fake_fitz_mod = types.SimpleNamespace(open=lambda *_a, **_k: _FakeDoc())
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz_mod)

    # The function should return the fallback text rather than an import error.
    out = client.convert_to_markdown(pdf_path)
    assert "PDF_FALLBACK_TEXT" in out
