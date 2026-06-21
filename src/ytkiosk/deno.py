from __future__ import annotations

import os
import shutil
import sys
from contextlib import suppress
from importlib import resources
from pathlib import Path


def bundled_deno_path() -> Path | None:
    """Return a packaged Deno sidecar path if one is present and executable."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "bin" / "deno")

    with suppress(FileNotFoundError, ModuleNotFoundError):
        candidates.append(resources.files("ytkiosk").joinpath("bin", "deno"))

    for candidate in candidates:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def resolve_deno(configured_path: str | None = None) -> Path | None:
    """Resolve Deno using config, environment, bundled sidecar, then PATH."""
    candidates = [configured_path, os.environ.get("YTKIOSK_DENO")]
    for value in candidates:
        if value:
            path = Path(value).expanduser()
            if path.is_file() and os.access(path, os.X_OK):
                return path

    bundled = bundled_deno_path()
    if bundled is not None:
        return bundled

    found = shutil.which("deno") or "/usr/local/bin/deno"
    path = Path(found)
    if path.is_file() and os.access(path, os.X_OK):
        return path
    return None


def yt_dlp_js_runtime_arg(deno_path: Path | None = None) -> list[str]:
    """Return yt-dlp CLI args that force the resolved Deno runtime, if present."""
    resolved = deno_path or resolve_deno()
    if resolved is None:
        return []
    return ["--js-runtimes", f"deno:{resolved}"]
