# Handoff: Lecteur Vidéo Simple (Kiosk Edition)

## Project Overview
Hospital-grade kiosk YouTube player for Linux Mint. Designed for elderly patients — a caregiver sets up keyword-based video streams and the patient watches full-screen with auto-queued random videos. No accounts, no browser, works on 2–4 GB RAM hardware.

## Current State — FULLY WORKING
- Fullscreen kiosk mode (no decorations, blocks Escape/Alt+F4)
- mpv **embedded inside** tkinter window on X11/XWayland; native Wayland uses standalone fullscreen fallback
- Click a keyword → searches YouTube → fetches **30 videos** → filters long (≥5 min) → picks **20 random long ones** → auto-plays in shuffled order
- On-screen controls: pause/next/prev/volume/stop/return-to-keywords
- **Persistent keywords** saved to `~/.config/yt-player/keywords.json`
- **Persistent language/CC/pin preferences** saved to `~/.config/yt-player/config.json`
- **Favorites playlist** saved to `~/.config/yt-player/favorites.json`
- Runtime EN/FR UI toggle, CC toggle, audio-track cycling, auto-hide playback bars, and password-protected Options menu
- Configurable application title plus caregiver control over keyword add/edit visibility
- Help dialog and Debug console for caregivers/testers
- Exit with confirmation dialog
- Captive portal detection & auto-accept tuned for the CISSS Côte-Nord guest WiFi portal
- App tests cover mpv command construction, display fallback, captive portal form parsing/submission, and config defaults; integration smoke tests cover Tk UI wiring

## Tech Stack

| Component | Version | Source | Path |
|-----------|---------|--------|------|
| OS | Linux Mint 22.3 (Zena), XFCE, X11 | — | — |
| Python | 3.12.3 | apt (python3) | `/usr/bin/python3` |
| tkinter | 8.6 | apt (python3-tk) | — |
| mpv | 0.37+ | apt or configured path | auto-detected with fallback `/usr/bin/mpv` |
| yt-dlp | 2026.06.09+ | Python package for new installs; GitHub binary for legacy direct script use | package dependency / fallback `/usr/local/bin/yt-dlp` |
| JS runtime | Optional; Deno 2.3.0+ preferred | Deno, Node 22+, QuickJS, or future bundled sidecar | `YTKIOSK_DENO`, package sidecar, PATH, or runtime-specific PATH lookup |

### Critical: yt-dlp must be current
The apt version (`/usr/bin/yt-dlp`) is often too old — YouTube's JS changes can break its `n`-signature extraction, causing HTTP 403 on all URLs. New installs use the PyPI package dependency (`yt-dlp[default]`) inside the YTKiosk venv. If running `simple-video-player.py` directly without installing the package, put a current `yt-dlp` on PATH:
```bash
sudo apt remove -y yt-dlp || true
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
/usr/local/bin/yt-dlp --version
```

### JavaScript runtime support is optional but recommended
yt-dlp can use Deno, Node, QuickJS, or Bun for JavaScript extraction. YTKiosk prefers Deno when present, then Node, then QuickJS, and passes the resolved runtime explicitly to both playlist search and mpv's yt-dlp hook. Missing runtime is a doctor warning, not an install failure.

```bash
curl -fsSL https://deno.land/install.sh | sh
~/.deno/bin/deno --version
```

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

- Bundle/manage Python dependencies, including `yt-dlp[default]`.
- Bundle a JavaScript runtime sidecar in future release artifacts only when needed and license/checksum records are complete.
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

## Current Install / Update Path

The README one-line install is the primary deployment path:

```bash
curl -fsSL 'https://raw.githubusercontent.com/mojomast/ytkiosk/main/install.sh?v=2026-06-21.5' | bash
```

It downloads `install.sh` from `main`; the installer downloads
`https://github.com/mojomast/ytkiosk/archive/refs/heads/main.tar.gz`, recreates
`~/.local/share/ytkiosk/venv`, installs the package, and refreshes wrappers in
`~/.local/bin`. Existing `~/.config/yt-player/keywords.json` and state are
preserved, including the new `config.json` preferences and `favorites.json`.

Useful installed commands:
- `ytkiosk` launches the GUI.
- `ytkiosk-doctor` checks dependencies and display/runtime state.
- `ytkiosk-cli doctor` runs the helper doctor command.
- `ytkiosk-yt-dlp` runs the venv-managed yt-dlp copy.

## Architecture

### Flow: Button Click → Fullscreen Playback
```
User clicks keyword (e.g. "Voitures classiques")
  │
  ├─► detect_captive_portal()
  │     └─ Portal? → handle_captive_portal() → auto-accept or browser
  │                  → wait briefly, then retry first yt-dlp search if needed
  │
  ├─► Show loading overlay in main window
  │
  ├─► yt-dlp ytsearch30:{kw} --flat-playlist
  │       --js-runtimes <runtime:path> when Deno/Node/QuickJS is detected
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
  │     X11/XWayland: root.update_idletasks() → video_frame.winfo_id() → X11 window ID
  │     Native Wayland: keep app controls and use standalone fullscreen mpv
  │
  ├─► Launch mpv
  │     mpv --osd-level=0
  │         --wid={X11_ID} on embedded X11/XWayland
  │         --no-config
  │         --input-ipc-server=$RUNTIME_DIR/mpv-socket
  │         --keep-open=no
  │         --gpu-context=x11egl on embedded X11/XWayland
  │         --fs --ontop --no-border on standalone fallback
  │         --ao=<detected backend> --profile=fast
  │         --x11-bypass-compositor=yes on embedded X11/XWayland
  │         --ytdl-format="bv[height<=720]+ba/b[height<=720]"
  │         --script-opts=ytdl_hook-ytdl_path=<YTKiosk venv yt-dlp>
  │         [20 shuffled YouTube URLs...]
  │
  └─► Controls enabled (IPC socket)
        ⏮  ▶/⏸  ⏭  CC  Audio  ♥  |  Volume [===]  |  Arrêter  Mots-clés
```

### New: Search & Playlist Algorithm
- Fetches **30 search results** in a single fast yt-dlp call
- `--flat-playlist` gives both IDs and durations from YouTube's search snippet data (no individual video extraction needed)
- `--match-filters "duration > 300 & !is_live"` filters out short clips and livestreams
- Results sorted by duration descending, top **20** selected, then **randomly shuffled**
- First video is random from among the longest candidates; the rest auto-queue in random order

### New: Embedded mpv (tkinter + X11/XWayland)
```
Main Window (fullscreen)
  ├── Top Bar: [Aide] [Debug] [EN/FR] [Épingler/Pin] [⚙ Options]
  ├── Main Area (fill both)
  │     ├── [Keyword View]  ← visible when choosing
  │     ├── [Loading Label] ← visible during search
  │     └── [Video Frame]   ← mpv embedded via --wid=winfo_id() on X11/XWayland
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

### Captive Portal: CISSS Côte-Nord
Current deployment focus is the CISSS Côte-Nord guest WiFi portal:

```text
https://cisss-public.reg09.rtss.qc.ca/login.html
```

Important implementation details in `src/ytkiosk/legacy.py`:
- `CAPTIVE_PORTAL_URLS` defaults to the CISSS portal URL.
- `ENABLE_CAPTIVE_PORTAL_TRIGGER_URLS` defaults to `False`, so `1.1.1.1` and `neverssl.com` are not attempted unless config opts in.
- The CISSS page is Cisco-style: the visible `Accepter` control is `input type="button"`, not a submit input.
- Browser JavaScript normally sets `buttonClicked=4`, fills `redirect_url` from the `redirect=` query parameter, and submits the form.
- Some variants include `switch_url=...`; when present, YTKiosk posts there.
- The hospital-tested variant only has `redirect=http://detectportal.firefox.com/canonical.html`; when `switch_url` is missing and the form action is the placeholder `google.ca`, YTKiosk posts back to the current `login.html?...redirect=...` URL instead.
- After portal acceptance, `_wait_after_captive_portal()` waits for connectivity to settle, then `_fetch_playlist_with_retries()` retries the initial search. Defaults: `POST_PORTAL_SEARCH_RETRIES=3`, `POST_PORTAL_RETRY_DELAY=5`.

Debugging:
- The top-bar **Debug** button opens a live tail of `LOG_FILE`.
- Logs redact query strings in URLs as `<query>`.
- Captive portal logs include fetch status/final URL/content type, selected form action/post URL, field names/types, submitted field names, submit status/final URL, and retry outcomes.

Config overrides in `~/.config/yt-player/config.json`:
- `language`: `"fr"` or `"en"`; defaults to `"fr"`.
- `cc_enabled`: boolean for subtitles/closed captions; defaults to `false`.
- `pin_controls`: boolean to disable playback control auto-hide; defaults to `false`.
- `app_title`: custom title shown in the window/title heading; defaults to the active localized title.
- `allow_keyword_changes`: boolean to show/hide add/edit keyword controls; defaults to `true`.
- `options_password`: password for the caregiver Options menu; defaults to `"baloney"`.
- `captive_portal_urls`: string comma list or JSON list of portal URLs.
- `enable_captive_portal_trigger_urls`: boolean to re-enable generic trigger URLs.
- `post_portal_search_retries`: integer retry count after portal acceptance.
- `post_portal_retry_delay`: integer seconds between post-portal search retries.

Favorites are stored in `~/.config/yt-player/favorites.json` as an array of
`{"id": "<yt_id>", "title": "<title>", "duration": <seconds>, "added": "<ISO8601>"}`.

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
**Fix:** Use package-managed `yt-dlp[default]` for installs, avoid stale distro yt-dlp, and pass YouTube URLs instead of direct media URLs.

### Bug 3: "Keyword reset on restart" (FIXED — added persistence)
Keywords now saved to `~/.config/yt-player/keywords.json`.

### Bug 4: "mpv pops up as separate window" (FIXED — embedded with `--wid`)
mpv now renders inside the tkinter window via X11/XWayland embedding. Native Wayland sessions use standalone fullscreen fallback instead of attempting unsupported native embedding.

### Bug 5: CISSS captive portal loops or posts to Google (FIXED)
**Root cause:** The portal's form action is a placeholder (`https://www.google.ca`). Browser JavaScript rewrites the action or posts back to the current portal URL while setting hidden fields. A non-JS client must emulate this.
**Fix:** Detect Cisco-style forms, set `buttonClicked=4`, fill `redirect_url`, prefer `switch_url` when provided, and otherwise post to the current CISSS `login.html?...redirect=...` URL instead of Google.

### Bug 6: First search fails immediately after portal acceptance (FIXED)
**Root cause:** Network authorization/DNS can lag briefly after captive portal acceptance, so the first `yt-dlp` search can fail even though a second keyword click works.
**Fix:** After portal success, wait for connectivity to settle and retry the first playlist search before surfacing an error.

## Known Issues / Gotchas

1. **X11-oriented embedding** — mpv uses Tk's X11 window ID via `--wid`; native Wayland embedding is unsupported and falls back to standalone fullscreen mpv.
2. **Captive portal auto-accept is deployment-tuned** — currently optimized for CISSS Côte-Nord. Other portals may need config changes or new parser rules.
3. **Daemon worker threads** — stale playback startup callbacks are session-guarded, but workers are still daemon threads during app shutdown.
4. **Audio track cycling depends on source media** — the Audio button only changes language when a video exposes multiple audio tracks to mpv.
5. **Subtitle availability varies** — CC asks mpv for best subtitles and prefers `fr,en` or `en,fr`, but YouTube videos may not expose matching captions.
6. **Options password is a kiosk guardrail** — it is stored in plain text in `config.json`, not hashed or encrypted.
7. **Duration filter may be too aggressive** — `MIN_DURATION=300` (5 min) might filter out good content for some keywords. Adjust config if needed.
8. **yt-dlp rate limiting** — YouTube may throttle after repeated requests. Add `--sleep-requests 1` if issues arise.

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

## Language Strings
All UI strings live in `STRINGS_FR` and `STRINGS_EN` near the top of
`src/ytkiosk/legacy.py`; tests assert both dictionaries have matching keys.
The active language defaults to French and can be changed at runtime with the
top-bar EN/FR toggle.

## Key Constants (tunable)
| Constant | Default | Purpose |
|----------|---------|---------|
| `SEARCH_COUNT` | 30 | Number of videos to fetch from YouTube |
| `PLAYLIST_SIZE` | 20 | Number of videos in the auto-queue |
| `MIN_DURATION` | 300 | Minimum video duration in seconds (5 min) |
