# Dependency Strategy

YTKiosk is Linux-only. Windows support is intentionally out of scope because a
primary goal is to reuse older computers that cannot run Windows 11 well.

## Target Install Modes

For development:

```bash
uv pip install -e .
ytkiosk-doctor
```

For end users, the intended direction is a Linux release bundle that includes
the Python app, Python dependencies, and Deno when needed. `mpv` remains a
system dependency installed by the distro package manager.

## Dependency Decisions

| Dependency | Decision | Reason |
|---|---|---|
| Python 3.11+ | Required | Supported baseline for packaging and typing. |
| tkinter | System dependency | Debian/Ubuntu package this as `python3-tk`; it is not a normal PyPI dependency. |
| `yt-dlp` | Managed Python dependency | Avoid stale distro packages and `/usr/local/bin` assumptions. |
| Deno | Optional bundled sidecar | Needed by modern yt-dlp JavaScript extraction paths. Discovery supports `YTKIOSK_DENO` and future `ytkiosk/bin/deno`. |
| `mpv` | System dependency | Avoid redistributing GPL media stack and large native dependencies. |
| `xset` | Optional system tool | X11-only best effort; not required for app launch. |
| `xdg-open` | Optional system tool | Desktop integration helper; not useful to vendor. |

## Doctor Command

Run:

```bash
ytkiosk-doctor
ytkiosk-cli doctor
```

The doctor command does not launch the GUI. It checks Python, Linux platform,
tkinter availability, `yt_dlp`, `mpv`, Deno, optional desktop tools, display
environment, and writable config/runtime directories.

## Deno Sidecar Discovery

Runtime discovery order is:

1. configured path, once config support is wired into the package
2. `YTKIOSK_DENO`
3. packaged `ytkiosk/bin/deno`
4. `PATH`
5. `/usr/local/bin/deno`

When the monolith's playlist fetching is migrated, yt-dlp should receive an
explicit runtime argument like:

```bash
--js-runtimes deno:/path/to/deno
```

## Debian/Mint System Packages

Recommended baseline for current script usage:

```bash
sudo apt install -y python3 python3-tk mpv xdg-utils x11-xserver-utils
```

`xset` comes from `x11-xserver-utils`; `xdg-open` comes from `xdg-utils`.
Both are optional for core playback.
