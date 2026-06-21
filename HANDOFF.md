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
- **15 unit tests + 6 integration tests all pass**

## Tech Stack

| Component | Version | Source | Path |
|-----------|---------|--------|------|
| OS | Linux Mint 22.3 (Zena), XFCE, X11 | — | — |
| Python | 3.12.3 | apt (python3) | `/usr/bin/python3` |
| tkinter | 8.6 | apt (python3-tk) | — |
| mpv | 0.37.0 | apt | `/usr/bin/mpv` |
| yt-dlp | 2026.06.09 | **GitHub release** (NOT apt) | `/usr/local/bin/yt-dlp` |
| deno | latest | GitHub install script | `~/.deno/bin/deno` |

### Critical: yt-dlp must be the latest GitHub release
The apt version (`/usr/bin/yt-dlp`) is too old — YouTube's JS changes break its `n`-signature extraction, causing HTTP 403 on all URLs. Always use the standalone binary from GitHub at `/usr/local/bin/yt-dlp`. Update with:
```bash
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
```

### Deno is required by yt-dlp for JS-based signature extraction
```bash
curl -fsSL https://deno.land/install.sh | sh
```
The `PATH` in the app's subprocess env includes `~/.deno/bin` via `$HOME/.deno/bin/deno`.

## Files (all in `/home/baloney/yt/`)

| File | Purpose |
|------|---------|
| `simple-video-player.py` | Main app (~770 lines) |
| `test_app.py` | 15 unit tests |
| `test_integration.py` | 6 integration tests |
| `yt-player.desktop` | Desktop shortcut |
| `HANDOFF.md` | This file |

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
  │         --input-ipc-server=/tmp/mpv-socket
  │         --keep-open=always
  │         --gpu-context=x11egl
  │         --ao=pulse --profile=fast --gpu-dumb-mode=yes
  │         --x11-bypass-compositor=no
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

### IPC Control (MpvRemote class — unchanged)
All controls communicate with mpv via Unix socket at `/tmp/mpv-socket`:
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

1. **No audio device fallback** — `--ao=pulse` assumes PulseAudio. If system uses ALSA or PipeWire directly, change to `--ao=alsa` or `--ao=pipewire`.
2. **Captive portal auto-accept is best-effort** — works for simple "click agree" portals, not complex login portals.
3. **Socket path hardcoded** — `/tmp/mpv-socket`. Fine for single-user, would conflict on multi-user system.
4. **daemon threads** — playback thread is daemon, so if main window closes during playback, thread may not clean up mpv.
5. **No automatic playlist refresh** — once the 20-video playlist finishes, mpv stays on the last frame. User must click "Mots-clés" and re-select a keyword.
6. **No screensaver inhibition** — consider adding `xset s off -dpms` for hospital use.
7. **Duration filter may be too aggressive** — `MIN_DURATION=300` (5 min) might filter out good content for some keywords. Adjust in the code if needed.
8. **yt-dlp rate limiting** — YouTube may throttle after repeated requests. Add `--sleep-requests 1` if issues arise.

## Running Tests
```bash
python3 /home/baloney/yt/test_app.py        # 15 unit tests
python3 /home/baloney/yt/test_integration.py # 6 integration tests
```

## Desktop Shortcut
`/home/baloney/yt/yt-player.desktop` — placed on desktop or in `~/.local/share/applications/`

## Auto-start on Boot (for hospital use)
```bash
mkdir -p ~/.config/autostart
cp /home/baloney/yt/yt-player.desktop ~/.config/autostart/
```

## French Strings
All UI strings in `FR` dict (lines 30–75). Change these to translate to another language. Keywords in `INITIAL_KEYWORDS` (lines 77–82).

## Key Constants (tunable)
| Constant | Default | Purpose |
|----------|---------|---------|
| `SEARCH_COUNT` | 30 | Number of videos to fetch from YouTube |
| `PLAYLIST_SIZE` | 20 | Number of videos in the auto-queue |
| `MIN_DURATION` | 300 | Minimum video duration in seconds (5 min) |
