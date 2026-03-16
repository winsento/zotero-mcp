from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _StubResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes = b""


class _StubHttpxClient:
    def __init__(self, response: _StubResponse):
        self._response = response

    def get(self, *_args, **_kwargs) -> _StubResponse:
        return self._response


class _StubCtx:
    def __init__(self):
        self.messages: list[str] = []

    def info(self, msg: str) -> None:
        self.messages.append(msg)


class _StubZot:
    def __init__(self, *, endpoint: str, library_type: str, library_id: str):
        self.endpoint = endpoint
        self.library_type = library_type
        self.library_id = library_id

    def default_headers(self) -> dict[str, str]:
        return {}

    def dump(self, *_args, **_kwargs) -> None:
        raise RuntimeError("Request URL has an unsupported protocol 'file://'.")


def test_dump_attachment_to_file_resolves_file_redirect(tmp_path: Path, monkeypatch) -> None:
    from zotero_mcp import server

    payload = b"%PDF-stub"
    local = tmp_path / "paper.pdf"
    local.write_bytes(payload)

    # http://.../file -> 302 Location: file://...
    location = "file://" + str(local)
    response = _StubResponse(status_code=302, headers={"Location": location})

    monkeypatch.setattr(server.httpx, "Client", lambda *a, **k: _StubHttpxClient(response))

    dest = tmp_path / "out.pdf"
    server.dump_attachment_to_file(
        _StubZot(endpoint="http://localhost:23119/api", library_type="users", library_id="1"),
        "ATTACHKEY",
        dest,
        ctx=_StubCtx(),
    )

    assert dest.read_bytes() == payload


def test_dump_attachment_to_file_accepts_inline_200_bytes(tmp_path: Path, monkeypatch) -> None:
    from zotero_mcp import server

    payload = b"%PDF-inline"
    response = _StubResponse(status_code=200, headers={}, content=payload)
    monkeypatch.setattr(server.httpx, "Client", lambda *a, **k: _StubHttpxClient(response))

    dest = tmp_path / "out.pdf"
    server.dump_attachment_to_file(
        _StubZot(endpoint="http://localhost:23119/api", library_type="users", library_id="1"),
        "ATTACHKEY",
        dest,
        ctx=_StubCtx(),
    )

    assert dest.read_bytes() == payload

