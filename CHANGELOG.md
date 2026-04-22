# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`zotero_attach_file_to_item`** — new public MCP tool that uploads a local
  file (PDF, DOCX, EPUB, etc.) from disk to Zotero as an `imported_file`
  attachment on an existing item. For PDFs, routes through the existing
  `_attach_pdf_bytes` cascade (Web API → Zotero local connector → recovery).
  Other file types use pyzotero's `attachment_simple` / `attachment_both`
  (the latter when a custom title is supplied). Fills a gap where no public
  tool existed to attach a file that was already on disk.
- **`zotero_attach_pdf_from_url`** — new public MCP tool that downloads a PDF
  from an arbitrary URL and attaches it to an existing Zotero item as an
  `imported_file` attachment. Thin wrapper over the internal
  `_attach_pdf_from_url` helper that already powers `add_items_by_*` imports
  (direct HTTP, Playwright fallback, Zotero local connector fast-path).
  Complements `zotero_add_linked_url_attachment` which only creates
  metadata-only `linked_url` attachments without downloading file content.

### Fixed

- **Import pipeline:** the connector probe is no longer called after a
  successful direct PDF download. Previously it ran as a "second attempt"
  via `/connector/saveItems` even when PyMuPDF extracted no DOI/arXiv/title,
  and its `finally`-block cleanup used `suppress(Exception)` — so if the
  local/web Zotero API sync delay broke the delete, items with titles like
  `zotero-mcp-pdf-probe-<uuid>` leaked into the collection. The connector
  remains the legitimate fallback in the `except`-branch when the direct
  download itself fails (auth cookies, CDN protection).
- **Fallback webpage title:** when importing a direct PDF URL without
  DOI/arXiv, the title is now built via a four-tier cascade: PDF XMP
  metadata → HTML landing-page `og:title` → HTTP `Content-Disposition`
  filename (RFC 5987 aware, only if distinct from URL filename) → URL
  filename. Previously the fallback went straight to `urlparse(url).path`
  filename, producing opaque titles like `abc123def4567890.pdf` for
  CDN-style URLs that use hash-style filenames.
- **HTML charset detection:** `_fetch_page_signals` now detects charset via
  HTTP `Content-Type` header → `<meta charset>` sniff → `charset_normalizer`
  → utf-8 fallback, instead of hardcoded utf-8. Extracted text fields
  (`title`, `description`, `abstract_note`, `venue`) now run through
  `html.unescape` to resolve HTML entities. Fixes mojibake for legacy CMSes
  that serve windows-1251 without a charset parameter in the HTTP header,
  and garbled text for UTF-8 sites that emit non-ASCII characters as
  numeric HTML entities.

### Infrastructure

- `_download_pdf_bytes` signature extended from `tuple[bytes, str]` to
  `tuple[bytes, str, dict[str, str]]` to surface HTTP response headers for
  the Content-Disposition title cascade. `_download_pdf_bytes_via_playwright`
  updated to match. Existing callers discard headers where not needed; test
  mocks updated.

### Notes

- All fixes and features are covered by unit tests in
  `tests/test_import_fixes.py` and `tests/test_attach_api.py`. No existing
  public MCP tool signatures change; two new tools are added alongside
  existing ones.

## [0.1.7] - 2026-03-16

### Changed
- Release refresh to re-run GitHub Actions tag publishing with a token that has `workflow` scope.

## [0.1.6] - 2026-03-16

### Fixed
- Updater: do not suggest downgrading when the local version is ahead of the latest PyPI release (common when installed from a fork or git URL).

## [0.1.5] - 2026-03-16

### Fixed
- Handle local Zotero API `/file` redirects to `file://...` when downloading attachments (fulltext and PDF-extraction annotations).
- Avoid crashing on import in some environments by lazily importing `markitdown`; add a lightweight PDF fallback conversion path.
- Make `import zotero_mcp` lightweight by lazily importing the server (`mcp`) only when requested.

## [0.1.3] - 2026-02-20

### Changed
- Published to PyPI as `zotero-mcp-server`. Install with `pip install zotero-mcp-server`.
- Updater now checks PyPI for latest versions (with GitHub releases as fallback).
- Updater now installs/upgrades from PyPI instead of git URLs.
- Install instructions updated to use PyPI in README and docs.

### Added
- PyPI badge in README.
- `keywords`, `license`, and additional `project.urls` metadata in package config.
- This changelog.

### Fixed
- Cleaned up `MANIFEST.in` (removed reference to nonexistent `setup.py`).

## [0.1.2] - 2026-01-07

### Added
- Full-text notes integration for semantic search.
- Extra citation key display support (Better BibTeX).

## [0.1.1] - 2025-12-29

### Added
- EPUB annotation support with CFI generation.
- Annotation feature documentation.
- Semantic search with ChromaDB and multiple embedding model support (default, OpenAI, Gemini).
- Smart update system with installation method detection.
- ChatGPT integration via SSE transport and tunneling.
- Cherry Studio and Chorus client configuration support.

## [0.1.0] - 2025-03-22

### Added
- Initial release.
- Zotero local and web API integration via pyzotero.
- MCP server with stdio transport.
- Claude Desktop auto-configuration (`zotero-mcp setup`).
- Search, metadata, full-text, collections, tags, and recent items tools.
- PDF annotation extraction with Better BibTeX support.
- Smithery and Docker support.
