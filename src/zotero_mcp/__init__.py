"""
Zotero MCP - Model Context Protocol server for Zotero

This module provides tools for AI assistants to interact with Zotero libraries.
"""

from __future__ import annotations

from typing import Any

from ._version import __version__

# These modules are not imported by default but are available
# pdfannots_helper and pdfannots_downloader

__all__ = ["__version__", "mcp"]


def __getattr__(name: str) -> Any:
    """
    Lazy attribute access.

    Importing the package should be lightweight. We only import the MCP server
    implementation (`fastmcp`, embedding stack, etc.) when `mcp` is actually
    requested.
    """
    if name == "mcp":
        from .server import mcp

        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
