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
  │     Show video frame → get X11 window ID → mpv --wid={ID}
  │
  └─► mpv plays embedded in the tkinter window
        Controls via IPC Unix socket (/tmp/mpv-socket)
```

---

## Requirements

- **OS:** Linux (tested on Linux Mint 22.3 XFCE, X11)
- **RAM:** 2–4 GB minimum
- **Python:** 3.12+ with tkinter (`python3-tk`)
- **mpv:** 0.37+ from apt is fine
- **yt-dlp:** Latest GitHub release at `/usr/local/bin/yt-dlp` (do not use apt)
- **Deno:** Required by current yt-dlp for YouTube JS signature extraction

### Install yt-dlp (Critical)

The apt version of yt-dlp is outdated and can fail with HTTP 403 errors. Always remove the apt package and use the latest GitHub release:

```bash
sudo apt remove -y yt-dlp || true
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
/usr/local/bin/yt-dlp --version
```

### Install Deno (required by yt-dlp for JS signature extraction)

```bash
curl -fsSL https://deno.land/install.sh | sh
sudo install -m 755 "$HOME/.deno/bin/deno" /usr/local/bin/deno
/usr/local/bin/deno --version
```

---

## Installation

```bash
# System dependencies
sudo apt install python3 python3-tk mpv

# Latest yt-dlp, not the apt package
sudo apt remove -y yt-dlp || true
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp

# Deno, available to subprocesses launched by the app
curl -fsSL https://deno.land/install.sh | sh
sudo install -m 755 "$HOME/.deno/bin/deno" /usr/local/bin/deno

# Clone and run
git clone https://github.com/mojomast/ytkiosk.git
cd ytkiosk
python3 simple-video-player.py
```

---

## Setup for a Hospital or Care Home

### Auto-start on Boot

```bash
mkdir -p ~/.config/autostart
cp yt-player.desktop ~/.config/autostart/
```

### Customizing Keywords

Use the ✎ button inside the app to edit keywords, or click **+ Ajouter un mot-clé** to add new ones. Keywords save automatically. You can also edit `INITIAL_KEYWORDS` in `simple-video-player.py` to set the defaults for a fresh install.

### Translation

All UI strings live in the `FR` dictionary at the top of `simple-video-player.py`. Replace the values to translate to any language.

---

## Configuration

| Constant | Default | Description |
|---|---|---|
| `SEARCH_COUNT` | 30 | Videos fetched per search |
| `PLAYLIST_SIZE` | 20 | Videos in the auto-queue |
| `MIN_DURATION` | 300 | Minimum video length in seconds (5 min) |
| `CONFIG_DIR` | `~/.config/yt-player` | Where keywords are saved |

---

## Tech Stack

| Component | Role |
|---|---|
| Python 3.12 + tkinter | UI |
| mpv | Video playback (embedded via X11 `--wid`) |
| yt-dlp | YouTube search and metadata |
| Deno | JS runtime for yt-dlp signature extraction |
| X11 (Xorg) | Window system |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Top Bar: [Aide]               [QUITTER]    │
├─────────────────────────────────────────────┤
│                                             │
│  Main Area (Keyword View / Video Embed)     │
│                                             │
├─────────────────────────────────────────────┤
│  ⏮  ▶  ⏭  | Volume [====] | Arrêter  Mots-clés │
│  En cours: Video Title...                   │
└─────────────────────────────────────────────┘
```

---

## Running Tests

```bash
python3 test_app.py         # 24 unit tests
python3 test_integration.py # 6 integration tests
```

---

## Known Limitations

- Audio backend assumes PulseAudio (`--ao=pulse`). Change to `alsa` or `pipewire` if needed
- Captive portal auto-accept works for simple "click agree" portals only
- When the playlist ends, the user must re-select a keyword to start a new queue
- Single-user only — socket at `/tmp/mpv-socket` assumes one session

---

## License

MIT — take it, deploy it, give it to a hospital, run it on whatever hardware you have.
