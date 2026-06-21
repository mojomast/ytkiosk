# YTKiosk — Give Old Computers a New Purpose

**A fullscreen YouTube kiosk for hospital patients, elderly care residents, and anyone who needs simple, hands-off entertainment — running on hardware that would otherwise end up in a landfill.**

Millions of laptops and desktops get thrown away every year. Most of them still work. YTKiosk turns those machines into something meaningful: a dedicated video player that a nurse can hand to a patient without a single explanation needed. Plug it into a TV, click a keyword, and it just plays. No accounts. No ads. No way to accidentally close it.

---

## Why This Exists

Hospital patients spend hours — sometimes days — staring at walls with nothing to do. Idle time in care settings has real effects on mood and recovery. At the same time, usable computers are being landfilled at scale because they're "too old" for modern software.

YTKiosk closes both gaps. A 10-year-old Core 2 Duo laptop with 2 GB of RAM runs this perfectly. No expensive hardware, no subscriptions, no IT contract required. A caregiver configures it once, and it runs indefinitely.

---

## Features

- **Fullscreen kiosk lockdown** — no window decorations, no Alt+F4, no Escape. Patients can't accidentally close it
- **mpv embedded inside the app** — no popup windows, one unified UI
- **Random long-form auto-queues** — fetches ~30 videos, filters out short clips (< 5 min) and livestreams, keeps the longest 20, shuffles them, plays them in sequence
- **Keyword-based browsing** — caregivers add/edit topics (e.g. "Nature documentaries", "Classic cars", "Animal compilations"). Each keyword generates a fresh random playlist
- **Large on-screen controls** — play/pause, skip, volume, stop, return to keywords. Sized for elderly users and touchscreens
- **Captive portal detection** — auto-detects and accepts hospital/hotel WiFi login pages, often without any user action
- **Persistent keywords** — saved to `~/.config/yt-player/keywords.json`, survives reboots
- **Password-protected Options** — small corner ⚙ menu controls title, keyword editing, and quitting; default password is `baloney`
- **Language, captions, audio, and favorites** — EN/FR toggle, CC toggle, audio-track cycling, and a personal favorites playlist
- **Auto-hide controls** — playback controls hide after inactivity unless pinned
- **Exit requires confirmation** — no accidental shutdowns

---

## How It Works

### For Patients
The app launches fullscreen. There's nothing to configure, nothing to break. Watch, pause, skip — that's it.

### For Caregivers
1. Launch the app (auto-starts on boot if configured)
2. Click a keyword → videos start playing automatically
3. Use the bottom bar to pause, skip, or adjust volume
4. Click **Mots-clés** to return to keyword selection
5. Click **QUITTER** → confirm to close

### Technical Flow
```
User clicks keyword
  │
  ├─► Check for captive portal → auto-accept if needed
  │
  ├─► yt-dlp ytsearch30:{keyword} --flat-playlist
  │     --match-filters "duration > 300 & !is_live"
  │     → Returns video IDs with durations
  │
  ├─► Sort by duration → keep longest 20 → shuffle randomly
  │
  ├─► Switch to video mode:
  │     X11/XWayland: show video frame → get X11 window ID → mpv --wid={ID}
  │     Native Wayland: launch standalone fullscreen mpv fallback
  │
  └─► mpv plays embedded when X11/XWayland is available
        Controls via IPC Unix socket in a private per-user runtime directory
```

---

## Requirements

- **OS:** Linux (tested on Linux Mint 22.3 XFCE, X11)
- **RAM:** 2–4 GB minimum
- **Python:** 3.11+ with tkinter (`python3-tk`)
- **mpv:** 0.37+ from apt is fine
- **yt-dlp:** Managed by the Python package in new installs with default extractor support; avoid stale distro packages
- **JavaScript runtime:** Optional but recommended for full YouTube extraction support. Deno is preferred when present; Node 22+ and QuickJS are also supported by yt-dlp.
- **Window system:** X11/Xorg is recommended for embedded playback. Native Wayland sessions use standalone fullscreen mpv fallback because `mpv --wid` is X11/XWayland-oriented.

### Install yt-dlp For Legacy Script Use

The apt version of yt-dlp is often outdated and can fail with HTTP 403 errors. Package installs use the PyPI `yt-dlp[default]` dependency inside the YTKiosk venv. If you run only the legacy script directly without installing the package, use a current upstream yt-dlp binary instead of apt:

```bash
sudo apt remove -y yt-dlp || true
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
/usr/local/bin/yt-dlp --version
```

### Optional JavaScript Runtime

New package installs include `yt-dlp[default]`, which provides yt-dlp's default extractor support. A local JavaScript runtime is still recommended for the most reliable YouTube signature extraction. Deno is the preferred low-maintenance choice; Node 22+ or QuickJS can also work.

```bash
curl -fsSL https://deno.land/install.sh | sh
~/.deno/bin/deno --version
```

---

## Installation

One-line install for Debian, Ubuntu, and Linux Mint:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mojomast/ytkiosk/main/install.sh?v=2026-06-21.5' | bash
```

The installer is user-space first: it installs `uv`, creates a dedicated venv in `~/.local/share/ytkiosk/venv`, installs YTKiosk and `yt-dlp[default]` there, and writes wrappers to `~/.local/bin`. It downloads YTKiosk as a source tarball, so it does not require Git. It only asks for `sudo` if required system components such as `mpv` or `python3-tk` are missing, because those cannot be reliably installed inside a Python venv. Optional helpers such as `xset`, `xdg-open`, `pactl`, and a JavaScript runtime are reported by `ytkiosk-doctor` but do not block install.

To also install Deno during the one-line install:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mojomast/ytkiosk/main/install.sh?v=2026-06-21.5' | YTKIOSK_INSTALL_DENO=1 bash
```

For a more auditable install, download `install.sh`, inspect it, then run it locally instead of piping directly to `bash`.

Manual install:

```bash
# System dependencies
sudo apt install python3 python3-tk mpv

# Clone and install the package
git clone https://github.com/mojomast/ytkiosk.git
cd ytkiosk
uv venv --python python3 .venv
uv pip install --python .venv/bin/python -e .
.venv/bin/ytkiosk-doctor
.venv/bin/ytkiosk
```

### Developer Package Install

The GUI implementation now lives in `src/ytkiosk/legacy.py` while the root
`simple-video-player.py` file remains as a compatibility launcher. The package
also provides helper commands and dependency checks:

```bash
uv pip install -e .
ytkiosk          # launch GUI
ytkiosk-doctor
ytkiosk-cli doctor
```

`ytkiosk-doctor` checks Linux platform support, Python, tkinter, `mpv`, the
Python `yt_dlp` package, JavaScript runtime discovery, optional desktop tools,
X11/Wayland display state, and writable config/runtime directories. It prints
`OK`, `WARN`, or `FAIL`; warnings do not make the command fail. It does not
launch the GUI.

### Update And Uninstall

To update a one-line install, rerun the installer. It recreates the venv and
refreshes YTKiosk-managed wrappers while preserving `~/.config/yt-player`.

To uninstall the app files:

```bash
rm -f ~/.local/bin/ytkiosk ~/.local/bin/ytkiosk-doctor ~/.local/bin/ytkiosk-cli ~/.local/bin/ytkiosk-yt-dlp
rm -rf ~/.local/share/ytkiosk
```

Remove `~/.local/bin/yt-dlp` only if it contains `YTKiosk managed yt-dlp wrapper`; otherwise it may be a user-managed yt-dlp install.

Only remove saved keywords/state if you no longer need them:

```bash
rm -rf ~/.config/yt-player
```

See `docs/DEPENDENCIES.md` for the Linux-only dependency strategy and
`docs/RELEASE.md` for the future bundle plan.

---

## Setup for a Hospital or Care Home

### Auto-start on Boot

```bash
mkdir -p ~/.config/autostart
cp yt-player.desktop ~/.config/autostart/
# If autostart cannot find ytkiosk, edit the desktop file to use:
# Exec=$HOME/.local/bin/ytkiosk
```

### Customizing Keywords

Use the ✎ button inside the app to edit keywords, or click **+ Ajouter un mot-clé** to add new ones. Keywords save automatically. Caregivers can disable keyword adding/editing from the password-protected **⚙ Options** menu. You can also edit `INITIAL_KEYWORDS` in `src/ytkiosk/legacy.py` to set the defaults for a fresh install.

### Translation

All UI strings live in the language dictionaries near the top of `src/ytkiosk/legacy.py`. Replace the values to translate to any language.

---

## Configuration

| Constant | Default | Description |
|---|---|---|
| `SEARCH_COUNT` | 30 | Videos fetched per search |
| `PLAYLIST_SIZE` | 20 | Videos in the auto-queue |
| `MIN_DURATION` | 300 | Minimum video length in seconds (5 min) |
| `CONFIG_DIR` | `~/.config/yt-player` | Where keywords and state are saved |
| `RUNTIME_DIR` | `$XDG_RUNTIME_DIR/yt-player-$UID` or `/tmp/yt-player-$UID` | Private runtime directory for logs and mpv IPC socket |
| `POST_PORTAL_SEARCH_RETRIES` | 3 | Initial search attempts after captive portal acceptance |
| `POST_PORTAL_RETRY_DELAY` | 5 | Seconds between post-portal search attempts |

User preferences in `~/.config/yt-player/config.json` are preserved across updates:
`language` (`"fr"` or `"en"`, default `"fr"`), `cc_enabled` (`true`/`false`),
`pin_controls` (`true`/`false`), `app_title`, `allow_keyword_changes`
(`true`/`false`, default `true`), and `options_password` (default `"baloney"`).
Favorites are stored separately in
`~/.config/yt-player/favorites.json` as video ID/title/duration/added timestamp entries.

Captive portal defaults are currently tuned for the CISSS Côte-Nord guest WiFi portal. The app tries `https://cisss-public.reg09.rtss.qc.ca/login.html` directly and does not use generic `1.1.1.1` / `neverssl.com` trigger URLs by default. The CISSS portal uses a Cisco-style JavaScript button; YTKiosk emulates that by posting `buttonClicked=4` and `redirect_url=<redirect query value>`, and posts back to the current portal URL when `switch_url` is absent. After portal acceptance, YTKiosk waits briefly for connectivity to settle and retries the first YouTube search before showing an error. To change this later, add `captive_portal_urls`, `enable_captive_portal_trigger_urls`, `post_portal_search_retries`, or `post_portal_retry_delay` to `~/.config/yt-player/config.json`.

Use the top-bar **Debug** button while testing captive portals. It opens a live log viewer showing detected portal URLs, selected form/action, submitted field names, HTTP status/final URL, and verification retries. The same log is written to `$XDG_RUNTIME_DIR/yt-player-$UID/yt-player.log` or `/tmp/yt-player-$UID/yt-player.log`.

`mpv` is intentionally not bundled. Future Linux release bundles may include
the Python app, Python dependencies, and an optional JavaScript runtime sidecar,
while continuing to use distro `mpv` for playback.

---

## Tech Stack

| Component | Role |
|---|---|
| Python 3.11+ + tkinter | UI |
| mpv | Video playback (embedded via X11/XWayland `--wid`, standalone fallback on native Wayland) |
| yt-dlp | YouTube search and metadata |
| Deno / Node / QuickJS | Optional JS runtime for yt-dlp signature extraction |
| X11 (Xorg) | Recommended window system for embedded playback |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Top Bar: [Aide] [Debug] [EN] [Épingler]        [⚙] │
├─────────────────────────────────────────────┤
│                                             │
│  Main Area (Keyword View / Video Embed)     │
│                                             │
├─────────────────────────────────────────────┤
│  ⏮ ▶ ⏭ CC Audio ♥ | Volume | Arrêter Mots-clés │
│  En cours: Video Title...                   │
└─────────────────────────────────────────────┘
```

---

## Running Tests

```bash
python3 test_app.py
xvfb-run -a python3 test_integration.py
```

`test_integration.py` creates Tk windows, so it needs a display. Use `xvfb-run` on headless systems.

---

## Known Limitations

- Native Wayland embedding is not supported by the current Tk + `mpv --wid` architecture. X11/Xorg or XWayland gives embedded playback; native Wayland falls back to standalone fullscreen mpv.
- Captive portal auto-accept works for simple "click agree" portals only
- Audio backend is detected at playback start; hot-plugged audio devices may require restarting playback
- Audio track cycling only changes tracks when the current video provides multiple audio tracks
- Subtitle availability depends on what YouTube/mpv can expose for the current video
- The Options password is stored in plain text in the per-user config file; it is a kiosk guardrail, not cryptographic security

---

## License

MIT — take it, deploy it, give it to a hospital, run it on whatever hardware you have.
