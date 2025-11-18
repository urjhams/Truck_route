"""Helpers for resolving asset paths in dev and frozen bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_asset_path(name: str) -> Path:
    """Return the absolute path to an asset regardless of PyInstaller state."""
    # When running from source we want the TruckRouteApp package directory as the base,
    # not the repository root. The assets live in ``TruckRouteApp/assets`` so using
    # ``parents[1]`` (the package root) keeps the path consistent between dev and PyInstaller.
    package_root = Path(__file__).resolve().parents[1]
    base = Path(getattr(sys, "_MEIPASS", package_root))
    return base / "assets" / name


__all__ = ["resolve_asset_path"]
