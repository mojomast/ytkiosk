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
import http.cookiejar
import urllib.request
import urllib.error
import html.parser
import tempfile
import shutil
import sys
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse, urlencode, urlunparse
import random
from datetime import datetime, timezone

try:
    from ytkiosk.deno import resolve_js_runtime, yt_dlp_js_runtime_arg
except ModuleNotFoundError:
    from deno import resolve_js_runtime, yt_dlp_js_runtime_arg

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
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
FAVORITES_FILE = os.path.join(CONFIG_DIR, "favorites.json")
_ensure_runtime_dir()
LOG_FILE = os.path.join(RUNTIME_DIR, "yt-player.log")
MPV_SOCKET = os.path.join(RUNTIME_DIR, "mpv-socket")
MPV_LOG_FILE = os.path.join(RUNTIME_DIR, "mpv-embed.log")


def _venv_script(name):
    candidate = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def _cfg_path(name, fallback_name, default, prefer_venv=False):
    value = _cfg.get(name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if prefer_venv:
        venv_script = _venv_script(fallback_name)
        if venv_script:
            return venv_script
    return shutil.which(fallback_name) or default


MPV = _cfg_path("mpv_path", "mpv", "/usr/bin/mpv")
YTDLP = _cfg_path("ytdlp_path", "yt-dlp", "/usr/local/bin/yt-dlp", prefer_venv=True)


def _cfg_int(name, default, minimum):
    try:
        value = int(_cfg.get(name, default))
        return value if value >= minimum else default
    except (TypeError, ValueError):
        return default


def _cfg_language(default="fr"):
    value = os.environ.get("YTKIOSK_LANG") or _cfg.get("language", default)
    if isinstance(value, str) and value.lower().startswith("en"):
        return "en"
    return "fr"


SEARCH_COUNT = _cfg_int("search_count", 30, 1)
PLAYLIST_SIZE = _cfg_int("playlist_size", 20, 1)
MIN_DURATION = _cfg_int("min_duration", 300, 0)
POST_PORTAL_SEARCH_RETRIES = _cfg_int("post_portal_search_retries", 3, 1)
POST_PORTAL_RETRY_DELAY = _cfg_int("post_portal_retry_delay", 5, 1)
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


def _detect_mpv_display_mode(root=None, environ=None, tk_windowing_system=None):
    env = os.environ if environ is None else environ
    display = env.get("DISPLAY")
    wayland_display = env.get("WAYLAND_DISPLAY")
    session_type = (env.get("XDG_SESSION_TYPE") or "unknown").lower()

    if tk_windowing_system is None and root is not None:
        try:
            tk_windowing_system = str(root.tk.call("tk", "windowingsystem")).lower()
        except tk.TclError:
            tk_windowing_system = "unknown"
    tk_windowing_system = (tk_windowing_system or "unknown").lower()

    embedded = tk_windowing_system == "x11" and bool(display)
    return {
        "mode": "embedded-x11" if embedded else "standalone",
        "display": display,
        "wayland_display": wayland_display,
        "session_type": session_type,
        "tk_windowing_system": tk_windowing_system,
    }


def _build_mpv_command(
    urls,
    *,
    display_mode,
    socket_path=MPV_SOCKET,
    window_id=None,
    audio_backend=None,
    ytdlp_path=YTDLP,
    js_runtime=None,
    language="fr",
    subtitles_enabled=False,
):
    cmd = [MPV, "--osd-level=0"]
    if display_mode == "embedded-x11":
        if window_id is None:
            raise ValueError("embedded mpv mode requires a window id")
        cmd.append(f"--wid={window_id}")

    cmd += [
        "--no-config",
        f"--input-ipc-server={socket_path}",
        "--keep-open=no",
        "--vo=gpu",
        "--hwdec=auto",
        f"--ao={audio_backend or _detect_audio_backend()}",
        "--profile=fast",
    ]

    if display_mode == "embedded-x11":
        cmd += [
            "--gpu-context=x11egl",
            "--x11-bypass-compositor=yes",
        ]
    else:
        cmd += [
            "--fs",
            "--ontop",
            "--no-border",
        ]

    cmd.append("--ytdl-format=bv[height<=720]+ba/b[height<=720]")
    lang_order = "fr,en" if language == "fr" else "en,fr"
    cmd.append(f"--alang={lang_order}")
    if subtitles_enabled:
        cmd += ["--sub-auto=best", f"--slang={lang_order}"]
    if ytdlp_path:
        cmd.append(f"--script-opts=ytdl_hook-ytdl_path={ytdlp_path}")
    if js_runtime is not None:
        cmd.append(f"--ytdl-raw-options=js-runtimes={js_runtime.yt_dlp_value}")
    return cmd + list(urls)


def log(msg):
    with _log_lock:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


log("=== App started ===")

STRINGS_FR = {
    "title": "Lecteur Vidéo Simple",
    "add_keyword": "+ Ajouter un mot-clé",
    "exit": "QUITTER",
    "options": "⚙",
    "options_title": "Options",
    "options_password_title": "Options protégées",
    "options_password_prompt": "Mot de passe :",
    "options_password_bad": "Mot de passe incorrect.",
    "app_title_label": "Titre de l'application :",
    "allow_keyword_changes": "Permettre l'ajout et la modification des mots-clés",
    "enable_debug": "Afficher le bouton Debug",
    "delete_keyword": "Supprimer",
    "delete_keyword_title": "Supprimer le mot-clé",
    "delete_keyword_msg": "Supprimer « {} » ?",
    "save": "Enregistrer",
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
    "standalone_mpv": "Session non-X11 détectée : lecture mpv plein écran séparée.",
    "debug": "Debug",
    "debug_title": "Debug YTKiosk",
    "debug_refresh": "Rafraîchir",
    "debug_clear": "Vider l'affichage",
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
        "POUR QUITTER : ouvrez Options (⚙), entrez le mot de passe, puis confirmez."
    ),
    "confirm_exit_title": "Confirmation",
    "confirm_exit_msg": "Êtes-vous sûr de vouloir quitter ?",
    "yes": "Oui",
    "no": "Non",
    "loading_duration": "Vérification des durées...",
    "playlist_ended": "Liste de lecture terminée",
    "language_toggle": "EN",
    "favorite": "♥",
    "favorites": "Favoris",
    "no_favorites": "Aucun favori pour l'instant.",
    "close": "Fermer",
}

STRINGS_EN = {
    "title": "Simple Video Player",
    "add_keyword": "+ Add keyword",
    "exit": "QUIT",
    "options": "⚙",
    "options_title": "Options",
    "options_password_title": "Protected Options",
    "options_password_prompt": "Password:",
    "options_password_bad": "Incorrect password.",
    "app_title_label": "Application title:",
    "allow_keyword_changes": "Allow adding and editing keywords",
    "enable_debug": "Show Debug button",
    "delete_keyword": "Delete",
    "delete_keyword_title": "Delete keyword",
    "delete_keyword_msg": "Delete '{}'?",
    "save": "Save",
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
    "standalone_mpv": "Non-X11 session detected: using standalone fullscreen mpv.",
    "debug": "Debug",
    "debug_title": "YTKiosk Debug",
    "debug_refresh": "Refresh",
    "debug_clear": "Clear View",
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
        "TO EXIT: open Options (⚙), enter the password, then confirm."
    ),
    "confirm_exit_title": "Confirm",
    "confirm_exit_msg": "Are you sure you want to quit?",
    "yes": "Yes",
    "no": "No",
    "loading_duration": "Checking durations...",
    "playlist_ended": "Playlist ended",
    "language_toggle": "FR",
    "favorite": "♥",
    "favorites": "Favorites",
    "no_favorites": "No favorites yet.",
    "close": "Close",
}

_locale = locale.getlocale()
_default_lang = _locale[0] if isinstance(_locale, tuple) else _locale
_lang = _cfg_language("fr")
FR = STRINGS_FR if _lang == "fr" else STRINGS_EN

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

CAPTIVE_PORTAL_TRIGGER_URLS = [
    "http://1.1.1.1/",
    "http://neverssl.com/",
]

DEFAULT_CAPTIVE_PORTAL_URLS = [
    "https://cisss-public.reg09.rtss.qc.ca/login.html",
]


def _cfg_bool(name, default=False):
    value = _cfg.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _cfg_str_list(name, default):
    value = _cfg.get(name)
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return list(default)


CAPTIVE_PORTAL_URLS = _cfg_str_list("captive_portal_urls", DEFAULT_CAPTIVE_PORTAL_URLS)
ENABLE_CAPTIVE_PORTAL_TRIGGER_URLS = _cfg_bool("enable_captive_portal_trigger_urls", False)

ACCEPT_WORDS = (
    "accept",
    "agree",
    "continue",
    "connect",
    "start",
    "submit",
    "login",
    "log in",
    "i agree",
    "j'accepte",
    "j accepte",
    "accepte",
    "accepter",
    "continuer",
    "connexion",
    "valider",
)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "close",
}

SENSITIVE_FIELD_WORDS = (
    "password",
    "passwd",
    "email",
    "room",
    "voucher",
    "phone",
    "sms",
    "card",
    "payment",
    "code",
)

EXPECTED = {
    "http://connectivitycheck.gstatic.com/generate_204": (204, None),
    "http://captive.apple.com/hotspot-detect.html": (200, "Success"),
    "http://detectportal.firefox.com/success.txt": (200, "success"),
    "http://connectivity-check.ubuntu.com/generate_204": (204, None),
}


def _normalize_accept_text(text):
    normalized = text.lower().replace("’", "'").replace("‘", "'").replace("`", "'")
    normalized = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _has_accept_word(text):
    normalized = _normalize_accept_text(text)
    normalized_spaces = normalized.replace("'", " ")
    return any(word in normalized or word in normalized_spaces for word in ACCEPT_WORDS)


def detect_captive_portal():
    last_failed_url = None
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
                if e.code in (401, 403, 511):
                    fallback_url = CAPTIVE_PORTAL_URLS[0] if CAPTIVE_PORTAL_URLS else None
                    return True, fallback_url, url
                return False, None, url
            finally:
                e.close()
        except (urllib.error.URLError, OSError, ValueError):
            last_failed_url = url

    if ENABLE_CAPTIVE_PORTAL_TRIGGER_URLS:
        # Generic triggers are opt-in; this deployment targets a known hospital portal.
        for url in CAPTIVE_PORTAL_TRIGGER_URLS:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64)")
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.url != url:
                        return True, resp.url or url, url
            except urllib.error.HTTPError as e:
                try:
                    portal_url = e.headers.get("Location")
                    return True, urljoin(url, portal_url) if portal_url else url, url
                finally:
                    e.close()
            except (urllib.error.URLError, OSError, ValueError):
                continue
    if last_failed_url:
        fallback_url = CAPTIVE_PORTAL_URLS[0] if CAPTIVE_PORTAL_URLS else None
        return True, fallback_url, last_failed_url
    return False, None, None


class PortalFormParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.form_action = None
        self.form_method = "get"
        self.fields = []
        self.forms = []
        self._in_form = False
        self._current_form = None
        self._current_button = None
        self.has_accept_submit = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form":
            self._in_form = True
            self.form_action = d.get("action")
            self.form_method = d.get("method", "get").lower()
            self._current_form = {
                "action": self.form_action,
                "method": self.form_method,
                "fields": [],
                "accept_submit": None,
                "has_accept": False,
                "enctype": d.get("enctype", "application/x-www-form-urlencoded").lower(),
            }
            self.forms.append(self._current_form)
        if not self._in_form or self._current_form is None or "disabled" in d:
            return
        if self._in_form and tag == "input":
            ftype = d.get("type", "").lower()
            field = {
                "name": d.get("name", ""),
                "value": d.get("value", ""),
                "type": ftype,
            }
            if ftype in ("submit", "button"):
                label = f"{field['name']} {field['value']}".lower()
                if _has_accept_word(label):
                    self.has_accept_submit = True
                    self._current_form["has_accept"] = True
                    if ftype == "submit":
                        self._current_form["accept_submit"] = field
            if field.get("name"):
                self.fields.append(field)
                self._current_form["fields"].append(field)
        if self._in_form and tag == "button" and d.get("type", "submit") == "submit":
            field = {
                "name": d.get("name", ""),
                "value": d.get("value", "submit"),
                "type": "submit",
            }
            self._current_button = field
            self._current_button["form"] = self._current_form
            if field.get("name"):
                self.fields.append(field)
                self._current_form["fields"].append(field)

    def handle_data(self, data):
        if self._in_form and self._current_button is not None:
            text = data.strip()
            if text and _has_accept_word(text):
                self.has_accept_submit = True
                form = self._current_button.get("form")
                if form is not None:
                    form["has_accept"] = True
                    form["accept_submit"] = self._current_button
                if not self._current_button.get("value"):
                    self._current_button["value"] = text

    def handle_endtag(self, tag):
        if tag == "form":
            self._in_form = False
            self._current_form = None
        if tag == "button":
            self._current_button = None


def _portal_form_score(form):
    if not form.get("has_accept"):
        return -1
    if form.get("enctype") not in ("", "application/x-www-form-urlencoded"):
        return -1
    score = 10
    for field in form.get("fields", []):
        text = f"{field.get('name', '')} {field.get('type', '')}".lower()
        if any(word in text for word in SENSITIVE_FIELD_WORDS):
            return -1
        if field.get("type") == "hidden":
            score += 1
    return score


def _select_portal_form(parser):
    candidates = [form for form in parser.forms if _portal_form_score(form) >= 0]
    if candidates:
        return max(candidates, key=_portal_form_score)
    if parser.has_accept_submit:
        return {
            "action": parser.form_action,
            "method": parser.form_method,
            "fields": parser.fields,
            "accept_submit": None,
            "has_accept": True,
            "enctype": "application/x-www-form-urlencoded",
        }
    return None


def _origin_for(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _safe_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "<query>", parsed.fragment))


def _field_summary(fields):
    result = []
    for field in fields:
        name = field.get("name", "") or "<unnamed>"
        ftype = field.get("type", "") or "text"
        result.append(f"{name}:{ftype}")
    return ", ".join(result) if result else "none"


def _portal_submit_url(final_url, action=None, base_url=None):
    return urljoin(base_url or final_url, action or final_url)


def _query_value(url, name):
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get(name)
    if not values:
        return None
    return values[0]


def _portal_action_from_query(final_url, portal_url=None):
    for url in (final_url, portal_url):
        if not url:
            continue
        value = _query_value(url, "switch_url")
        if value:
            return value
    return None


def _portal_form_action(form, final_url, portal_url=None):
    query_action = _portal_action_from_query(final_url, portal_url)
    if query_action:
        return query_action
    action = form.get("action")
    if _is_cisco_portal_form(form) and action and "google." in urlparse(action).netloc:
        log(
            "Captive portal auto-accept: Cisco-style form has no switch_url; "
            "posting back to current portal URL instead of placeholder action."
        )
        return final_url
    return action or final_url


def _portal_redirect_from_query(final_url, portal_url=None):
    for url in (final_url, portal_url):
        if not url:
            continue
        value = _query_value(url, "redirect")
        if value:
            return value[:255]
    return ""


def _is_cisco_portal_form(form):
    names = {field.get("name", "") for field in form.get("fields", [])}
    return "buttonClicked" in names and "redirect_url" in names


def _portal_form_data(form, final_url, portal_url=None):
    data = {}
    selected_submit = form.get("accept_submit")
    for f in form.get("fields", []):
        name = f.get("name", "")
        val = f.get("value", "")
        ftype = f.get("type", "")
        if name:
            label = f"{name} {val}".lower()
            if f is selected_submit:
                data[name] = val
                continue
            if ftype == "checkbox":
                lv = val.lower()
                if lv in ("", "agree", "accept", "yes", "1", "true") or _has_accept_word(
                    label
                ):
                    data[name] = val if val else "agree"
            elif ftype == "submit" and _has_accept_word(label):
                data[name] = val if val else "Submit"
            elif ftype in ("submit", "button", "reset", "image", "file"):
                continue
            else:
                data[name] = val if val else ""

    # Cisco-style captive portals often rely on JavaScript to set these fields.
    if "buttonClicked" in data and form.get("has_accept"):
        data["buttonClicked"] = "4"
    if "redirect_url" in data:
        data["redirect_url"] = _portal_redirect_from_query(final_url, portal_url)
    return data


def try_auto_accept(portal_url, base_url=None):
    log(f"Captive portal auto-accept: fetching {_safe_url(portal_url)}")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        req = urllib.request.Request(portal_url, headers=BROWSER_HEADERS)
        with opener.open(req, timeout=10) as resp:
            final_url = resp.url
            log(
                "Captive portal fetch result: "
                f"status={getattr(resp, 'status', '?')} final={_safe_url(final_url)} "
                f"content_type={resp.headers.get('Content-Type', '')}"
            )
            html_content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"Captive portal fetch failed for {_safe_url(portal_url)}: {type(e).__name__}: {e}")
        return False


    parser = PortalFormParser()
    parser.feed(html_content)
    form = _select_portal_form(parser)
    if form is None:
        log(
            "Captive portal auto-accept: no safe accept form found; "
            f"forms={len(parser.forms)} has_accept={parser.has_accept_submit}"
        )
        return False

    action = _portal_form_action(form, final_url, portal_url)

    post_url = _portal_submit_url(final_url, action, base_url)
    if urlparse(post_url).scheme not in ("http", "https"):
        log(f"Captive portal auto-accept: unsupported submit URL {_safe_url(post_url)}")
        return False
    data = _portal_form_data(form, final_url, portal_url)
    log(
        "Captive portal form selected: "
        f"method={form.get('method', 'get')} action={_safe_url(action)} "
        f"post={_safe_url(post_url)} fields={_field_summary(form.get('fields', []))} "
        f"submit_fields={', '.join(data.keys()) or 'none'}"
    )

    if not data and not parser.has_accept_submit:
        log("Captive portal auto-accept: refusing to submit empty form")
        return False

    encoded = urlencode(data)
    try:
        if form.get("method", "get") == "get":
            sep = "&" if "?" in post_url else "?"
            req2 = urllib.request.Request(
                post_url + sep + encoded,
                headers={**BROWSER_HEADERS, "Referer": final_url},
            )
        else:
            headers = {
                **BROWSER_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": final_url,
            }
            origin = _origin_for(final_url)
            if origin:
                headers["Origin"] = origin
            req2 = urllib.request.Request(
                post_url,
                data=encoded.encode(),
                headers=headers,
            )
        with opener.open(req2, timeout=10) as resp2:
            log(
                "Captive portal submit result: "
                f"status={getattr(resp2, 'status', '?')} final={_safe_url(resp2.url)}"
            )
        return True
    except Exception as e:
        log(f"Captive portal submit failed for {_safe_url(post_url)}: {type(e).__name__}: {e}")
        return False


def captive_portal_attempt_urls(portal_url=None, include_triggers=False):
    urls = []
    if portal_url:
        urls.append(portal_url)
    urls.extend(CAPTIVE_PORTAL_URLS)
    if ENABLE_CAPTIVE_PORTAL_TRIGGER_URLS and include_triggers:
        urls.extend(CAPTIVE_PORTAL_TRIGGER_URLS)

    seen = set()
    result = []
    for url in urls:
        if url and url not in seen:
            result.append(url)
            seen.add(url)
    return result

def try_auto_accept_any(portal_url=None, include_triggers=False, on_attempt=None):
    for url in captive_portal_attempt_urls(portal_url, include_triggers):
        if on_attempt:
            on_attempt(url)
        if try_auto_accept(url):
            return True, url
    return False, None


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
        status_lbl = tk.Message(
            dlg, textvariable=status_var, font=("TkDefaultFont", 12), width=460
        )
        status_lbl.pack(pady=5)

        attempt_count = [0]
        attempt_running = [False]
        current_portal_url = [portal_url]

        def _set_status(text):
            try:
                if dlg.winfo_exists():
                    status_var.set(text)
            except tk.TclError:
                pass

        def _set_attempt_status(url):
            log(f"Captive portal attempt {attempt_count[0]}: {url}")
            dlg.after(0, lambda url=url: _set_status(
                f"Tentative {attempt_count[0]} :\n{url}"
            ))

        def _finish_attempt(ok, accepted_url=None):
            attempt_running[0] = False
            if ok:
                _set_status(FR["portal_auto_ok"])
                dlg.after(1000, lambda: _done(True))
                return
            if accepted_url:
                _set_status(
                    f"Formulaire envoyé, mais le portail est toujours actif :\n"
                    f"{accepted_url}\n\n"
                    "Nouvelle tentative automatique dans 3 secondes..."
                )
            else:
                _set_status(
                    "Portail toujours détecté.\n"
                    "Nouvelle tentative automatique dans 3 secondes..."
                )
            dlg.after(3000, _try_auto)

        def _try_auto():
            if attempt_running[0]:
                return
            attempt_running[0] = True
            attempt_count[0] += 1
            _set_status(
                f"Tentative automatique {attempt_count[0]}...\n"
                "Recherche de la page du portail..."
            )

            def _worker():
                candidate_url = current_portal_url[0]
                if not candidate_url:
                    is_captive, detected_url, _ = detect_captive_portal()
                    if not is_captive:
                        dlg.after(0, lambda: _finish_attempt(True))
                        return
                    if detected_url:
                        candidate_url = detected_url
                        current_portal_url[0] = detected_url
                include_triggers = attempt_count[0] > 2
                accepted, accepted_url = try_auto_accept_any(
                    candidate_url,
                    include_triggers=include_triggers,
                    on_attempt=_set_attempt_status,
                )
                if accepted:
                    dlg.after(0, lambda: _set_status(
                        f"Formulaire envoyé :\n{accepted_url}\n\n"
                        "Vérification de la connexion..."
                    ))
                    time.sleep(1)
                    still = detect_captive_portal()[0]
                    if not still:
                        dlg.after(0, lambda: _finish_attempt(True, accepted_url))
                        return
                dlg.after(0, lambda: _finish_attempt(False, accepted_url))

            threading.Thread(target=_worker, daemon=True).start()

        def _manual_open():
            open_url = current_portal_url[0] or (CAPTIVE_PORTAL_URLS[0] if CAPTIVE_PORTAL_URLS else None)
            _set_status(
                "Ouverture manuelle de la page du portail :\n"
                f"{open_url}\n\n"
                "Après acceptation, YTKiosk reprendra automatiquement."
            )
            _open_browser(open_url)

        def _open_browser(url):
            open_url = url or current_portal_url[0] or (CAPTIVE_PORTAL_URLS[0] if CAPTIVE_PORTAL_URLS else None)
            if not open_url:
                _set_status("Aucune URL de portail configurée.")
                return
            if urlparse(open_url).scheme not in ("http", "https"):
                _set_status(f"URL de portail invalide :\n{open_url}")
                return
            try:
                subprocess.Popen(
                    ["xdg-open", open_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as e:
                log(f"Failed to open portal browser: {e}")
                _set_status(f"Impossible d'ouvrir la page du portail :\n{e}")
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
            command=_try_auto
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame, text="Ouvrir le portail", font=("TkDefaultFont", 14),
            command=_manual_open,
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            btn_frame, text=FR["cancel"], font=("TkDefaultFont", 14),
            command=lambda: _done(False)
        ).pack(side=tk.LEFT, padx=10)

        dlg.after(250, _try_auto)

    threading.Thread(target=_run, daemon=True).start()


class SimpleVideoPlayer:
    def __init__(self, root):
        self.root = root

        self.keywords = self._load_keywords()
        self.language = _cfg_language("fr")
        self.app_title = self._load_config_str("app_title", FR["title"])
        self._custom_app_title = bool(self._load_config_str("app_title", ""))
        self.allow_keyword_changes = self._load_config_bool("allow_keyword_changes", True)
        self.enable_debug = self._load_config_bool("enable_debug", False)
        self.options_password = self._load_config_str("options_password", "baloney")
        self.favorites = self._load_favorites()
        self.mpv_proc = None
        self.current_keyword = None
        self.current_playlist = []
        self.current_video = None
        self._last_playlist_pos = None
        self.mpv = MpvRemote()
        self._paused = False
        self._volume = 75
        self._volume = self._load_state().get("volume", 75)
        self._playing = False
        self._loading = False
        self._playlist_ending = False
        self._volume_save_after_id = None
        self._session_id = 0

        self.root.title(self.app_title)

        self._setup_kiosk()
        self._build_ui()

        self._poll_mpv()
        log("UI ready")

    def _setup_kiosk(self):
        self.root.attributes("-fullscreen", True)
        self.root.focus_force()

        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

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

        self.debug_btn = tk.Button(
            self.top_bar, text=FR["debug"], font=("TkDefaultFont", 14),
            command=self._show_debug, bg="#444", fg="white",
            relief=tk.FLAT, padx=15, pady=5,
        )
        if self.enable_debug:
            self.debug_btn.pack(side=tk.LEFT, padx=(0, 10), pady=5)

        self.lang_btn = tk.Button(
            self.top_bar, text=FR["language_toggle"], font=("TkDefaultFont", 14),
            command=self._toggle_language, bg="#444", fg="white",
            relief=tk.FLAT, padx=15, pady=5,
        )
        self.lang_btn.pack(side=tk.LEFT, padx=(0, 10), pady=5)

        self.status_label = tk.Label(
            self.top_bar, text="", font=("TkDefaultFont", 11),
            fg="#aaaaaa", bg="#2a2a2a", anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15)

        self.options_btn = tk.Button(
            self.top_bar, text=FR["options"], font=("TkDefaultFont", 12, "bold"),
            command=self._show_options, bg="#444", fg="white",
            relief=tk.FLAT, padx=10, pady=3,
        )
        self.options_btn.pack(side=tk.RIGHT, padx=8, pady=5)

    def _build_keyword_view(self):
        container = tk.Frame(self.keyword_frame, bg="#1a1a1a")
        container.pack(fill=tk.BOTH, expand=True, padx=40, pady=30)

        self.title_lbl = tk.Label(
            container, text=self.app_title, font=("TkDefaultFont", 26, "bold"),
            fg="white", bg="#1a1a1a",
        )
        self.title_lbl.pack(pady=(0, 20))

        self.kw_scrollable = tk.Frame(container, bg="#1a1a1a")
        self.kw_scrollable.pack(fill=tk.BOTH, expand=True)

        self._rebuild_keyword_buttons()

    def _rebuild_keyword_buttons(self):
        for w in self.kw_scrollable.winfo_children():
            w.destroy()

        for col in range(8):
            self.kw_scrollable.grid_columnconfigure(col, weight=1, uniform="kw")

        max_rows = 6
        item_index = 0

        fav_row = tk.Frame(self.kw_scrollable, bg="#1a1a1a")
        fav_row.grid(row=0, column=0, sticky="ew", padx=6, pady=(0, 10))
        fav_btn = tk.Button(
            fav_row, text=FR["favorites"], font=("TkDefaultFont", 20, "bold"),
            command=self._on_favorites_click,
            bg="#5a2222", fg="white", relief=tk.RAISED, padx=10, pady=8,
        )
        fav_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        item_index += 1

        for i, kw in enumerate(self.keywords):
            row = tk.Frame(self.kw_scrollable, bg="#1a1a1a")
            row.grid(
                row=item_index % max_rows,
                column=item_index // max_rows,
                sticky="ew",
                padx=6,
                pady=4,
            )
            item_index += 1

            btn = tk.Button(
                row, text=kw, font=("TkDefaultFont", 20),
                command=lambda k=kw: self._on_keyword_click(k),
                bg="#333", fg="white", relief=tk.RAISED, padx=10, pady=8,
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

            if self.allow_keyword_changes:
                delete_btn = tk.Button(
                    row, text="×", font=("TkDefaultFont", 16, "bold"),
                    width=3, command=lambda idx=i: self._delete_keyword(idx),
                    bg="#aa3333", fg="white", relief=tk.RAISED, pady=8,
                )
                delete_btn.pack(side=tk.RIGHT, padx=(5, 0))

                edit_btn = tk.Button(
                    row, text=FR["edit"], font=("TkDefaultFont", 14),
                    width=3, command=lambda idx=i: self._edit_keyword(idx),
                    bg="#555", fg="white", relief=tk.RAISED, pady=8,
                )
                edit_btn.pack(side=tk.RIGHT, padx=(5, 0))

        if self.allow_keyword_changes:
            add_btn = tk.Button(
                self.kw_scrollable, text=FR["add_keyword"],
                font=("TkDefaultFont", 18),
                command=self._on_add_keyword,
                bg="#2a6b2a", fg="white", relief=tk.RAISED, padx=10, pady=8,
            )
            add_btn.grid(
                row=item_index % max_rows,
                column=item_index // max_rows,
                sticky="ew",
                padx=6,
                pady=(12, 0),
            )

    def _edit_keyword(self, idx):
        if not self.allow_keyword_changes:
            return
        old = self.keywords[idx]
        new = simpledialog.askstring(
            FR["edit_title"], FR["edit_prompt"],
            initialvalue=old, parent=self.root,
        )
        if new and new.strip():
            self.keywords[idx] = new.strip()
            self._rebuild_keyword_buttons()
            self._save_keywords()

    def _delete_keyword(self, idx):
        """Remove a keyword after caregiver confirmation."""
        if not self.allow_keyword_changes or idx < 0 or idx >= len(self.keywords):
            return
        keyword = self.keywords[idx]
        ok = messagebox.askyesno(
            FR["delete_keyword_title"],
            FR["delete_keyword_msg"].format(keyword),
            parent=self.root,
            icon="warning",
            default="no",
        )
        if ok:
            del self.keywords[idx]
            self._rebuild_keyword_buttons()
            self._save_keywords()

    def _on_add_keyword(self):
        if not self.allow_keyword_changes:
            return
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

        self.favorite_btn = tk.Button(
            inner, text=FR["favorite"], font=("TkDefaultFont", 20),
            width=3, command=self._toggle_favorite,
            bg="#444", fg="white", relief=tk.RAISED,
        )
        self.favorite_btn.pack(side=tk.LEFT, padx=3)

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
        for b in (
            self.prev_btn, self.play_btn, self.next_btn, self.stop_btn,
            self.favorite_btn,
        ):
            b.config(state=state)
        self.vol_scale.config(state=state)

    def _refresh_control_states(self):
        """Refresh favorite button visual state."""
        vid = self.current_video.get("id") if self.current_video else None
        is_fav = bool(vid) and any(item.get("id") == vid for item in self.favorites)
        self.favorite_btn.config(bg="#aa2222" if is_fav else "#444")

    def _refresh_language_text(self):
        """Update visible static UI labels after a runtime language switch."""
        if not self._custom_app_title:
            self.app_title = FR["title"]
        self.root.title(self.app_title)
        self.title_lbl.config(text=self.app_title)
        self.help_btn.config(text=FR["help"])
        self.debug_btn.config(text=FR["debug"])
        if self.enable_debug and not self.debug_btn.winfo_ismapped():
            self.debug_btn.pack(side=tk.LEFT, padx=(0, 10), pady=5, before=self.lang_btn)
        elif not self.enable_debug and self.debug_btn.winfo_ismapped():
            self.debug_btn.pack_forget()
        self.lang_btn.config(text=FR["language_toggle"])
        self.options_btn.config(text=FR["options"])
        self.favorite_btn.config(text=FR["favorite"])
        self.keyword_btn.config(text=FR["control_keywords"])
        self.stop_btn.config(text=FR["control_stop"])
        self.play_btn.config(
            text=FR["control_play"] if self._paused or not self._playing else FR["control_pause"]
        )
        self._rebuild_keyword_buttons()
        if not self._playing and not self._loading:
            self.status_label.config(text="")

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

    def _on_favorites_click(self):
        """Start playback from the saved favorites list instead of searching."""
        if self._loading:
            return
        self.favorites = self._load_favorites()
        if not self.favorites:
            self.status_label.config(text=FR["no_favorites"])
            return
        if self._playing:
            self._stop_playback()
        self._session_id += 1
        session_id = self._session_id
        self.current_keyword = FR["favorites"]
        self.current_playlist = list(self.favorites)
        self.current_video = self.current_playlist[0] if self.current_playlist else None
        self._last_playlist_pos = None
        self._playlist_ending = False
        self._loading = True
        self._show_loading(FR["fetching"].format(FR["favorites"]))
        self.root.after(0, lambda: self._start_mpv(self.current_playlist, session_id))

    def _play_keyword(self, keyword, session_id):
        try:
            log(FR["starting"].format(keyword))

            portal_resolved = False
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
                portal_resolved = True
                self._wait_after_captive_portal(session_id)
            if not self._is_active_session(session_id):
                return

            playlist = self._fetch_playlist_with_retries(
                keyword,
                session_id,
                attempts=POST_PORTAL_SEARCH_RETRIES if portal_resolved else 1,
                delay=POST_PORTAL_RETRY_DELAY,
            )

            if not playlist:
                self._schedule_error(FR["no_videos"].format(keyword), session_id)
                return

            log(FR["launching"].format(len(playlist)))
            self.root.after(0, lambda: self._start_mpv(playlist, session_id))

        except Exception as e:
            log(f"EXCEPTION: {e}")
            import traceback
            log(traceback.format_exc())
            self._schedule_error(str(e), session_id)

    def _wait_after_captive_portal(self, session_id):
        log("Captive portal accepted; waiting for network to settle before search")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not self._is_active_session(session_id):
                return
            try:
                if not detect_captive_portal()[0]:
                    log("Post-portal connectivity check passed")
                    time.sleep(2)
                    return
            except Exception as e:
                log(f"Post-portal connectivity check failed: {type(e).__name__}: {e}")
            time.sleep(1)
        log("Post-portal connectivity wait timed out; trying search anyway")

    def _fetch_playlist_with_retries(self, keyword, session_id, attempts=1, delay=5):
        last_error = None
        for attempt in range(1, attempts + 1):
            if not self._is_active_session(session_id):
                return []
            try:
                log(f"yt-dlp search attempt {attempt}/{attempts}")
                return self._fetch_playlist(keyword)
            except Exception as e:
                last_error = e
                log(f"yt-dlp search attempt {attempt}/{attempts} failed: {e}")
                if attempt >= attempts:
                    break
                time.sleep(delay)
        raise last_error or Exception("Search failed")

    def _fetch_playlist(self, keyword):
        log(FR["fetching"].format(keyword))
        js_runtime_args = yt_dlp_js_runtime_arg()
        search_keyword = f"{keyword} en français" if self.language == "fr" else keyword
        extractor_args = ["--extractor-args", f"youtube:lang={self.language}"]

        try:
            cmd = [
                YTDLP,
                *js_runtime_args,
                *extractor_args,
                f"ytsearch{SEARCH_COUNT}:{search_keyword}",
                "--flat-playlist",
                "--ignore-errors",
                "--match-filters", f"duration > {MIN_DURATION} & !is_live",
                "--retries", "5",
                "--fragment-retries", "5",
                "--socket-timeout", "15",
                "--print", "%(id)s\t%(duration)s\t%(title)s",
            ]
            result = subprocess.run(
                cmd,
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
                        title = parts[2].strip() if len(parts) >= 3 else vid
                        if dur > MIN_DURATION:
                            candidates.append({
                                "id": vid,
                                "title": title,
                                "duration": dur,
                            })
                    except (ValueError, IndexError):
                        pass

        log(f"Found {len(candidates)} videos > {MIN_DURATION}s")

        if not candidates:
            raise Exception(FR["no_videos"].format(keyword))

        candidates.sort(key=lambda x: x["duration"], reverse=True)

        selected = candidates[:PLAYLIST_SIZE]
        random.shuffle(selected)

        log(f"Playlist: {[v['id'] for v in selected]}")
        return selected

    def _start_mpv(self, playlist, session_id):
        if not self._is_active_session(session_id):
            return
        self.current_playlist = list(playlist)
        self.current_video = self.current_playlist[0] if self.current_playlist else None
        self._last_playlist_pos = None
        self._show_video_view()
        fw, fh = self._ensure_video_frame_sized()
        display_info = _detect_mpv_display_mode(self.root)
        display_mode = display_info["mode"]
        wid = None
        if display_mode == "embedded-x11":
            wid = self.video_frame.winfo_id()
            log(f"Video frame X11 ID: {wid} size={fw}x{fh}")
        else:
            self.status_label.config(text=FR["standalone_mpv"])
            log(f"Using standalone mpv fallback: {display_info}")

        env = os.environ.copy()
        env["PATH"] = ":".join(
            part for part in (
                os.path.dirname(YTDLP),
                "/usr/local/bin",
                env.get("PATH", "/usr/bin"),
            ) if part
        )
        if display_mode == "embedded-x11":
            env.pop("WAYLAND_DISPLAY", None)

        cmd = _build_mpv_command(
            [f"https://www.youtube.com/watch?v={entry['id']}" for entry in playlist],
            display_mode=display_mode,
            window_id=wid,
            audio_backend=_detect_audio_backend(),
            ytdlp_path=YTDLP,
            js_runtime=resolve_js_runtime(),
            language=self.language,
            subtitles_enabled=False,
        )

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
        self._refresh_control_states()

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
        self.current_playlist = []
        self.current_video = None
        self._last_playlist_pos = None
        self._refresh_control_states()
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

    def _toggle_language(self):
        """Switch the active UI/search language and persist the setting."""
        global FR
        self.language = "en" if self.language == "fr" else "fr"
        FR = STRINGS_FR if self.language == "fr" else STRINGS_EN
        self._save_config_value("language", self.language)
        self._refresh_language_text()

    def _toggle_favorite(self):
        """Add or remove the current video from the favorites file."""
        if not self.current_video:
            return
        vid = self.current_video.get("id")
        if not vid:
            return
        self.favorites = self._load_favorites()
        if any(item.get("id") == vid for item in self.favorites):
            self.favorites = [item for item in self.favorites if item.get("id") != vid]
        else:
            entry = {
                "id": vid,
                "title": self.current_video.get("title") or vid,
                "duration": int(self.current_video.get("duration") or 0),
                "added": datetime.now(timezone.utc).isoformat(),
            }
            self.favorites.append(entry)
        self._save_favorites()
        self._refresh_control_states()

    def _show_options(self):
        """Open the password-protected caregiver options dialog."""
        password = simpledialog.askstring(
            FR["options_password_title"],
            FR["options_password_prompt"],
            parent=self.root,
            show="*",
        )
        if password is None:
            return
        if password != self.options_password:
            messagebox.showerror(FR["error"], FR["options_password_bad"], parent=self.root)
            return
        self._open_options_dialog()

    def _open_options_dialog(self):
        """Render caregiver settings after successful password entry."""
        dlg = tk.Toplevel(self.root)
        dlg.title(FR["options_title"])
        dlg.geometry("620x360")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#1a1a1a")

        body = tk.Frame(dlg, bg="#1a1a1a")
        body.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        tk.Label(
            body, text=FR["app_title_label"], font=("TkDefaultFont", 14),
            fg="white", bg="#1a1a1a", anchor="w",
        ).pack(fill=tk.X, pady=(0, 5))

        title_var = tk.StringVar(value=self.app_title)
        title_entry = tk.Entry(body, textvariable=title_var, font=("TkDefaultFont", 16))
        title_entry.pack(fill=tk.X, pady=(0, 18))
        title_entry.focus_set()

        keyword_var = tk.BooleanVar(value=self.allow_keyword_changes)
        tk.Checkbutton(
            body, text=FR["allow_keyword_changes"], variable=keyword_var,
            font=("TkDefaultFont", 13), bg="#1a1a1a", fg="white",
            selectcolor="#333", activebackground="#1a1a1a",
            activeforeground="white",
        ).pack(fill=tk.X, anchor="w", pady=(0, 10))

        debug_var = tk.BooleanVar(value=self.enable_debug)
        tk.Checkbutton(
            body, text=FR["enable_debug"], variable=debug_var,
            font=("TkDefaultFont", 13), bg="#1a1a1a", fg="white",
            selectcolor="#333", activebackground="#1a1a1a",
            activeforeground="white",
        ).pack(fill=tk.X, anchor="w", pady=(0, 20))

        button_frame = tk.Frame(body, bg="#1a1a1a")
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Button(
            button_frame, text=FR["exit"], font=("TkDefaultFont", 14, "bold"),
            command=lambda: self._confirm_exit(dlg), bg="#cc0000", fg="white",
            relief=tk.RAISED, padx=20, pady=5,
        ).pack(side=tk.LEFT)

        tk.Button(
            button_frame, text=FR["cancel"], font=("TkDefaultFont", 14),
            command=dlg.destroy, bg="#444", fg="white",
            relief=tk.RAISED, padx=20, pady=5,
        ).pack(side=tk.RIGHT, padx=(10, 0))

        tk.Button(
            button_frame, text=FR["save"], font=("TkDefaultFont", 14),
            command=lambda: self._save_options(dlg, title_var, keyword_var, debug_var),
            bg="#2a6b2a", fg="white", relief=tk.RAISED, padx=20, pady=5,
        ).pack(side=tk.RIGHT)

        self.root.wait_window(dlg)

    def _save_options(self, dlg, title_var, keyword_var, debug_var):
        """Persist caregiver options and refresh visible controls."""
        title = title_var.get().strip() or FR["title"]
        self.app_title = title
        self._custom_app_title = True
        self.allow_keyword_changes = bool(keyword_var.get())
        self.enable_debug = bool(debug_var.get())
        self._save_config_values({
            "app_title": self.app_title,
            "allow_keyword_changes": self.allow_keyword_changes,
            "enable_debug": self.enable_debug,
        })
        self._refresh_language_text()
        self._rebuild_keyword_buttons()
        dlg.destroy()

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
            dlg, text=FR["close"], font=("TkDefaultFont", 14),
            command=dlg.destroy, bg="#444", fg="white",
            relief=tk.RAISED, padx=20, pady=5,
        )
        close_btn.pack(pady=(0, 15))

        self.root.wait_window(dlg)

    def _show_debug(self):
        dlg = tk.Toplevel(self.root)
        dlg.title(FR["debug_title"])
        dlg.geometry("900x650")
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.configure(bg="#111")

        header = tk.Label(
            dlg,
            text=(
                f"Log: {LOG_FILE}\n"
                f"Portal URLs: {', '.join(CAPTIVE_PORTAL_URLS) or 'none'}\n"
                f"Generic triggers enabled: {ENABLE_CAPTIVE_PORTAL_TRIGGER_URLS}"
            ),
            font=("TkDefaultFont", 11),
            fg="#cccccc",
            bg="#111",
            justify=tk.LEFT,
            anchor="w",
        )
        header.pack(fill=tk.X, padx=10, pady=(10, 5))

        text_frame = tk.Frame(dlg, bg="#111")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget = tk.Text(
            text_frame,
            wrap=tk.NONE,
            font=("TkFixedFont", 10),
            bg="#050505",
            fg="#e0e0e0",
            insertbackground="white",
            yscrollcommand=scrollbar.set,
        )
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        state = {"after_id": None}

        def _read_log_tail():
            try:
                with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-500:]
                return "".join(lines)
            except FileNotFoundError:
                return "Log file not created yet.\n"
            except Exception as e:
                return f"Could not read log: {e}\n"

        def _refresh():
            try:
                if not dlg.winfo_exists():
                    return
                at_bottom = text_widget.yview()[1] > 0.98
                text_widget.config(state=tk.NORMAL)
                text_widget.delete("1.0", tk.END)
                text_widget.insert("1.0", _read_log_tail())
                text_widget.config(state=tk.DISABLED)
                if at_bottom:
                    text_widget.see(tk.END)
                state["after_id"] = dlg.after(1000, _refresh)
            except tk.TclError:
                pass

        def _clear_view():
            text_widget.config(state=tk.NORMAL)
            text_widget.delete("1.0", tk.END)
            text_widget.config(state=tk.DISABLED)

        def _close():
            if state["after_id"] is not None:
                try:
                    dlg.after_cancel(state["after_id"])
                except tk.TclError:
                    pass
            dlg.destroy()

        button_frame = tk.Frame(dlg, bg="#111")
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(
            button_frame,
            text=FR["debug_refresh"],
            font=("TkDefaultFont", 13),
            command=_refresh,
            bg="#444",
            fg="white",
            padx=15,
            pady=5,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            button_frame,
            text=FR["debug_clear"],
            font=("TkDefaultFont", 13),
            command=_clear_view,
            bg="#444",
            fg="white",
            padx=15,
            pady=5,
        ).pack(side=tk.LEFT, padx=(0, 10))
        tk.Button(
            button_frame,
            text=FR["close"],
            font=("TkDefaultFont", 13),
            command=_close,
            bg="#666",
            fg="white",
            padx=15,
            pady=5,
        ).pack(side=tk.RIGHT)

        dlg.protocol("WM_DELETE_WINDOW", _close)
        log("Debug console opened")
        _refresh()

    def _confirm_exit(self, parent=None):
        result = messagebox.askyesno(
            FR["confirm_exit_title"], FR["confirm_exit_msg"],
            parent=parent or self.root, icon="warning",
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

    def _load_config_str(self, name, default=""):
        """Read a persisted string config value with a safe default."""
        data = _load_config()
        value = data.get(name, default)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return default

    def _load_config_bool(self, name, default=False):
        """Read a persisted boolean config value with a safe default."""
        data = _load_config()
        value = data.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _save_config_value(self, name, value):
        """Merge and persist one user config value without dropping existing keys."""
        self._save_config_values({name: value})

    def _save_config_values(self, values):
        """Merge and persist multiple user config values."""
        global _cfg
        try:
            os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
            os.chmod(CONFIG_DIR, 0o700)
            data = _load_config()
            data.update(values)
            _cfg = data
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
            os.chmod(CONFIG_FILE, 0o600)
            log(f"Config saved: {', '.join(values.keys())}")
        except Exception as e:
            log(f"Failed to save config: {e}")

    def _load_favorites(self):
        """Load the persisted favorites playlist."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if os.path.exists(FAVORITES_FILE):
                with open(FAVORITES_FILE) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    result = []
                    for item in data:
                        if not isinstance(item, dict) or not item.get("id"):
                            continue
                        result.append({
                            "id": str(item.get("id")),
                            "title": str(item.get("title") or item.get("id")),
                            "duration": int(item.get("duration") or 0),
                            "added": str(item.get("added") or ""),
                        })
                    return result
        except Exception as e:
            log(f"Failed to load favorites: {e}")
        return []

    def _save_favorites(self):
        """Persist the current favorites playlist."""
        try:
            os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
            os.chmod(CONFIG_DIR, 0o700)
            with open(FAVORITES_FILE, "w") as f:
                json.dump(self.favorites, f, indent=2)
            os.chmod(FAVORITES_FILE, 0o600)
            log("Favorites saved")
        except Exception as e:
            log(f"Failed to save favorites: {e}")

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
                if pos is not None and pos != self._last_playlist_pos:
                    try:
                        idx = int(pos)
                    except (TypeError, ValueError):
                        idx = -1
                    if 0 <= idx < len(self.current_playlist):
                        self.current_video = self.current_playlist[idx]
                    self._last_playlist_pos = pos
                    self.favorites = self._load_favorites()
                    self._refresh_control_states()
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
        self.current_playlist = []
        self.current_video = None
        self._last_playlist_pos = None
        self._refresh_control_states()
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
