"""Unit tests for import pipeline fixes: probe leak, fallback title cascade, HTML charset.

These tests are pure unit tests — they mock external dependencies (HTTP, Zotero
connector, PyMuPDF) and do not require a running Zotero desktop.
"""
from unittest.mock import MagicMock, patch

import pytest

# Tests import symbols from zotero_mcp.server lazily inside each test to avoid
# breaking collection when a symbol does not yet exist during incremental development.
