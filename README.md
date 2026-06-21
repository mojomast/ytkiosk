# YT Kiosk — Hospital-Grade YouTube Video Kiosk

A fullscreen, lockdown YouTube video player for hospital patients, elderly care, and any setting where you want a simple, hands-off video experience. A caregiver sets up keyword-based video streams, and patients watch an endless auto-queue of randomly shuffled, long-form content — no accounts, no browser, no way to escape.

Born from a real need: patients staring at walls with nothing to do. This runs on a cheap Linux laptop plugged into a TV, and requires nothing else.

## Features

- **Fullscreen kiosk mode** — no window decorations, no Alt+F4, no Escape. Patients can't accidentally close it.
- **mpv embedded inside the app** — no separate popup window. One unified UI.
- **Random, long-form auto-queues** — searches ~30 videos, filters out short clips (<5 min) and livestreams, picks the longest 20, shuffles them, and plays them in sequence.
- **Keyword-based browsing** — caregivers add/edit keywords (e.g. "Voitures classiques", "Compilations d'animaux"). Each keyword generates a fresh random playlist every click.
- **On-screen controls** — play/pause, skip, volume, stop, return to keywords. Large buttons for elderly/touch use.
- **Captive portal detection** — auto-detects and accepts hotel/hospital WiFi login pages.
- **Persistent keywords** — saved to `~/.config/yt-player/keywords.json`. Survives restarts.
- **Help dialog** — built-in French-language instructions for caregivers.
- **Exit requires confirmation** — no accidental shutdowns.

## How It Works

### For Patients

The app launches directly into fullscreen. The patient just watches. Caregivers handle everything else.

### For Caregivers

1. Launch the app (auto-starts on boot if configured)
2. Click a keyword button → videos start playing automatically
3. Use the bottom control bar to pause, skip, or adjust volume
4. Click **Mots-clés** to return to keyword selection
5. Click **Aide** for built-in instructions
6. Click **QUITTER** → confirm → app closes

### Technical Flow

```
User clicks keyword
  │
  ├─► Detect captive portal → auto-accept if needed
  │
  ├─► yt-dlp ytsearch30:{keyword} --flat-playlist
  │     --match-filters "duration > 300 & !is_live"
  │     → Returns 20+ video IDs with durations
  │
  ├─► Sort by duration → keep longest 20 → shuffle randomly
  │
  ├─► Switch tkinter to video mode:
  │     Show video frame → get X11 window ID → mpv --wid={ID}
  │
  └─► mpv plays embedded in the tkinter window
        Controls via IPC Unix socket (/tmp/mpv-socket)
```

## Requirements

- **OS:** Linux (tested on Linux Mint 22.3 XFCE, X11)
- **RAM:** 2–4 GB minimum
- **Python:** 3.12+ with tkinter (`python3-tk`)
- **mpv:** 0.37+ (`apt install mpv`)
- **yt-dlp:** Latest GitHub release (NOT apt version)

### Critical: yt-dlp

The apt version of yt-dlp is too old and will fail with HTTP 403 errors. Always use the latest release from GitHub:

```bash
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp
```

### Deno (required by yt-dlp for JS signature extraction)

```bash
curl -fsSL https://deno.land/install.sh | sh
```

## Installation

```bash
# Install system dependencies
sudo apt install python3 python3-tk mpv

# Install latest yt-dlp
sudo wget -q https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
  -O /usr/local/bin/yt-dlp && sudo chmod +x /usr/local/bin/yt-dlp

# Install deno
curl -fsSL https://deno.land/install.sh | sh

# Clone or copy the files
git clone https://github.com/mojomast/ytkiosk.git
cd ytkiosk

# Run
python3 simple-video-player.py
```

## Usage

### Desktop Shortcut

Copy `yt-player.desktop` to your desktop or to `~/.local/share/applications/`.

### Auto-start on Boot (Hospital Setup)

```bash
mkdir -p ~/.config/autostart
cp yt-player.desktop ~/.config/autostart/
```

### Customizing Keywords

Edit `simple-video-player.py` and change the `INITIAL_KEYWORDS` list, or use the ✎ button and "+ Ajouter un mot-clé" inside the app. Keywords persist automatically.

### Translation

All UI strings are in the `FR` dictionary at the top of `simple-video-player.py`. Change the values to translate.

## Configuration

Key constants at the top of `simple-video-player.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `SEARCH_COUNT` | 30 | Number of videos to fetch per search |
| `PLAYLIST_SIZE` | 20 | Number of videos in auto-queue |
| `MIN_DURATION` | 300 | Min video duration in seconds (5 min) |
| `CONFIG_DIR` | `~/.config/yt-player` | Where keywords are saved |

## Running Tests

```bash
python3 test_app.py         # 24 unit tests
python3 test_integration.py # 6 integration tests
```

## Tech Stack

| Component | Role |
|-----------|------|
| Python 3.12 + tkinter | UI framework |
| mpv 0.37+ | Video playback (embedded via X11 `--wid`) |
| yt-dlp (latest GitHub) | YouTube search + metadata extraction |
| Deno | JS runtime for yt-dlp signature extraction |
| X11 (Xorg) | Window system — embedding mpv via `--wid` |

## Architecture

```
┌─────────────────────────────────────────────┐
│  Top Bar: [Aide]               [QUITTER]    │
├─────────────────────────────────────────────┤
│                                             │
│  Main Area (Keyword View / Video Embed)     │
│  ┌───────────────────────────────────────┐  │
│  │                                       │  │
│  │  • Keyword buttons (keyword mode)     │  │
│  │     or                                │  │
│  │  • mpv embedded via --wid (playback)  │  │
│  │                                       │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│  ⏮  ▶  ⏭  | Volume [====] | Arrêter Mots-clés │
│  En cours: Video Title...                    │
└─────────────────────────────────────────────┘
```

## Known Limitations

- Audio backend assumes PulseAudio (`--ao=pulse`). Change to `alsa` or `pipewire` if needed.
- Captive portal auto-accept works for simple "click agree" portals only.
- Socket at `/tmp/mpv-socket` is single-user only.
- Duration filter (`MIN_DURATION=300`) may be too aggressive for some keywords.
- No automatic playlist refresh — when the queue ends, user must re-select a keyword.

## License

MIT
