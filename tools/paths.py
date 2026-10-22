"""Resolve mutable runtime paths without changing cwd or creating directories."""

import os
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def runtime_root(default=None):
    """Resolve RVC_DATA_DIR against the caller's cwd before any chdir."""
    return Path(os.environ.get("RVC_DATA_DIR", default or Path.cwd())).expanduser().resolve()


def runtime_path(value, root=None):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (runtime_root() if root is None else root) / path
    return path.resolve()


def weight_path(name):
    """Use the same configured weights directory as the WebUI."""
    root = runtime_path(os.environ.get("weight_root", "assets/weights"))
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
