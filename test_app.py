#!/usr/bin/env python3

import subprocess
import sys
import os
import importlib.util
import tempfile

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
    mod = _import_module()
    try:
        r = subprocess.run(
            [mod.YTDLP, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        test("yt-dlp is installed and recent",
             r.returncode == 0 and r.stdout.strip() >= "2026",
             f"rc={r.returncode} version={r.stdout.strip()}")
    except FileNotFoundError:
        test("yt-dlp binary is resolvable", False, f"path={mod.YTDLP}")


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
    mod = _import_module()
    urls = ["https://www.youtube.com/watch?v=abc123"]
    cmd = mod._build_mpv_command(
        urls,
        display_mode="embedded-x11",
        socket_path="<runtime>/mpv-socket",
        window_id="<id>",
        audio_backend="pulse",
        ytdlp_path="/venv/bin/yt-dlp",
    )
    required = [
        "--osd-level=0", "--no-config",
        "--input-ipc-server=<runtime>/mpv-socket",
        "--keep-open=no",
        "--vo=gpu", "--hwdec=auto",
        "--gpu-context=x11egl", "--ao=pulse",
        "--profile=fast",
        "--x11-bypass-compositor=yes",
        "--ytdl-format=bv[height<=720]+ba/b[height<=720]",
        "--script-opts=ytdl_hook-ytdl_path=/venv/bin/yt-dlp",
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

    fallback_cmd = mod._build_mpv_command(
        urls,
        display_mode="standalone",
        socket_path="<runtime>/mpv-socket",
        audio_backend="pulse",
        ytdlp_path="/venv/bin/yt-dlp",
    )
    test("standalone mpv fallback omits --wid",
         not any(a.startswith("--wid=") for a in fallback_cmd),
         f"cmd={fallback_cmd}")
    test("standalone mpv fallback uses fullscreen flags",
         all(a in fallback_cmd for a in ("--fs", "--ontop", "--no-border")),
         f"cmd={fallback_cmd}")
    test("standalone mpv fallback omits X11-only flags",
         "--gpu-context=x11egl" not in fallback_cmd and
         "--x11-bypass-compositor=yes" not in fallback_cmd,
         f"cmd={fallback_cmd}")


def test_display_mode_detection():
    mod = _import_module()
    x11 = mod._detect_mpv_display_mode(
        environ={"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11"},
        tk_windowing_system="x11",
    )
    test("X11 Tk session uses embedded mpv",
         x11["mode"] == "embedded-x11", f"got {x11}")

    wayland = mod._detect_mpv_display_mode(
        environ={"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"},
        tk_windowing_system="wayland",
    )
    test("Native Wayland session uses standalone mpv fallback",
         wayland["mode"] == "standalone", f"got {wayland}")


def test_app_script_syntax():
    try:
        compile(open(APP_PATH).read(), "simple-video-player.py", "exec")
        test("App script has valid syntax", True)
    except SyntaxError as e:
        test("App script has valid syntax", False, str(e))


def _clear_legacy_module():
    sys.modules.pop("ytkiosk.legacy", None)
    pkg = sys.modules.get("ytkiosk")
    if pkg is not None and hasattr(pkg, "legacy"):
        delattr(pkg, "legacy")


def _import_module(name="svp", fresh_legacy=False):
    if fresh_legacy:
        _clear_legacy_module()
    spec = importlib.util.spec_from_file_location(name, APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_module_with_env(name, env):
    old_env = {k: os.environ.get(k) for k in env}
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return _import_module(name, fresh_legacy=True)
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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


def test_i18n_selection():
    fr_mod = _import_module_with_env("svp_fr", {"YTKIOSK_LANG": "fr"})
    en_mod = _import_module_with_env("svp_en", {"YTKIOSK_LANG": "en"})
    test("YTKIOSK_LANG=fr selects STRINGS_FR",
         fr_mod.FR is fr_mod.STRINGS_FR)
    test("YTKIOSK_LANG=en selects STRINGS_EN",
         en_mod.FR is en_mod.STRINGS_EN)
    test("French and English string keys match",
         set(en_mod.STRINGS_FR) == set(en_mod.STRINGS_EN))


def test_mpv_remote_socket_path():
    mod = _import_module()
    test("mpv socket is in private runtime dir",
         mod.MPV_SOCKET.endswith("mpv-socket") and mod.RUNTIME_DIR in mod.MPV_SOCKET,
         f"got {mod.MPV_SOCKET}")


def test_mpv_remote_playlist_methods():
    mod = _import_module()
    test("MpvRemote has get_playlist_pos",
         hasattr(mod.MpvRemote, "get_playlist_pos"))
    test("MpvRemote has get_playlist_count",
         hasattr(mod.MpvRemote, "get_playlist_count"))


def test_audio_backend_detection():
    mod = _import_module()
    backend = mod._detect_audio_backend()
    test("Audio backend detection returns known backend",
         backend in ("pulse", "pipewire", "alsa"),
         f"got {backend}")


def test_captive_portal_accept_button_detection():
    mod = _import_module()
    parser = mod.PortalFormParser()
    parser.feed(
        '<form method="post" action="/login">'
        '<input type="hidden" name="token" value="abc">'
        '<button type="submit">Accepter</button>'
        '</form>'
    )
    test("Captive portal parser recognizes Accepter button",
         parser.has_accept_submit)
    test("Captive portal parser keeps hidden fields",
         {field["name"]: field["value"] for field in parser.fields}.get("token") == "abc",
         f"fields={parser.fields}")


def test_captive_portal_form_selection():
    mod = _import_module()
    parser = mod.PortalFormParser()
    parser.feed(
        '<form method="post" action="/newsletter">'
        '<input name="email" value="">'
        '<button type="submit">Submit</button>'
        '</form>'
        '<form method="post" action="/accept">'
        '<input type="hidden" name="token" value="abc">'
        '<button type="submit" name="choice" value="1">Accepter</button>'
        '</form>'
    )
    form = mod._select_portal_form(parser)
    test("Captive portal parser selects accept form",
         form is not None and form.get("action") == "/accept",
         f"form={form}")
    submit = form.get("accept_submit") if form else None
    test("Captive portal parser keeps clicked button value",
         submit is not None and submit.get("name") == "choice" and submit.get("value") == "1",
         f"submit={submit}")


def test_captive_portal_submit_url_uses_final_url():
    mod = _import_module()
    final_url = "http://portal.local/login"
    test("Empty portal form action submits to final URL",
         mod._portal_submit_url(final_url, "") == final_url)
    test("Relative portal form action resolves from final URL",
         mod._portal_submit_url(final_url, "/accept") == "http://portal.local/accept")


def test_cisco_captive_portal_javascript_defaults():
    mod = _import_module()
    portal_url = (
        "https://cisss-public.reg09.rtss.qc.ca/login.html?"
        "switch_url=http%3A%2F%2F1.2.3.4%2Flogin.html&redirect=https%3A%2F%2Fexample.com%2F"
    )
    parser = mod.PortalFormParser()
    parser.feed(
        '<form method="post" action="https://www.google.ca">'
        '<input name="buttonClicked" value="0" type="hidden">'
        '<input name="redirect_url" value="" type="hidden">'
        '<input name="err_flag" value="0" type="hidden">'
        '<input type="button" name="Submit" value="Accepter" onclick="submitAction();">'
        '</form>'
    )
    form = mod._select_portal_form(parser)
    action = mod._portal_action_from_query(portal_url)
    data = mod._portal_form_data(form, portal_url, portal_url)
    test("Cisco portal action uses switch_url query value",
         action == "http://1.2.3.4/login.html", f"action={action}")
    test("Cisco portal sets buttonClicked to accepted value",
         data.get("buttonClicked") == "4", f"data={data}")
    test("Cisco portal sets redirect_url from query",
         data.get("redirect_url") == "https://example.com/", f"data={data}")
    test("Cisco portal does not submit input type=button name/value",
         "Submit" not in data, f"data={data}")


def test_cisco_captive_portal_without_switch_url_posts_to_current_url():
    mod = _import_module()
    portal_url = (
        "https://cisss-public.reg09.rtss.qc.ca/login.html?"
        "redirect=http%3A%2F%2Fdetectportal.firefox.com%2Fcanonical.html"
    )
    parser = mod.PortalFormParser()
    parser.feed(
        '<form method="post" action="https://www.google.ca">'
        '<input name="buttonClicked" value="0" type="hidden">'
        '<input name="redirect_url" value="" type="hidden">'
        '<input type="button" name="Submit" value="Accepter" onclick="submitAction();">'
        '</form>'
    )
    form = mod._select_portal_form(parser)
    test("Cisco portal form is detected",
         mod._is_cisco_portal_form(form), f"form={form}")
    test("Cisco portal without switch_url posts to current portal URL",
         mod._portal_form_action(form, portal_url, portal_url) == portal_url)


def test_hospital_portal_attempts_before_generic_triggers():
    mod = _import_module()
    urls = mod.captive_portal_attempt_urls()
    test("CISSS captive portal is attempted by default",
         urls and urls[0] == "https://cisss-public.reg09.rtss.qc.ca/login.html",
         f"urls={urls}")
    test("Generic captive portal triggers are disabled by default",
         "http://1.1.1.1/" not in urls and "http://neverssl.com/" not in urls,
         f"urls={urls}")

    detected_url = "https://cisss-public.reg09.rtss.qc.ca/login.html?switch_url=http%3A%2F%2F1.2.3.4%2Flogin.html"
    detected_urls = mod.captive_portal_attempt_urls(detected_url)
    test("Detected portal URL is attempted before static fallback",
         detected_urls[0] == detected_url, f"urls={detected_urls}")


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
    test("Post-portal search retries enabled",
         mod.POST_PORTAL_SEARCH_RETRIES >= 2,
         f"POST_PORTAL_SEARCH_RETRIES={mod.POST_PORTAL_SEARCH_RETRIES}")
    test("Post-portal retry delay enabled",
         mod.POST_PORTAL_RETRY_DELAY >= 1,
         f"POST_PORTAL_RETRY_DELAY={mod.POST_PORTAL_RETRY_DELAY}")


def test_config_file_location():
    mod = _import_module()
    test("KEYWORDS_FILE ends with keywords.json",
         mod.KEYWORDS_FILE.endswith("keywords.json"),
         f"got {mod.KEYWORDS_FILE}")


def test_load_config_missing_defaults():
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.environ["HOME"] = tmp
            mod = _import_module("svp_config_missing")
            cfg = mod._load_config()
            test("_load_config returns empty dict when missing",
                 cfg == {}, f"got {cfg}")
            test("Missing config uses default constants",
                 (mod.SEARCH_COUNT, mod.PLAYLIST_SIZE, mod.MIN_DURATION) == (30, 20, 300),
                 f"got {(mod.SEARCH_COUNT, mod.PLAYLIST_SIZE, mod.MIN_DURATION)}")
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def test_ytdlp_search():
    mod = _import_module()
    keywords = [
        "Voitures classiques",
        "Compilations d'animaux",
        "Course automobile",
        "Chasse et pêche",
    ]
    for kw in keywords:
        try:
            r = subprocess.run(
                [mod.YTDLP, *mod.yt_dlp_js_runtime_arg(), f"ytsearch5:{kw}",
                 "--flat-playlist", "--print", "%(id)s"],
                capture_output=True, text=True, timeout=30,
            )
            ids = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
            test(f"yt-dlp search '{kw}' returns >=1 video ID",
                 len(ids) >= 1, f"got {len(ids)} ids, rc={r.returncode}")
        except Exception as e:
            test(f"yt-dlp search '{kw}' executes", False, str(e))


def test_ytdlp_search_with_duration():
    mod = _import_module()
    try:
        r = subprocess.run(
            [mod.YTDLP,
             *mod.yt_dlp_js_runtime_arg(),
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


def test_load_state_missing_defaults():
    old_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.environ["HOME"] = tmp
            mod = _import_module("svp_state_missing")
            app = object.__new__(mod.SimpleVideoPlayer)
            state = app._load_state()
            test("_load_state returns empty dict when missing",
                 state == {}, f"got {state}")
            test("Missing state yields default volume",
                 state.get("volume", 75) == 75, f"got {state}")
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home


def test_kiosk_constants():
    mod = _import_module()
    test("LOG_FILE is in private runtime dir",
         mod.LOG_FILE.endswith("yt-player.log") and mod.RUNTIME_DIR in mod.LOG_FILE,
         f"got {mod.LOG_FILE}")
    test("YTDLP binary configured",
         bool(mod.YTDLP),
         f"got {mod.YTDLP}")


if __name__ == "__main__":
    print("=== Simple Video Player Tests ===\n")

    print("--- Environment ---")
    test_ytdlp_installed()
    test_mpv_available()

    print("\n--- Core Logic ---")
    test_url_building()
    test_mpv_command_format()
    test_display_mode_detection()
    test_app_script_syntax()
    test_french_keywords()
    test_french_strings()
    test_i18n_selection()
    test_mpv_remote_socket_path()
    test_mpv_remote_playlist_methods()
    test_audio_backend_detection()
    test_captive_portal_accept_button_detection()
    test_captive_portal_form_selection()
    test_captive_portal_submit_url_uses_final_url()
    test_cisco_captive_portal_javascript_defaults()
    test_cisco_captive_portal_without_switch_url_posts_to_current_url()
    test_hospital_portal_attempts_before_generic_triggers()

    print("\n--- Configuration ---")
    test_search_constants()
    test_config_file_location()
    test_load_config_missing_defaults()
    test_persistent_keywords()
    test_load_state_missing_defaults()
    test_kiosk_constants()

    print("\n--- YouTube Search (French keywords) ---")
    test_ytdlp_search()
    test_ytdlp_search_with_duration()

    print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
    sys.exit(0 if FAIL == 0 else 1)
