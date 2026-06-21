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
the Python app, Python dependencies, and an optional JavaScript runtime sidecar
when needed. `mpv` remains a system dependency installed by the distro package
manager.

The one-line installer is user-space first. It installs `uv`, creates a venv at
`~/.local/share/ytkiosk/venv`, installs YTKiosk and `yt-dlp[default]` into that
venv, and writes wrappers to `~/.local/bin`. It only uses `sudo apt` when
required system components such as `mpv` or `python3-tk` are missing. Deno is
optional and only installed by the script when `YTKIOSK_INSTALL_DENO=1` is set.
It installs YTKiosk from a GitHub source tarball instead of `git+https`, so it
does not depend on Git or Git's HTTPS remote helper.

## Dependency Decisions

| Dependency | Decision | Reason |
|---|---|---|
| Python 3.11+ | Required | Supported baseline for packaging and typing. |
| tkinter | System dependency | Debian/Ubuntu package this as `python3-tk`; it is not a normal PyPI dependency. |
| `yt-dlp[default]` | Managed Python dependency | Avoid stale distro packages and `/usr/local/bin` assumptions while installing yt-dlp's default extractor support. |
| Deno / Node / QuickJS | Optional runtime | Recommended for modern yt-dlp JavaScript extraction paths. Discovery supports `YTKIOSK_DENO`, future `ytkiosk/bin/deno`, PATH runtimes, `~/.deno/bin/deno`, and `/usr/local/bin/deno`. |
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
tkinter availability, `yt_dlp`, `mpv`, JavaScript runtime discovery, optional
desktop tools, X11/Wayland display environment, and writable config/runtime
directories. It prints `OK`, `WARN`, or `FAIL`; only `FAIL` makes the command
return non-zero.

## JavaScript Runtime Discovery

Runtime discovery order is:

1. configured path, once config support is wired into the package
2. `YTKIOSK_DENO`
3. packaged `ytkiosk/bin/deno`
4. Deno on `PATH`
5. `~/.deno/bin/deno`
6. `/usr/local/bin/deno`
7. Node on `PATH` (`node` or `nodejs`)
8. QuickJS on `PATH` (`qjs`, `quickjs`, or `qjs-ng`)
9. Bun on `PATH` as a last resort

When a runtime is detected, YTKiosk passes an explicit runtime argument to
playlist search and to mpv's yt-dlp hook:

```bash
--js-runtimes deno:/path/to/deno
--ytdl-raw-options=js-runtimes=deno:/path/to/deno
```

Missing runtime is a warning because yt-dlp can still work for many operations,
but full YouTube extraction is more reliable with a current runtime.

## X11, XWayland, And Wayland

Embedded playback uses Tk's native window ID and `mpv --wid`, which is an
X11/XWayland path. Linux Mint XFCE/Xorg remains the recommended kiosk session.
On a Wayland desktop, embedded playback works only when Tk is using XWayland and
`DISPLAY` is available. Native Wayland sessions fall back to standalone
fullscreen mpv controlled by the same IPC socket.

`ytkiosk-doctor` reports `DISPLAY`, `WAYLAND_DISPLAY`, session type, and whether
the X11/XWayland embedding path is available.

## Debian/Mint System Packages

Recommended baseline for current script usage:

```bash
sudo apt install -y python3 python3-tk mpv xdg-utils x11-xserver-utils
```

`xset` comes from `x11-xserver-utils`; `xdg-open` comes from `xdg-utils`.
Both are optional for core playback.

## Update And Uninstall

Rerunning `install.sh` updates the app by recreating the venv and refreshing
YTKiosk-managed wrappers. Saved keywords and state in `~/.config/yt-player` are
preserved.

To remove the user-space install:

```bash
rm -f ~/.local/bin/ytkiosk ~/.local/bin/ytkiosk-doctor ~/.local/bin/ytkiosk-cli ~/.local/bin/ytkiosk-yt-dlp
rm -rf ~/.local/share/ytkiosk
```

Remove `~/.local/bin/yt-dlp` only if it contains `YTKiosk managed yt-dlp wrapper`;
otherwise it may belong to the user or another application.

Remove `~/.config/yt-player` separately only if saved keywords/state should be
deleted.

## Captive Portals

When normal connectivity checks discover a portal URL, YTKiosk tries that URL
first and shows the exact page currently being attempted in the dialog. If no
portal URL is discovered after repeated attempts, it falls back to plain HTTP
trigger URLs such as `http://1.1.1.1/` and `http://neverssl.com/`, which are
often intercepted by hospital, hotel, and public WiFi captive portals. YTKiosk
attempts best-effort in-app auto-accept by submitting forms with common
accept/agree/continue/connect buttons, preserving cookies and following the
portal page's form method. The dialog shows each URL it is trying and retries
in-app instead of automatically opening an external browser.

If automatic acceptance cannot complete, the dialog provides an **Open portal**
button for a caregiver to open the discovered sign-in page manually. This is
still required for portals with passwords, room numbers, payments, CAPTCHA,
OAuth/SAML, JavaScript-generated forms, or other browser-only flows. YTKiosk
does not fill credentials or payment details automatically.
