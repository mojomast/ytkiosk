from __future__ import annotations

import os
import shutil
import sys
from contextlib import suppress
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass(frozen=True)
class JsRuntime:
    name: str
    path: Path

    @property
    def yt_dlp_value(self) -> str:
        return f"{self.name}:{self.path}"


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

    for value in (
        shutil.which("deno"),
        Path.home() / ".deno" / "bin" / "deno",
        "/usr/local/bin/deno",
    ):
        if value is None:
            continue
        path = Path(value)
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def _resolve_named_runtime(name: str, commands: tuple[str, ...]) -> JsRuntime | None:
    for command in commands:
        value = shutil.which(command)
        if value is None:
            continue
        path = Path(value)
        if path.is_file() and os.access(path, os.X_OK):
            return JsRuntime(name, path)
    return None


def resolve_js_runtime(configured_deno_path: str | None = None) -> JsRuntime | None:
    """Resolve a yt-dlp JavaScript runtime without making one mandatory."""
    deno = resolve_deno(configured_deno_path)
    if deno is not None:
        return JsRuntime("deno", deno)

    for name, commands in (
        ("node", ("node", "nodejs")),
        ("quickjs", ("qjs", "quickjs", "qjs-ng")),
        ("bun", ("bun",)),
    ):
        runtime = _resolve_named_runtime(name, commands)
        if runtime is not None:
            return runtime
    return None


def yt_dlp_js_runtime_arg(runtime: JsRuntime | Path | None = None) -> list[str]:
    """Return yt-dlp CLI args that force the resolved JS runtime, if present."""
    if isinstance(runtime, Path):
        runtime = JsRuntime("deno", runtime)
    resolved = runtime or resolve_js_runtime()
    if resolved is None:
        return []
    return ["--js-runtimes", resolved.yt_dlp_value]
