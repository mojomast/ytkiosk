from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ytkiosk.deno import resolve_deno

Check = tuple[bool, str]


def _check_command(name: str, command: str, *, required: bool = True) -> Check:
    path = shutil.which(command)
    if not path:
        status = "missing" if required else "optional, not found"
        return (not required, f"{name}: {status} ({command} not on PATH)")

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
            not required,
            f"{name}: found at {path}, but failed to run: {exc}",
        )

    output = (result.stdout or result.stderr).strip().splitlines()
    version = output[0] if output else "version unknown"
    if result.returncode != 0:
        return (
            not required,
            f"{name}: {path} returned {result.returncode}: {version}",
        )
    return True, f"{name}: {path} ({version})"


def _check_import(name: str, module: str, *, required: bool = True) -> Check:
    found = importlib.util.find_spec(module) is not None
    if found:
        return True, f"{name}: available"
    status = "missing" if required else "optional, not installed"
    return not required, f"{name}: {status} ({module})"


def _check_directory(name: str, path: Path) -> Check:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        test_file = path / ".ytkiosk-write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
    except Exception as exc:
        return False, f"{name}: not writable at {path}: {exc}"
    return True, f"{name}: writable at {path}"


def run_checks() -> list[Check]:
    runtime_dir = Path(
        os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    ) / f"yt-player-{os.getuid()}"
    config_dir = Path.home() / ".config" / "yt-player"
    deno = resolve_deno()

    checks: list[Check] = [
        (
            sys.version_info >= (3, 11),
            f"python: {sys.version.split()[0]} "
            f"({'ok' if sys.version_info >= (3, 11) else 'requires >=3.11'})",
        ),
        (
            sys.platform.startswith("linux"),
            f"platform: {sys.platform} (Linux required)",
        ),
        _check_import("tkinter", "tkinter"),
        _check_import("yt-dlp Python package", "yt_dlp"),
        _check_command("mpv", "mpv"),
        _check_command("xset", "xset", required=False),
        _check_command("xdg-open", "xdg-open", required=False),
        _check_command("pactl", "pactl", required=False),
        _check_directory("config dir", config_dir),
        _check_directory("runtime dir", runtime_dir),
    ]

    if deno is None:
        checks.append((False, "deno: missing (set YTKIOSK_DENO or bundle bin/deno)"))
    else:
        checks.append((True, f"deno: {deno}"))

    display = os.environ.get("DISPLAY")
    session_type = os.environ.get("XDG_SESSION_TYPE", "unknown")
    checks.append((bool(display), f"DISPLAY: {display or 'not set'}"))
    checks.append((True, f"session: {session_type}"))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check YTKiosk runtime dependencies.")
    parser.parse_args(argv)

    checks = run_checks()
    for ok, message in checks:
        print(f"{'OK' if ok else 'FAIL'}: {message}")

    return 0 if all(ok for ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
