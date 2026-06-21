from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ytkiosk.deno import resolve_js_runtime

Check = tuple[str, str]


def _check_command(name: str, command: str, *, required: bool = True) -> Check:
    path = shutil.which(command)
    if not path:
        status = "missing" if required else "optional, not found"
        return (
            "FAIL" if required else "WARN",
            f"{name}: {status} ({command} not on PATH)",
        )

    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return (
            "FAIL" if required else "WARN",
            f"{name}: found at {path}, but failed to run: {exc}",
        )

    output = (result.stdout or result.stderr).strip().splitlines()
    version = output[0] if output else "version unknown"
    if result.returncode != 0:
        return (
            "FAIL" if required else "WARN",
            f"{name}: {path} returned {result.returncode}: {version}",
        )
    return "OK", f"{name}: {path} ({version})"


def _check_import(name: str, module: str, *, required: bool = True) -> Check:
    found = importlib.util.find_spec(module) is not None
    if found:
        return "OK", f"{name}: available"
    status = "missing" if required else "optional, not installed"
    return "FAIL" if required else "WARN", f"{name}: {status} ({module})"


def _check_directory(name: str, path: Path) -> Check:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        test_file = path / ".ytkiosk-write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
    except Exception as exc:
        return "FAIL", f"{name}: not writable at {path}: {exc}"
    return "OK", f"{name}: writable at {path}"


def _parse_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups(default="0"))


def _check_mpv() -> Check:
    status, message = _check_command("mpv", "mpv")
    if status != "OK":
        return status, message
    version = _parse_version(message)
    if version is not None and version < (0, 37, 0):
        return "WARN", f"{message} - recommended mpv >= 0.37"
    return status, message


def _check_js_runtime() -> Check:
    runtime = resolve_js_runtime()
    if runtime is None:
        return (
            "WARN",
            "JavaScript runtime: optional, not found; install Deno, Node 22+, "
            "or QuickJS if yt-dlp reports YouTube extraction failures",
        )

    try:
        result = subprocess.run(
            [str(runtime.path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return (
            "WARN",
            f"JavaScript runtime: {runtime.name} at {runtime.path} failed: {exc}",
        )

    output = (result.stdout or result.stderr).strip().splitlines()
    version = output[0] if output else "version unknown"
    if result.returncode != 0:
        return (
            "WARN",
            f"JavaScript runtime: {runtime.name} at {runtime.path} returned "
            f"{result.returncode}: {version}",
        )
    if runtime.name == "deno":
        parsed = _parse_version(version)
        if parsed is not None and parsed < (2, 3, 0):
            return (
                "WARN",
                f"JavaScript runtime: {runtime.name} at {runtime.path} "
                f"({version}) - recommended Deno >= 2.3",
            )
    return "OK", f"JavaScript runtime: {runtime.name} at {runtime.path} ({version})"


def _display_checks() -> list[Check]:
    display = os.environ.get("DISPLAY")
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()

    checks: list[Check] = [
        ("OK" if display else "WARN", f"DISPLAY: {display or 'not set'}"),
        (
            "OK" if wayland_display else "WARN",
            f"WAYLAND_DISPLAY: {wayland_display or 'not set'}",
        ),
        ("OK", f"session: {session_type}"),
    ]

    if display:
        if session_type == "wayland":
            checks.append(
                (
                    "WARN",
                    "embedding: X11/XWayland DISPLAY is available; native Wayland "
                    "embedding is not supported",
                )
            )
        else:
            checks.append(("OK", "embedding: X11/XWayland path available"))
    elif wayland_display:
        checks.append(
            (
                "WARN",
                "embedding: native Wayland detected without DISPLAY; YTKiosk will "
                "use standalone fullscreen mpv fallback if Tk can start",
            )
        )
    else:
        checks.append(("WARN", "display: no DISPLAY or WAYLAND_DISPLAY in this shell"))
    return checks


def run_checks() -> list[Check]:
    runtime_dir = Path(
        os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    ) / f"yt-player-{os.getuid()}"
    config_dir = Path.home() / ".config" / "yt-player"

    checks: list[Check] = [
        (
            "OK" if sys.version_info >= (3, 11) else "FAIL",
            f"python: {sys.version.split()[0]} "
            f"({'ok' if sys.version_info >= (3, 11) else 'requires >=3.11'})",
        ),
        (
            "OK" if sys.platform.startswith("linux") else "FAIL",
            f"platform: {sys.platform} (Linux required)",
        ),
        _check_import("tkinter", "tkinter"),
        _check_import("yt-dlp Python package", "yt_dlp"),
        _check_mpv(),
        _check_command("xset", "xset", required=False),
        _check_command("xdg-open", "xdg-open", required=False),
        _check_command("pactl", "pactl", required=False),
        _check_directory("config dir", config_dir),
        _check_directory("runtime dir", runtime_dir),
        _check_js_runtime(),
    ]
    checks.extend(_display_checks())
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check YTKiosk runtime dependencies.")
    parser.parse_args(argv)

    checks = run_checks()
    for status, message in checks:
        print(f"{status}: {message}")

    return 1 if any(status == "FAIL" for status, _ in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
