#!/usr/bin/env python3

import tkinter as tk
from tkinter import simpledialog, messagebox
import subprocess
import threading
import time
import os
import json
import locale
import socket
import urllib.request
import urllib.error
import html.parser
import tempfile
import shutil
from urllib.parse import urljoin, urlparse, urlencode
import random

CONFIG_DIR = os.path.expanduser("~/.config/yt-player")
RUNTIME_DIR = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(),
    f"yt-player-{os.getuid()}"
)


def _ensure_runtime_dir():
    os.makedirs(RUNTIME_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(RUNTIME_DIR, 0o700)
    except OSError:
        pass


def _load_config():
    try:
        path = os.path.join(CONFIG_DIR, "config.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


_cfg = _load_config()
KEYWORDS_FILE = os.path.join(CONFIG_DIR, "keywords.json")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
_ensure_runtime_dir()
LOG_FILE = os.path.join(RUNTIME_DIR, "yt-player.log")
MPV_SOCKET = os.path.join(RUNTIME_DIR, "mpv-socket")
MPV_LOG_FILE = os.path.join(RUNTIME_DIR, "mpv-embed.log")


def _cfg_path(name, fallback_name, default):
    value = _cfg.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return shutil.which(fallback_name) or default


MPV = _cfg_path("mpv_path", "mpv", "/usr/bin/mpv")
YTDLP = _cfg_path("ytdlp_path", "yt-dlp", "/usr/local/bin/yt-dlp")


def _cfg_int(name, default, minimum):
    try:
        value = int(_cfg.get(name, default))
        return value if value >= minimum else default
    except (TypeError, ValueError):
        return default


SEARCH_COUNT = _cfg_int("search_count", 30, 1)
PLAYLIST_SIZE = _cfg_int("playlist_size", 20, 1)
MIN_DURATION = _cfg_int("min_duration", 300, 0)
_log_lock = threading.Lock()


def _detect_audio_backend():
    try:
        result = subprocess.run(
            ["pactl", "info"], capture_output=True, text=True, timeout=3
        )
        if "PipeWire" in result.stdout:
            return "pipewire"
        if result.returncode == 0:
            return "pulse"
    except Exception:
        pass
    return "alsa"


def log(msg):
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


log("=== App started ===")

STRINGS_FR = {
    "title": "Lecteur Vidéo Simple",
    "add_keyword": "+ Ajouter un mot-clé",
    "exit": "QUITTER",
    "edit": "✎",
    "edit_title": "Modifier le mot-clé",
    "edit_prompt": "Entrez un nouveau mot-clé :",
    "add_title": "Ajouter un mot-clé",
    "add_prompt": "Entrez un mot-clé à rechercher :",
    "no_videos": "Aucune vidéo trouvée pour « {} »",
    "ytdlp_failed": "Échec de recherche :\n{}",
    "mpv_exited": "mpv s'est arrêté (code {})",
    "error": "Erreur",
    "fetching": "Recherche de vidéos pour :\n{}",
    "starting": "Lecture lancée pour : {}",
    "killed": "Ancien mpv terminé",
    "selecting": "Sélection des meilleures vidéos...",
    "launching": "Lancement avec {} vidéos",
    "mpv_ok": "mpv en cours d'exécution",
    "mpv_dead": "mpv arrêté prématurément (code {})",
    "control_play": "▶",
    "control_pause": "⏸",
    "control_next": "⏭",
    "control_prev": "⏮",
    "control_stop": "Arrêter",
    "control_keywords": "Mots-clés",
    "volume": "Volume",
    "now_playing": "En cours :",
    "portal_detected": "Portail captif détecté",
    "portal_msg": "Un portail captif bloque l'accès. Ouverture du navigateur pour connexion...",
    "portal_success": "Connexion rétablie !",
    "portal_fail": "Impossible de se connecter au portail captif.",
    "portal_auto_ok": "Portail accepté automatiquement !",
    "connectivity_check": "Vérification de la connexion...",
    "retry": "Réessayer",
    "cancel": "Annuler",
    "help": "Aide",
    "help_title": "Aide - Lecteur Vidéo Simple",
    "help_text": (
        "Ce programme permet de regarder des vidéos YouTube sur des thèmes choisis.\n\n"
        "--- POUR LES SOIGNANTS ---\n\n"
        "1. Cliquez sur un mot-clé pour lancer la lecture automatique\n"
        "2. ✎ permet de modifier un mot-clé\n"
        "3. « + Ajouter un mot-clé » pour ajouter un nouveau thème\n\n"
        "PENDANT LA LECTURE :\n"
        "  ▶/⏸  Lecture / Pause\n"
        "  ⏮    Vidéo précédente\n"
        "  ⏭    Vidéo suivante\n"
        "  Volume  Curseur pour régler le son\n"
        "  Arrêter  Arrête la lecture\n"
        "  Mots-clés  Retour à la liste des thèmes\n\n"
        "Les vidéos longues sont prioritaires.\n"
        "La liste de lecture est mélangée aléatoirement.\n"
        "Les mots-clés sont sauvegardés automatiquement.\n\n"
        "POUR QUITTER : cliquez sur QUITTER puis confirmez."
    ),
    "confirm_exit_title": "Confirmation",
    "confirm_exit_msg": "Êtes-vous sûr de vouloir quitter ?",
    "yes": "Oui",
    "no": "Non",
    "loading_duration": "Vérification des durées...",
    "playlist_ended": "Liste de lecture terminée",
}

STRINGS_EN = {
    "title": "Simple Video Player",
    "add_keyword": "+ Add keyword",
    "exit": "QUIT",
    "edit": "✎",
    "edit_title": "Edit keyword",
    "edit_prompt": "Enter a new keyword:",
    "add_title": "Add keyword",
    "add_prompt": "Enter a keyword to search:",
    "no_videos": "No videos found for '{}'",
    "ytdlp_failed": "Search failed:\n{}",
    "mpv_exited": "mpv stopped (code {})",
    "error": "Error",
    "fetching": "Searching videos for:\n{}",
    "starting": "Starting playback for: {}",
    "killed": "Previous mpv stopped",
    "selecting": "Selecting best videos...",
    "launching": "Launching with {} videos",
    "mpv_ok": "mpv running",
    "mpv_dead": "mpv stopped early (code {})",
    "control_play": "▶",
    "control_pause": "⏸",
    "control_next": "⏭",
    "control_prev": "⏮",
    "control_stop": "Stop",
    "control_keywords": "Keywords",
    "volume": "Volume",
    "now_playing": "Now playing:",
    "portal_detected": "Captive portal detected",
    "portal_msg": "A captive portal is blocking access. Opening browser to connect...",
    "portal_success": "Connection restored!",
    "portal_fail": "Could not connect to captive portal.",
    "portal_auto_ok": "Portal accepted automatically!",
    "connectivity_check": "Checking connection...",
    "retry": "Retry",
    "cancel": "Cancel",
    "help": "Help",
    "help_title": "Help - Simple Video Player",
    "help_text": (
        "This program lets users watch YouTube videos based on selected themes.\n\n"
        "--- FOR CAREGIVERS ---\n\n"
        "1. Click a keyword to start automatic playback\n"
        "2. ✎ lets you edit a keyword\n"
        "3. \"+ Add keyword\" lets you add a new theme\n\n"
        "DURING PLAYBACK:\n"
        "  ▶/⏸  Play / Pause\n"
        "  ⏮    Previous video\n"
        "  ⏭    Next video\n"
        "  Volume  Slider to adjust the sound\n"
        "  Stop    Stops playback\n"
        "  Keywords  Return to the theme list\n\n"
        "Long videos are prioritized.\n"
        "The playlist is shuffled randomly.\n"
        "Keywords are saved automatically.\n\n"
        "TO EXIT: click EXIT, then confirm."
    ),
    "confirm_exit_title": "Confirm",
    "confirm_exit_msg": "Are you sure you want to quit?",
    "yes": "Yes",
    "no": "No",
    "loading_duration": "Checking durations...",
    "playlist_ended": "Playlist ended",
}

_locale = locale.getlocale()
_default_lang = _locale[0] if isinstance(_locale, tuple) else _locale
_lang = os.environ.get("YTKIOSK_LANG", _default_lang or "en")
FR = STRINGS_FR if _lang.startswith("fr") else STRINGS_EN

INITIAL_KEYWORDS = [
    "Voitures classiques",
    "Compilations d'animaux",
    "Course automobile",
    "Chasse et pêche",
]


class MpvRemote:
    def __init__(self, socket_path=MPV_SOCKET):
        self.socket_path = socket_path

    def _send(self, command, args=None):
        if args is None:
            args = []
        msg = json.dumps({"command": [command] + args}) + "\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect(self.socket_path)
                sock.sendall(msg.encode())
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
            resp = json.loads(data.decode())
            if not isinstance(resp, dict):
                return None
            if resp.get("error") != "success":
                return None
            return resp.get("data")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, TimeoutError):
            return None

    def toggle_pause(self):
        self._send("cycle", ["pause"])

    def next_track(self):
        self._send("playlist-next")

    def prev_track(self):
        self._send("playlist-prev")

    def set_volume(self, val):
        self._send("set_property", ["volume", float(val)])

    def get_volume(self):
        return self._send("get_property", ["volume"])

    def get_pause_state(self):
        return self._send("get_property", ["pause"])

    def get_media_title(self):
        return self._send("get_property", ["media-title"])

    def get_playlist_pos(self):
        return self._send("get_property", ["playlist-pos"])

    def get_playlist_count(self):
        return self._send("get_property", ["playlist-count"])

    def is_running(self):
        return self._send("get_property", ["time-pos"]) is not None

    def stop(self):
        self._send("stop")


PROBE_URLS = [
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://captive.apple.com/hotspot-detect.html",
    "http://detectportal.firefox.com/success.txt",
    "http://connectivity-check.ubuntu.com/generate_204",
]

EXPECTED = {
    "http://connectivitycheck.gstatic.com/generate_204": (204, None),
    "http://captive.apple.com/hotspot-detect.html": (200, "Success"),
    "http://detectportal.firefox.com/success.txt": (200, "success"),
    "http://connectivity-check.ubuntu.com/generate_204": (204, None),
}


def detect_captive_portal():
    for url in PROBE_URLS:
        expected_status, expected_text = EXPECTED.get(url, (200, None))
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64)")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                actual_status = resp.status
                if actual_status != expected_status:
                    portal_url = resp.url if resp.url != url else None
                    return True, portal_url, url
                if expected_text:
                    body = resp.read(300).decode("utf-8", errors="replace")
                    if expected_text not in body:
                        portal_url = resp.url if resp.url != url else None
                        return True, portal_url, url
        except urllib.error.HTTPError as e:
            try:
                if e.code in (301, 302, 303, 307, 308):
                    portal_url = e.headers.get("Location")
                    if portal_url:
                        abs_url = urljoin(url, portal_url)
                        return True, abs_url, url
                return False, None, url
            finally:
                e.close()
        except (urllib.error.URLError, OSError, ValueError):
            return False, None, url
    return False, None, None


class PortalFormParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.form_action = None
        self.fields = []
        self._in_form = False
        self._current = {}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form":
            self._in_form = True
            self.form_action = d.get("action")
        if self._in_form and tag == "input":
            field = {
                "name": d.get("name", ""),
                "value": d.get("value", ""),
                "type": d.get("type", ""),
            }
            if field.get("name"):
                self.fields.append(field)
        if self._in_form and tag == "button" and d.get("type") == "submit":
            field = {
                "name": d.get("name", ""),
                "value": d.get("value", "submit"),
                "type": "submit",
            }
            if field.get("name"):
                self.fields.append(field)

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False


def try_auto_accept(portal_url, base_url=None):
    try:
        req = urllib.request.Request(portal_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html_content = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return False

    parser = PortalFormParser()
    parser.feed(html_content)

    action = parser.form_action
    if not action:
        return False

    post_url = urljoin(base_url or portal_url, action)
    data = {}
    for f in parser.fields:
        name = f.get("name", "")
        val = f.get("value", "")
        ftype = f.get("type", "")
        if name:
            if ftype == "checkbox":
                lv = val.lower()
                if lv in ("", "agree", "accept", "yes", "1", "true"):
                    data[name] = val if val else "agree"
            elif ftype == "submit":
                data[name] = val if val else "Submit"
            else:
                data[name] = val if val else ""

    if not data:
        return False

    encoded = urlencode(data).encode()
    try:
        req2 = urllib.request.Request(
            post_url, data=encoded, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req2, timeout=10):
            pass
        return True
    except Exception:
        return False


def handle_captive_portal(root, on_done):
    def _run():
        is_captive, portal_url, _ = detect_captive_portal()
        if not is_captive:
            root.after(0, lambda: on_done(True, None))
            return
        log("Captive portal detected")
        root.after(0, lambda: _show_portal_dialog(portal_url, on_done))

    def _show_portal_dialog(portal_url, on_done):
        dlg = tk.Toplevel(root)
        dlg.title(FR["portal_detected"])
        dlg.geometry("500x300")
        dlg.resizable(False, False)
        dlg.transient(root)
        dlg.grab_set()

        msg = tk.Message(dlg, text=FR["portal_msg"], font=("TkDefaultFont", 14), width=460)
        msg.pack(pady=20)

        status_var = tk.StringVar(value=FR["connectivity_check"])
        status_lbl = tk.Label(dlg, textvariable=status_var, font=("TkDefaultFont", 12))
        status_lbl.pack(pady=5)

        def _try_auto():
            status_var.set("Tentative d'acceptation automatique...")
            dlg.update()
            accepted = try_auto_accept(portal_url) if portal_url else False
            if accepted:
                time.sleep(1)
                still = detect_captive_portal()[0]
                if not still:
                    status_var.set(FR["portal_auto_ok"])
                    dlg.after(1000, lambda: _done(True))
                    return
            _open_browser(portal_url)

        def _open_browser(url):
            status_var.set("Ouverture du navigateur...")
            open_url = url or PROBE_URLS[0]
            if urlparse(open_url).scheme not in ("http", "https"):
                _done(False)
                return
            try:
                subprocess.Popen(
                    ["xdg-open", open_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                log(f"Failed to open portal browser: {e}")
                _done(False)
                return
            _poll()

        def _poll():
            is_captive, _, _ = detect_captive_portal()
            if not is_captive:
                status_var.set(FR["portal_success"])
                dlg.after(1000, lambda: _done(True))
                return
            dlg.after(2000, _poll)

        def _done(ok):
            try:
                dlg.destroy()
            except tk.TclError:
                pass
            on_done(ok, "Portail non accepté" if not ok else None)

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=10)
        tk.Button(
            btn_frame, text=FR["retry"], font=("TkDefaultFont", 14),
            command=lambda: _done(True)
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame, text=FR["cancel"], font=("TkDefaultFont", 14),
            command=lambda: _done(False)
        ).pack(side=tk.LEFT, padx=10)

        _try_auto()

    threading.Thread(target=_run, daemon=True).start()


class SimpleVideoPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title(FR["title"])

        self.keywords = self._load_keywords()
        self.mpv_proc = None
        self.current_keyword = None
        self.mpv = MpvRemote()
        self._paused = False
        self._volume = 75
        self._volume = self._load_state().get("volume", 75)
        self._playing = False
        self._loading = False
        self._playlist_ending = False
        self._volume_save_after_id = None
        self._session_id = 0

        self._setup_kiosk()
        self._build_ui()

        self._poll_mpv()
        log("UI ready")

    def _setup_kiosk(self):
        self.root.attributes("-fullscreen", True)
        self.root.focus_force()

        self.root.protocol("WM_DELETE_WINDOW", self._confirm_exit)

        try:
            subprocess.run(
                ["xset", "s", "off", "-dpms"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception:
            pass

        for key in ("<Escape>", "<F11>", "<Control-q>"):
            self.root.bind(key, lambda e: "break")

    def _build_ui(self):
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        self.top_bar = tk.Frame(self.root, bg="#2a2a2a")
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self._build_top_bar()

        self.main_area = tk.Frame(self.root, bg="black")
        self.main_area.grid(row=1, column=0, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        self.keyword_frame = tk.Frame(self.main_area, bg="#1a1a1a")
        self.keyword_frame.grid(row=0, column=0, sticky="nsew")
        self._build_keyword_view()

        self.video_frame = tk.Frame(self.main_area, bg="black")
        self.video_frame.grid(row=0, column=0, sticky="nsew")
        self.video_frame.grid_remove()

        self.loading_label = tk.Label(
            self.main_area, text="", font=("TkDefaultFont", 24),
            fg="#aaaaaa", bg="black", justify=tk.CENTER,
        )
        self.loading_label.grid(row=0, column=0, sticky="nsew")
        self.loading_label.grid_remove()

        self.control_bar = tk.Frame(self.root, bg="#2a2a2a")
        self.control_bar.grid(row=2, column=0, sticky="ew")
        self._build_controls()
        self._set_controls_enabled(False)

    def _build_top_bar(self):
        self.help_btn = tk.Button(
            self.top_bar, text=FR["help"], font=("TkDefaultFont", 14),
            command=self._show_help, bg="#444", fg="white",
            relief=tk.FLAT, padx=15, pady=5,
        )
        self.help_btn.pack(side=tk.LEFT, padx=10, pady=5)

        self.status_label = tk.Label(
            self.top_bar, text="", font=("TkDefaultFont", 11),
            fg="#aaaaaa", bg="#2a2a2a", anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15)

        self.exit_btn = tk.Button(
            self.top_bar, text=FR["exit"], font=("TkDefaultFont", 14, "bold"),
            command=self._confirm_exit, bg="#cc0000", fg="white",
            relief=tk.FLAT, padx=20, pady=5,
        )
        self.exit_btn.pack(side=tk.RIGHT, padx=10, pady=5)

    def _build_keyword_view(self):
        container = tk.Frame(self.keyword_frame, bg="#1a1a1a")
        container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        title_lbl = tk.Label(
            container, text=FR["title"], font=("TkDefaultFont", 26, "bold"),
            fg="white", bg="#1a1a1a",
        )
        title_lbl.pack(pady=(0, 20))

        inner_frame = tk.Frame(container, bg="#1a1a1a")
        inner_frame.pack(fill=tk.BOTH, expand=True)

        self.kw_canvas = tk.Canvas(inner_frame, highlightthickness=0, bg="#1a1a1a")
        self.kw_scroll = tk.Scrollbar(
            inner_frame, orient="vertical", command=self.kw_canvas.yview,
        )
        self.kw_scrollable = tk.Frame(self.kw_canvas, bg="#1a1a1a")

        self.kw_scrollable.bind(
            "<Configure>",
            lambda e: self.kw_canvas.configure(
                scrollregion=self.kw_canvas.bbox("all")
            ),
        )
        self.kw_canvas.create_window((0, 0), window=self.kw_scrollable, anchor="nw")
        self.kw_canvas.configure(yscrollcommand=self.kw_scroll.set)

        self.kw_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.kw_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._rebuild_keyword_buttons()

    def _rebuild_keyword_buttons(self):
        for w in self.kw_scrollable.winfo_children():
            w.destroy()

        for i, kw in enumerate(self.keywords):
            row = tk.Frame(self.kw_scrollable, bg="#1a1a1a")
            row.pack(fill=tk.X, pady=4)

            btn = tk.Button(
                row, text=kw, font=("TkDefaultFont", 20),
                command=lambda k=kw: self._on_keyword_click(k),
                bg="#333", fg="white", relief=tk.RAISED, padx=10, pady=8,
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

            edit_btn = tk.Button(
                row, text=FR["edit"], font=("TkDefaultFont", 14),
                width=3, command=lambda idx=i: self._edit_keyword(idx),
                bg="#555", fg="white", relief=tk.RAISED, pady=8,
            )
            edit_btn.pack(side=tk.RIGHT, padx=(5, 0))

        add_btn = tk.Button(
            self.kw_scrollable, text=FR["add_keyword"],
            font=("TkDefaultFont", 18),
            command=self._on_add_keyword,
            bg="#2a6b2a", fg="white", relief=tk.RAISED, padx=10, pady=8,
        )
        add_btn.pack(fill=tk.X, pady=(12, 0))

    def _edit_keyword(self, idx):
        old = self.keywords[idx]
        new = simpledialog.askstring(
            FR["edit_title"], FR["edit_prompt"],
            initialvalue=old, parent=self.root,
        )
        if new and new.strip():
            self.keywords[idx] = new.strip()
            self._rebuild_keyword_buttons()
            self._save_keywords()

    def _on_add_keyword(self):
        kw = simpledialog.askstring(
            FR["add_title"], FR["add_prompt"], parent=self.root,
        )
        if kw and kw.strip():
            self.keywords.append(kw.strip())
            self._rebuild_keyword_buttons()
            self._save_keywords()

    def _build_controls(self):
        inner = tk.Frame(self.control_bar, bg="#2a2a2a")
        inner.pack(fill=tk.X, padx=15, pady=8)

        self.prev_btn = tk.Button(
            inner, text=FR["control_prev"], font=("TkDefaultFont", 20),
            width=3, command=self._prev_track,
            bg="#444", fg="white", relief=tk.RAISED,
        )
        self.prev_btn.pack(side=tk.LEFT, padx=3)

        self.play_btn = tk.Button(
            inner, text=FR["control_play"], font=("TkDefaultFont", 20),
            width=3, command=self._toggle_pause,
            bg="#444", fg="white", relief=tk.RAISED,
        )
        self.play_btn.pack(side=tk.LEFT, padx=3)

        self.next_btn = tk.Button(
            inner, text=FR["control_next"], font=("TkDefaultFont", 20),
            width=3, command=self._next_track,
            bg="#444", fg="white", relief=tk.RAISED,
        )
        self.next_btn.pack(side=tk.LEFT, padx=3)

        vol_frame = tk.Frame(inner, bg="#2a2a2a")
        vol_frame.pack(side=tk.LEFT, padx=(20, 10))
        tk.Label(
            vol_frame, text=FR["volume"], font=("TkDefaultFont", 12),
            fg="white", bg="#2a2a2a",
        ).pack(side=tk.TOP, anchor="center")
        self.vol_scale = tk.Scale(
            vol_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            showvalue=True, width=18, length=160,
            command=self._on_volume_change,
            bg="#444", fg="white", troughcolor="#666",
        )
        self.vol_scale.set(self._volume)
        self.vol_scale.pack()

        self.now_playing_label = tk.Label(
            inner, text="", font=("TkDefaultFont", 12),
            fg="#aaaaaa", bg="#2a2a2a", anchor="w",
        )
        self.now_playing_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(15, 0))

        self.keyword_btn = tk.Button(
            inner, text=FR["control_keywords"], font=("TkDefaultFont", 14),
            command=self._show_keywords_mode,
            bg="#5a5a5a", fg="white", relief=tk.RAISED, padx=10, pady=5,
        )
        self.keyword_btn.pack(side=tk.RIGHT, padx=3)

        self.stop_btn = tk.Button(
            inner, text=FR["control_stop"], font=("TkDefaultFont", 14),
            command=self._stop_playback,
            bg="#aa3333", fg="white", relief=tk.RAISED, padx=10, pady=5,
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=3)

    def _set_controls_enabled(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for b in (self.prev_btn, self.play_btn, self.next_btn, self.stop_btn):
            b.config(state=state)
        self.vol_scale.config(state=state)

    def _show_keyword_view(self):
        self.video_frame.grid_remove()
        self.loading_label.grid_remove()
        self.keyword_frame.grid()
        self.status_label.config(text="")
        self.now_playing_label.config(text="")

    def _show_video_view(self):
        self.keyword_frame.grid_remove()
        self.loading_label.grid_remove()
        self.video_frame.grid()
        self.root.update_idletasks()
        self.root.update()

    def _ensure_video_frame_sized(self):
        for _ in range(10):
            self.root.update_idletasks()
            self.root.update()
            w = self.video_frame.winfo_width()
            h = self.video_frame.winfo_height()
            if w > 10 and h > 10:
                return w, h
            time.sleep(0.05)
        fw = max(self.main_area.winfo_width(), 640)
        fh = max(self.main_area.winfo_height(), 480)
        log(f"Forcing video frame size to {fw}x{fh}")
        self.video_frame.config(width=fw, height=fh)
        self.root.update_idletasks()
        return self.video_frame.winfo_width(), self.video_frame.winfo_height()

    def _show_loading(self, text):
        self.keyword_frame.grid_remove()
        self.video_frame.grid_remove()
        self.loading_label.config(text=text)
        self.loading_label.grid()
        self.root.update_idletasks()

    # ── Search and playback ─────────────────────────────────────

    def _on_keyword_click(self, keyword):
        if self._loading:
            return
        if self._playing:
            self._stop_playback()
        self._session_id += 1
        session_id = self._session_id
        self.current_keyword = keyword
        self._playlist_ending = False
        self._loading = True
        self._show_loading(FR["fetching"].format(keyword))
        threading.Thread(
            target=self._play_keyword, args=(keyword, session_id), daemon=True
        ).start()

    def _play_keyword(self, keyword, session_id):
        try:
            log(FR["starting"].format(keyword))

            is_captive, _, _ = detect_captive_portal()
            if is_captive:
                log("Captive portal detected before playback")
                wait = threading.Event()
                result = [False]

                def _on_portal_done(ok, err):
                    result[0] = ok
                    wait.set()

                self.root.after(
                    0, lambda: handle_captive_portal(self.root, _on_portal_done)
                )
                wait.wait(timeout=120)
                if not result[0]:
                    self._schedule_error(FR["portal_fail"], session_id)
                    return
            if not self._is_active_session(session_id):
                return

            urls = self._fetch_playlist(keyword)

            if not urls:
                self._schedule_error(FR["no_videos"].format(keyword), session_id)
                return

            log(FR["launching"].format(len(urls)))
            self.root.after(0, lambda: self._start_mpv(urls, session_id))

        except Exception as e:
            log(f"EXCEPTION: {e}")
            import traceback
            log(traceback.format_exc())
            self._schedule_error(str(e), session_id)

    def _fetch_playlist(self, keyword):
        log(FR["fetching"].format(keyword))

        try:
            result = subprocess.run(
                [
                    YTDLP,
                    f"ytsearch{SEARCH_COUNT}:{keyword}",
                    "--flat-playlist",
                    "--ignore-errors",
                    "--match-filters", f"duration > {MIN_DURATION} & !is_live",
                    "--retries", "5",
                    "--fragment-retries", "5",
                    "--socket-timeout", "15",
                    "--print", "%(id)s\t%(duration)s",
                ],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise Exception("Search timed out. Check network connection.")
        log(f"yt-dlp rc={result.returncode}")

        if result.returncode != 0:
            log(f"yt-dlp stderr: {result.stderr[:300]}")
            raise Exception(FR["ytdlp_failed"].format(result.stderr[:200]))

        candidates = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if "\t" in line:
                parts = line.split("\t")
                if len(parts) >= 2 and parts[0] and parts[1]:
                    try:
                        vid = parts[0].strip()
                        dur = int(float(parts[1].strip()))
                        if dur > MIN_DURATION:
                            candidates.append((vid, dur))
                    except (ValueError, IndexError):
                        pass

        log(f"Found {len(candidates)} videos > {MIN_DURATION}s")

        if not candidates:
            raise Exception(FR["no_videos"].format(keyword))

        candidates.sort(key=lambda x: x[1], reverse=True)

        selected = candidates[:PLAYLIST_SIZE]
        random.shuffle(selected)

        urls = [f"https://www.youtube.com/watch?v={vid}" for vid, _ in selected]
        log(f"Playlist: {[v for v, _ in selected]}")
        return urls

    def _start_mpv(self, urls, session_id):
        if not self._is_active_session(session_id):
            return
        self._show_video_view()
        fw, fh = self._ensure_video_frame_sized()
        wid = self.video_frame.winfo_id()
        log(f"Video frame X11 ID: {wid} size={fw}x{fh}")

        env = os.environ.copy()
        env["PATH"] = f"/usr/local/bin:{env.get('PATH', '/usr/bin')}"

        cmd = [
            MPV, "--osd-level=0",
            f"--wid={wid}",
            "--no-config",
            f"--input-ipc-server={MPV_SOCKET}",
            "--keep-open=no",
            # Fallback for Wayland/no-GPU edge cases: replace with "--vo=x11".
            "--vo=gpu",
            "--hwdec=auto",
            "--gpu-context=x11egl",
            f"--ao={_detect_audio_backend()}",
            "--profile=fast",
            "--x11-bypass-compositor=yes",
            "--ytdl-format=bv[height<=720]+ba/b[height<=720]",
        ] + urls

        try:
            os.unlink(MPV_SOCKET)
        except OSError:
            pass

        try:
            with open(MPV_LOG_FILE, "w") as mpv_log:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=mpv_log, env=env,
                )
        except Exception as e:
            log(f"Failed to launch mpv: {e}")
            self._on_error(str(e), session_id)
            return
        self.mpv_proc = proc
        log(f"mpv pid={proc.pid}")

        threading.Thread(
            target=self._wait_for_mpv, args=(proc, session_id), daemon=True
        ).start()

    def _wait_for_mpv(self, proc, session_id):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not self._is_active_session(session_id, proc):
                return
            if proc.poll() is not None:
                code = proc.returncode
                log(FR["mpv_dead"].format(code))
                self.root.after(
                    0,
                    lambda code=code: self._on_error(
                        FR["mpv_exited"].format(code), session_id
                    ),
                )
                return
            if self.mpv.is_running():
                self.root.after(0, lambda: self._on_mpv_ready(proc, session_id))
                return
            time.sleep(0.2)
        self.root.after(
            0, lambda: self._on_error("mpv did not respond within 10 seconds", session_id)
        )

    def _on_mpv_ready(self, proc, session_id):
        if not self._is_active_session(session_id, proc) or proc.poll() is not None:
            return
        log(FR["mpv_ok"])
        self._playing = True
        self._loading = False
        self._set_controls_enabled(True)
        self.play_btn.config(text=FR["control_pause"])
        self._paused = False
        self.vol_scale.set(self._volume)
        self._update_mpv_title()

    def _show_keywords_mode(self):
        if self._playing:
            self._stop_playback()

    def _stop_playback(self):
        self._session_id += 1
        self._playing = False
        self._loading = False
        self._terminate_mpv()

        try:
            os.unlink(MPV_SOCKET)
        except OSError:
            pass

        self._show_keyword_view()
        self._set_controls_enabled(False)
        self.play_btn.config(text=FR["control_play"])
        self._paused = False
        self.root.config(cursor="")

    # ── IPC controls ────────────────────────────────────────────

    def _toggle_pause(self):
        self.mpv.toggle_pause()
        self._paused = not self._paused
        self.play_btn.config(
            text=FR["control_play"] if self._paused else FR["control_pause"]
        )
        self._update_mpv_title()

    def _next_track(self):
        self.mpv.next_track()
        self._update_mpv_title()

    def _prev_track(self):
        self.mpv.prev_track()
        self._update_mpv_title()

    def _on_volume_change(self, val):
        self._volume = float(val)
        self.mpv.set_volume(self._volume)
        if self._volume_save_after_id is not None:
            try:
                self.root.after_cancel(self._volume_save_after_id)
            except tk.TclError:
                pass
        self._volume_save_after_id = self.root.after(1000, self._save_state)

    # ── Help and exit ───────────────────────────────────────────

    def _show_help(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(FR["help_title"])
        dlg.geometry("700x550")
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#1a1a1a")

        text_widget = tk.Text(
            dlg, wrap=tk.WORD, font=("TkDefaultFont", 13),
            bg="#1a1a1a", fg="white", padx=20, pady=20,
            relief=tk.FLAT, spacing1=4, spacing2=2,
        )
        text_widget.insert("1.0", FR["help_text"])
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill=tk.BOTH, expand=True)

        close_btn = tk.Button(
            dlg, text="Fermer", font=("TkDefaultFont", 14),
            command=dlg.destroy, bg="#444", fg="white",
            relief=tk.RAISED, padx=20, pady=5,
        )
        close_btn.pack(pady=(0, 15))

        self.root.wait_window(dlg)

    def _confirm_exit(self):
        result = messagebox.askyesno(
            FR["confirm_exit_title"], FR["confirm_exit_msg"],
            parent=self.root, icon="warning",
            default="no",
        )
        if result:
            self._cleanup()
            self.root.destroy()

    def _cleanup(self):
        self._session_id += 1
        self._terminate_mpv()
        try:
            os.unlink(MPV_SOCKET)
        except OSError:
            pass

    # ── Persistent keywords ─────────────────────────────────────

    def _load_keywords(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.exists(KEYWORDS_FILE):
                with open(KEYWORDS_FILE) as f:
                    data = json.load(f)
                if isinstance(data, list) and all(isinstance(k, str) for k in data):
                    return [k.strip() for k in data if k.strip()]
        except Exception as e:
            log(f"Failed to load keywords: {e}")
        return list(INITIAL_KEYWORDS)

    def _save_keywords(self):
        try:
            os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
            os.chmod(CONFIG_DIR, 0o700)
            with open(KEYWORDS_FILE, "w") as f:
                json.dump(self.keywords, f, indent=2)
            os.chmod(KEYWORDS_FILE, 0o600)
            self._save_state()
            log("Keywords saved")
        except Exception as e:
            log(f"Failed to save keywords: {e}")

    def _load_state(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("volume", 75), (int, float)):
                    return data
        except Exception as e:
            log(f"Failed to load state: {e}")
        return {}

    def _save_state(self):
        self._volume_save_after_id = None
        try:
            os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
            os.chmod(CONFIG_DIR, 0o700)
            with open(STATE_FILE, "w") as f:
                json.dump({"volume": self._volume}, f, indent=2)
            os.chmod(STATE_FILE, 0o600)
            log("State saved")
        except Exception as e:
            log(f"Failed to save state: {e}")

    # ── UI polling ──────────────────────────────────────────────

    def _poll_mpv(self):
        if not self._playing:
            self.root.after(2000, self._poll_mpv)
            return

        if self.mpv_proc and self.mpv_proc.poll() is not None:
            if self._playlist_ending and self.current_keyword:
                log(FR["playlist_ended"])
                self._session_id += 1
                session_id = self._session_id
                keyword = self.current_keyword
                self._playlist_ending = False
                self._playing = False
                self._loading = True
                self.mpv_proc = None
                self._show_loading(FR["fetching"].format(keyword))
                threading.Thread(
                    target=self._play_keyword,
                    args=(keyword, session_id),
                    daemon=True,
                ).start()
            else:
                log("mpv process died, returning to keyword selection")
                self._stop_playback()
        elif self.mpv_proc and self.mpv_proc.poll() is None:
            self._update_mpv_title()
            try:
                v = self.mpv.get_volume()
                if v is not None:
                    self._volume = v
                    if abs(self.vol_scale.get() - v) > 2:
                        self.vol_scale.set(v)
                p = self.mpv.get_pause_state()
                if p is not None and p != self._paused:
                    self._paused = p
                    self.play_btn.config(
                        text=FR["control_play"] if p else FR["control_pause"]
                    )
                pos = self.mpv.get_playlist_pos()
                count = self.mpv.get_playlist_count()
                if (
                    pos is not None
                    and count is not None
                    and count > 0
                    and pos == count - 1
                    and p is False
                ):
                    self._playlist_ending = True
            except Exception:
                pass
        self.root.after(2000, self._poll_mpv)

    def _update_mpv_title(self):
        try:
            title = self.mpv.get_media_title()
            if title:
                self.now_playing_label.config(
                    text=f"{FR['now_playing']} {title[:60]}"
                )
        except Exception:
            pass

    # ── Helpers ─────────────────────────────────────────────────

    def _is_active_session(self, session_id, proc=None):
        if session_id != self._session_id:
            return False
        return proc is None or self.mpv_proc is proc

    def _schedule_error(self, msg, session_id):
        self.root.after(0, lambda: self._on_error(msg, session_id))

    def _terminate_mpv(self):
        proc = self.mpv_proc
        self.mpv_proc = None
        if not proc:
            return
        if proc.poll() is None:
            self.mpv.stop()
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass

    def _on_error(self, msg, session_id=None):
        if session_id is not None and not self._is_active_session(session_id):
            return
        self._loading = False
        self._playing = False
        self._terminate_mpv()
        self._set_controls_enabled(False)
        self.play_btn.config(text=FR["control_play"])
        self._paused = False
        self._show_keyword_view()
        messagebox.showerror(FR["error"], msg, parent=self.root)


def main() -> int:
    root = tk.Tk()
    SimpleVideoPlayer(root)
    root.mainloop()
    log("=== App closed ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
