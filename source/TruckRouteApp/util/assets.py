"""Helpers for resolving asset paths in dev and frozen bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_asset_path(name: str) -> Path:
    """Return the absolute path to an asset regardless of PyInstaller state."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "assets" / name


__all__ = ["resolve_asset_path"]
