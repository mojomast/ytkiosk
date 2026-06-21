# Handoff: Lecteur Vidéo Simple (Kiosk Edition)

## Project Overview
Hospital-grade kiosk YouTube player for Linux Mint. Designed for elderly patients — a caregiver sets up keyword-based video streams and the patient watches full-screen with auto-queued random videos. No accounts, no browser, works on 2–4 GB RAM hardware.

## Current State — FULLY WORKING
- Fullscreen kiosk mode (no decorations, blocks Escape/Alt+F4)
- mpv **embedded inside** tkinter window (no separate popup)
- Click a keyword → searches YouTube → fetches **30 videos** → filters long (≥5 min) → picks **20 random long ones** → auto-plays in shuffled order
- On-screen controls: pause/next/prev/volume/stop/return-to-keywords
- **Persistent keywords** saved to `~/.config/yt-player/keywords.json`
- Help dialog for caregivers (French)
- Exit with confirmation dialog
- Captive portal detection & auto-accept on public WiFi
- **34 app tests + 6 integration tests pass**

## Tech Stack

| Component | Version | Source | Path |
|-----------|---------|--------|------|
| OS | Linux Mint 22.3 (Zena), XFCE, X11 | — | — |
| Python | 3.12.3 | apt (python3) | `/usr/bin/python3` |
| tkinter | 8.6 | apt (python3-tk) | — |
| mpv | 0.37+ | apt or configured path | auto-detected with fallback `/usr/bin/mpv` |
| yt-dlp | 2026.06.09+ | Python package for new installs; GitHub binary for legacy direct script use | package dependency / fallback `/usr/local/bin/yt-dlp` |
| deno | 2.3.0+ | GitHub install script or future bundled sidecar | `YTKIOSK_DENO`, package sidecar, PATH, or `/usr/local/bin/deno` |

### Critical: yt-dlp must be the latest GitHub release
The apt version (`/usr/bin/yt-dlp`) is too old — YouTube's JS changes can break its `n`-signature extraction, causing HTTP 403 on all URLs. Remove the apt package and use the standalone binary from GitHub at `/usr/local/bin/yt-dlp`:
```bash
sudo apt remove -y yt-dlp || true
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
/usr/local/bin/yt-dlp --version
```

### Deno is required by yt-dlp for JS-based signature extraction
```bash
curl -fsSL https://deno.land/install.sh | sh
sudo install -m 755 "$HOME/.deno/bin/deno" /usr/local/bin/deno
/usr/local/bin/deno --version
```
Install Deno into `/usr/local/bin` so subprocesses launched by the app and yt-dlp can find it reliably.

## Packaging Direction

The project is intentionally Linux-only. Windows support is out of scope because
the deployment goal is to reuse older hardware that cannot run Windows 11 well.

The GUI implementation now lives in `src/ytkiosk/legacy.py`. The root
`simple-video-player.py` file is a compatibility launcher for existing scripts,
desktop shortcuts, and tests.

```bash
uv pip install -e .
ytkiosk
ytkiosk-doctor
ytkiosk-cli doctor
```

Bundling policy:

- Bundle/manage Python dependencies, including `yt-dlp`.
- Bundle Deno as a Linux sidecar in future release artifacts when needed.
- Do **not** bundle `mpv`; install it via the distro package manager.
- Treat `xset`, `xdg-open`, and `pactl` as optional system helpers.

See `docs/DEPENDENCIES.md`, `docs/RELEASE.md`, and
`THIRD_PARTY_LICENSES.md` before publishing binary bundles.

## Files

| File | Purpose |
|------|---------|
| `simple-video-player.py` | Compatibility launcher for the packaged legacy app |
| `test_app.py` | App/unit-style tests |
| `test_integration.py` | 6 integration tests |
| `yt-player.desktop` | Desktop shortcut |
| `HANDOFF.md` | This file |
| `pyproject.toml` | Python packaging metadata and helper command entry points |
| `src/ytkiosk/legacy.py` | Current GUI/playback implementation, moved from the monolith |
| `src/ytkiosk/` | Incremental package modules and helper commands |
| `docs/DEPENDENCIES.md` | Linux-only dependency and bundling policy |
| `docs/RELEASE.md` | Future release bundle checklist |

## Architecture

### Flow: Button Click → Fullscreen Playback
```
User clicks keyword (e.g. "Voitures classiques")
  │
  ├─► detect_captive_portal()
  │     └─ Portal? → handle_captive_portal() → auto-accept or browser
  │
  ├─► Show loading overlay in main window
  │
  ├─► yt-dlp ytsearch30:{kw} --flat-playlist
  │       --ignore-errors
  │       --match-filters "duration > 300 & !is_live"
  │       --print "%(id)s\t%(duration)s"
  │     └─ Returns IDs + durations for long non-live videos
  │
  ├─► Filter: keep duration > 300s (5 min)
  │     Sort by duration descending → take top 20 → shuffle
  │
  ├─► Switch to video mode:
  │     Hide keyword_frame → show video_frame
  │     root.update_idletasks() → video_frame.winfo_id() → X11 window ID
  │
  ├─► Launch embedded mpv with --wid={X11_ID}
  │     mpv --osd-level=0
  │         --wid={X11_ID}
  │         --no-config
  │         --input-ipc-server=$RUNTIME_DIR/mpv-socket
  │         --keep-open=no
  │         --gpu-context=x11egl
  │         --ao=<detected backend> --profile=fast
  │         --x11-bypass-compositor=yes
  │         --ytdl-format="bv[height<=720]+ba/b[height<=720]"
  │         [20 shuffled YouTube URLs...]
  │
  └─► Controls enabled (IPC socket)
        ⏮  ▶/⏸  ⏭  |  Volume [===]  |  Arrêter  Mots-clés
```

### New: Search & Playlist Algorithm
- Fetches **30 search results** in a single fast yt-dlp call
- `--flat-playlist` gives both IDs and durations from YouTube's search snippet data (no individual video extraction needed)
- `--match-filters "duration > 300 & !is_live"` filters out short clips and livestreams
- Results sorted by duration descending, top **20** selected, then **randomly shuffled**
- First video is random from among the longest candidates; the rest auto-queue in random order

### New: Embedded mpv (tkinter + X11)
```
Main Window (fullscreen)
  ├── Top Bar: [Aide]  [QUITTER]
  ├── Main Area (fill both)
  │     ├── [Keyword View]  ← visible when choosing
  │     ├── [Loading Label] ← visible during search
  │     └── [Video Frame]   ← mpv embedded via --wid=winfo_id()
  └── Control Bar: ⏮ ▶ ⏭ Volume Arrêter Mots-clés
```

### New: Kiosk Mode
- `root.attributes("-fullscreen", True)` — proper fullscreen without focus bugs
- `root.protocol("WM_DELETE_WINDOW")` — blocks Alt+F4 / window close
- `<Escape>`, `<F11>`, `<Control-q>` all bound to `"break"`
- Exit requires **confirmation dialog** (Yes/No, default No)
- `_cleanup()` ensures mpv is killed on exit

### New: Help Dialog
- Always-accessible **Aide** button in top bar
- Full-screen modal Toplevel with instructions for caregivers
- Explains keyword setup, playback controls, and exit procedure

### New: Persistent Keywords
- Saved to `~/.config/yt-player/keywords.json`
- Loaded on startup; initialized to `INITIAL_KEYWORDS` if missing
- Saved on every add/edit

### IPC Control (MpvRemote class)
All controls communicate with mpv via a Unix socket in the private per-user runtime directory:
- `toggle_pause()` → `cycle pause`
- `next_track()` → `playlist-next`
- `prev_track()` → `playlist-prev`
- `set_volume(n)` → `set_property volume n`
- `get_volume()` / `get_pause_state()` / `get_media_title()` → `get_property`
- `stop()` → `stop`
- Polling loop every 2s syncs UI state with mpv

### Captive Portal (unchanged)
Same logic as before: probe multiple endpoints, detect redirect, auto-accept or open browser.

## Key Architecture Decisions

### Why `attributes("-fullscreen")` over `overrideredirect(True)`?
- `overrideredirect(True)` causes **focus/input bugs** on X11/Linux (Entry widgets don't gain focus, keyboard events break)
- `attributes("-fullscreen")` gives proper fullscreen without focus issues
- Combined with `protocol("WM_DELETE_WINDOW")` and key bindings, it's sufficiently locked down for hospital use

### Why `--flat-playlist` with `--match-filters`?
- `--flat-playlist` is **fast** (uses YouTube search snippet data, no per-video extraction)
- Contrary to common belief, `--flat-playlist` **does provide duration** for search results
- `--match-filters "duration > 300 & !is_live"` filters before printing, saving processing
- No need for ThreadPoolExecutor or per-video yt-dlp calls

### Why remove `--loop-playlist` and `--autofit`?
- `--loop-playlist` conflicts with embedded mode (loop not needed — playlist auto-advances)
- `--autofit` is irrelevant when embedded (mpv fills the Frame)
- `--force-window=immediate` conflicts with `--wid` (never combine them)
- `--no-border` is implicit when using `--wid` (the parent frame controls appearance)

## Bug History (all resolved)

### Bug 1: "mpv launches but no window" (INHERITED — still resolved)
**Root cause:** Three independent failure modes in mpv 0.37.0 on XFCE/X11:
1. Window creation deferred → `--force-window=immediate` (not needed with `--wid`)
2. Wayland probe fail on X11 → `--gpu-context=x11egl`
3. PipeWire audio init hang → `--ao=pulse`

### Bug 2: "Window appears but black, no video" (INHERITED — still resolved)
**Root cause:** Old yt-dlp (apt 2024.04.09) can't extract YouTube's `n` signature → 403 Forbidden.
**Fix:** Use GitHub release + pass YouTube URLs instead of direct media URLs.

### Bug 3: "Keyword reset on restart" (FIXED — added persistence)
Keywords now saved to `~/.config/yt-player/keywords.json`.

### Bug 4: "mpv pops up as separate window" (FIXED — embedded with `--wid`)
mpv now renders inside the tkinter window via X11 embedding.

## Known Issues / Gotchas

1. **X11-oriented embedding** — mpv uses Tk's X11 window ID via `--wid`; Wayland or unusual GPU drivers may need mpv flag changes.
2. **Captive portal auto-accept is best-effort** — works for simple "click agree" portals, not complex login portals.
3. **Daemon worker threads** — stale playback startup callbacks are session-guarded, but workers are still daemon threads during app shutdown.
4. **Duration filter may be too aggressive** — `MIN_DURATION=300` (5 min) might filter out good content for some keywords. Adjust config if needed.
5. **yt-dlp rate limiting** — YouTube may throttle after repeated requests. Add `--sleep-requests 1` if issues arise.

## Running Tests
```bash
python3 test_app.py
xvfb-run -a python3 test_integration.py
```
Use `xvfb-run` for integration tests on headless systems because Tk requires a display.

## Desktop Shortcut
`yt-player.desktop` — placed on desktop or in `~/.local/share/applications/`

## Auto-start on Boot (for hospital use)
```bash
mkdir -p ~/.config/autostart
cp yt-player.desktop ~/.config/autostart/
```

## French Strings
All UI strings in `FR` dict (lines 30–75). Change these to translate to another language. Keywords in `INITIAL_KEYWORDS` (lines 77–82).

## Key Constants (tunable)
| Constant | Default | Purpose |
|----------|---------|---------|
| `SEARCH_COUNT` | 30 | Number of videos to fetch from YouTube |
| `PLAYLIST_SIZE` | 20 | Number of videos in the auto-queue |
| `MIN_DURATION` | 300 | Minimum video duration in seconds (5 min) |
