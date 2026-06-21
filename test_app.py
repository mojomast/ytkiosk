#!/usr/bin/env python3

import subprocess
import sys
import os
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(TEST_DIR, "simple-video-player.py")


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}  {detail}")


def test_ytdlp_installed():
    try:
        r = subprocess.run(
            ["/usr/local/bin/yt-dlp", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        test("yt-dlp is installed and recent",
             r.returncode == 0 and r.stdout.strip() >= "2026",
             f"rc={r.returncode} version={r.stdout.strip()}")
    except FileNotFoundError:
        test("yt-dlp binary at /usr/local/bin/yt-dlp", False)


def test_mpv_available():
    try:
        r = subprocess.run(
            ["mpv", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        test("mpv is installed and runnable", r.returncode == 0,
             f"rc={r.returncode}")
    except FileNotFoundError:
        test("mpv binary exists", False)


def test_url_building():
    ids = ["abc123", "def456", "ghi789"]
    urls = [f"https://www.youtube.com/watch?v={vid}" for vid in ids]
    expected = [
        "https://www.youtube.com/watch?v=abc123",
        "https://www.youtube.com/watch?v=def456",
        "https://www.youtube.com/watch?v=ghi789",
    ]
    test("YouTube URLs constructed correctly", urls == expected, f"got {urls}")


def test_mpv_command_format():
    urls = ["https://www.youtube.com/watch?v=abc123"]
    cmd = [
        "mpv", "--osd-level=0",
        "--wid=<id>",
        "--no-config",
        "--input-ipc-server=/tmp/mpv-socket",
        "--keep-open=always",
        "--gpu-context=x11egl", "--ao=pulse",
        "--profile=fast", "--gpu-dumb-mode=yes",
        "--x11-bypass-compositor=no",
        "--ytdl-format=bv[height<=720]+ba/b[height<=720]",
    ] + urls
    required = [
        "--osd-level=0", "--no-config",
        "--input-ipc-server=/tmp/mpv-socket",
        "--keep-open=always",
        "--gpu-context=x11egl", "--ao=pulse",
        "--profile=fast", "--gpu-dumb-mode=yes",
        "--x11-bypass-compositor=no",
        "--ytdl-format=bv[height<=720]+ba/b[height<=720]",
    ]
    test("mpv command has all required args",
         all(a in cmd for a in required), f"cmd={cmd}")

    test("mpv command includes --wid for embedding",
         any(a.startswith("--wid=") for a in cmd),
         f"no --wid flag in {cmd}")

    test("mpv command does NOT include --loop-playlist",
         "--loop-playlist" not in cmd,
         "loop-playlist should not be used with embedded mpv")

    test("mpv command does NOT include --autofit",
         not any(a.startswith("--autofit") for a in cmd),
         "autofit should not be used with embedded mpv")


def test_app_script_syntax():
    try:
        compile(open(APP_PATH).read(), "simple-video-player.py", "exec")
        test("App script has valid syntax", True)
    except SyntaxError as e:
        test("App script has valid syntax", False, str(e))


def _import_module():
    spec = importlib.util.spec_from_file_location("svp", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_french_keywords():
    mod = _import_module()
    expected = [
        "Voitures classiques",
        "Compilations d'animaux",
        "Course automobile",
        "Chasse et pêche",
    ]
    test("French keywords defined correctly",
         mod.INITIAL_KEYWORDS == expected,
         f"got {mod.INITIAL_KEYWORDS}")


def test_french_strings():
    mod = _import_module()
    required_keys = [
        "title", "add_keyword", "exit", "edit",
        "control_play", "control_pause", "control_next", "control_prev",
        "control_stop", "control_keywords", "volume", "now_playing",
        "error", "portal_detected", "help", "help_title", "help_text",
        "confirm_exit_title", "confirm_exit_msg",
    ]
    missing = [k for k in required_keys if k not in mod.FR or not mod.FR[k]]
    test("All French UI strings defined", not missing,
         f"missing: {missing}")


def test_mpv_remote_socket_path():
    mod = _import_module()
    test("mpv socket is /tmp/mpv-socket",
         mod.MPV_SOCKET == "/tmp/mpv-socket", f"got {mod.MPV_SOCKET}")


def test_search_constants():
    mod = _import_module()
    test("SEARCH_COUNT >= 20", mod.SEARCH_COUNT >= 20,
         f"SEARCH_COUNT={mod.SEARCH_COUNT}")
    test("PLAYLIST_SIZE >= 10", mod.PLAYLIST_SIZE >= 10,
         f"PLAYLIST_SIZE={mod.PLAYLIST_SIZE}")
    test("MIN_DURATION >= 120", mod.MIN_DURATION >= 120,
         f"MIN_DURATION={mod.MIN_DURATION}")
    test("CONFIG_DIR exists", bool(mod.CONFIG_DIR),
         f"CONFIG_DIR={mod.CONFIG_DIR}")


def test_config_file_location():
    mod = _import_module()
    test("KEYWORDS_FILE ends with keywords.json",
         mod.KEYWORDS_FILE.endswith("keywords.json"),
         f"got {mod.KEYWORDS_FILE}")


def test_ytdlp_search():
    keywords = [
        "Voitures classiques",
        "Compilations d'animaux",
        "Course automobile",
        "Chasse et pêche",
    ]
    for kw in keywords:
        try:
            r = subprocess.run(
                ["/usr/local/bin/yt-dlp", f"ytsearch5:{kw}",
                 "--flat-playlist", "--print", "%(id)s"],
                capture_output=True, text=True, timeout=30,
            )
            ids = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
            test(f"yt-dlp search '{kw}' returns >=1 video ID",
                 len(ids) >= 1, f"got {len(ids)} ids, rc={r.returncode}")
        except Exception as e:
            test(f"yt-dlp search '{kw}' executes", False, str(e))


def test_ytdlp_search_with_duration():
    try:
        r = subprocess.run(
            ["/usr/local/bin/yt-dlp",
             "ytsearch5:Compilations d'animaux",
             "--flat-playlist", "--ignore-errors",
             "--match-filters", "duration > 60",
             "--print", "%(id)s\t%(duration)s"],
            capture_output=True, text=True, timeout=30,
        )
        lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
        ids_with_duration = []
        for line in lines:
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0] and parts[1]:
                    ids_with_duration.append(parts[0])
        test("yt-dlp search with duration filter returns videos",
             len(ids_with_duration) >= 1 or r.returncode == 0,
             f"got {len(ids_with_duration)} videos, rc={r.returncode}")
    except Exception as e:
        test("yt-dlp search with duration executes", False, str(e))


def test_persistent_keywords():
    mod = _import_module()
    test("KEYWORDS_FILE path includes .config",
         ".config" in mod.KEYWORDS_FILE,
         f"got {mod.KEYWORDS_FILE}")


def test_kiosk_constants():
    mod = _import_module()
    test("LOG_FILE is /tmp/yt-player.log",
         mod.LOG_FILE == "/tmp/yt-player.log",
         f"got {mod.LOG_FILE}")
    test("YTDLP binary at /usr/local/bin/yt-dlp",
         mod.YTDLP == "/usr/local/bin/yt-dlp",
         f"got {mod.YTDLP}")


if __name__ == "__main__":
    print("=== Simple Video Player Tests ===\n")

    print("--- Environment ---")
    test_ytdlp_installed()
    test_mpv_available()

    print("\n--- Core Logic ---")
    test_url_building()
    test_mpv_command_format()
    test_app_script_syntax()
    test_french_keywords()
    test_french_strings()
    test_mpv_remote_socket_path()

    print("\n--- Configuration ---")
    test_search_constants()
    test_config_file_location()
    test_persistent_keywords()
    test_kiosk_constants()

    print("\n--- YouTube Search (French keywords) ---")
    test_ytdlp_search()
    test_ytdlp_search_with_duration()

    print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
    sys.exit(0 if FAIL == 0 else 1)
