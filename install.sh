#!/usr/bin/env bash
set -euo pipefail

SOURCE_URL="${YTKIOSK_SOURCE_URL:-https://github.com/mojomast/ytkiosk/archive/refs/heads/main.tar.gz}"
INSTALL_VERSION="2026-06-21.3"
APP_DIR="${YTKIOSK_APP_DIR:-$HOME/.local/share/ytkiosk}"
BIN_DIR="$HOME/.local/bin"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "YTKiosk is Linux-only." >&2
  exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.deno/bin:$PATH"
echo "YTKiosk installer $INSTALL_VERSION"

check_python_version() {
  python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

has_js_runtime() {
  local cmd
  for cmd in deno node nodejs qjs quickjs qjs-ng bun; do
    command -v "$cmd" >/dev/null 2>&1 && return 0
  done
  return 1
}

missing_required=()
missing_optional=()
command -v python3 >/dev/null 2>&1 || missing_required+=(python3)
python3 - <<'PY' >/dev/null 2>&1 || missing_required+=(python3-tk)
import tkinter
PY
command -v mpv >/dev/null 2>&1 || missing_required+=(mpv)
command -v curl >/dev/null 2>&1 || missing_required+=(curl)
command -v tar >/dev/null 2>&1 || missing_required+=(tar)
command -v xset >/dev/null 2>&1 || missing_optional+=(x11-xserver-utils)
command -v xdg-open >/dev/null 2>&1 || missing_optional+=(xdg-utils)
command -v pactl >/dev/null 2>&1 || missing_optional+=(pulseaudio-utils)

if ((${#missing_required[@]})); then
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    echo "Installing missing required system packages with sudo: ${missing_required[*]}"
    sudo apt-get update
    sudo apt-get install -y ca-certificates "${missing_required[@]}"
  else
    echo "Missing required system packages: ${missing_required[*]}" >&2
    echo "Install them with your OS package manager, then rerun this installer." >&2
    exit 1
  fi
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is still missing after dependency installation." >&2
  exit 1
fi

if ! check_python_version; then
  echo "Python >= 3.11 is required. Install a newer python3, then rerun this installer." >&2
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1; then
import tkinter
PY
  echo "python3-tk is still missing after dependency installation." >&2
  exit 1
fi

for required_cmd in mpv curl tar; do
  if ! command -v "$required_cmd" >/dev/null 2>&1; then
    echo "$required_cmd is still missing after dependency installation." >&2
    exit 1
  fi
done

if ((${#missing_optional[@]})); then
  echo "Optional desktop/audio helpers not found: ${missing_optional[*]}"
  echo "Core playback can still install; install them later if doctor warns."
fi

if has_js_runtime; then
  echo "JavaScript runtime detected for yt-dlp extraction support."
elif [[ "${YTKIOSK_INSTALL_DENO:-0}" == "1" ]]; then
  echo "Installing optional Deno runtime because YTKIOSK_INSTALL_DENO=1."
  curl -fsSL https://deno.land/install.sh | sh
  export PATH="$HOME/.deno/bin:$PATH"
else
  echo "No JavaScript runtime found. yt-dlp can still install, but YouTube extraction"
  echo "may require Deno, Node 22+, or QuickJS if ytkiosk-doctor later warns."
  echo "To install Deno automatically, rerun with: YTKIOSK_INSTALL_DENO=1 bash install.sh"
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL "$SOURCE_URL" | tar -xz -C "$tmpdir" --strip-components=1
mkdir -p "$APP_DIR" "$BIN_DIR"
uv venv --clear --python python3 "$APP_DIR/venv"
uv pip install --python "$APP_DIR/venv/bin/python" "$tmpdir"

cat > "$BIN_DIR/ytkiosk" <<EOF
#!/usr/bin/env bash
export PATH="\$HOME/.local/bin:\$HOME/.deno/bin:\$PATH"
exec "$APP_DIR/venv/bin/ytkiosk" "\$@"
EOF
cat > "$BIN_DIR/ytkiosk-doctor" <<EOF
#!/usr/bin/env bash
export PATH="\$HOME/.local/bin:\$HOME/.deno/bin:\$PATH"
exec "$APP_DIR/venv/bin/ytkiosk-doctor" "\$@"
EOF
cat > "$BIN_DIR/ytkiosk-cli" <<EOF
#!/usr/bin/env bash
export PATH="\$HOME/.local/bin:\$HOME/.deno/bin:\$PATH"
exec "$APP_DIR/venv/bin/ytkiosk-cli" "\$@"
EOF
cat > "$BIN_DIR/ytkiosk-yt-dlp" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/venv/bin/yt-dlp" "\$@"
EOF
chmod +x "$BIN_DIR/ytkiosk" "$BIN_DIR/ytkiosk-doctor" "$BIN_DIR/ytkiosk-cli" "$BIN_DIR/ytkiosk-yt-dlp"

write_generic_ytdlp=0
if [[ ! -e "$BIN_DIR/yt-dlp" ]]; then
  write_generic_ytdlp=1
elif [[ -f "$BIN_DIR/yt-dlp" ]]; then
  existing_ytdlp_wrapper="$(<"$BIN_DIR/yt-dlp")"
  case "$existing_ytdlp_wrapper" in
    *"YTKiosk managed yt-dlp wrapper"*|*"$APP_DIR/venv/bin/yt-dlp"*)
      write_generic_ytdlp=1
      ;;
  esac
fi

if ((write_generic_ytdlp)); then
  cat > "$BIN_DIR/yt-dlp" <<EOF
#!/usr/bin/env bash
# YTKiosk managed yt-dlp wrapper
exec "$APP_DIR/venv/bin/yt-dlp" "\$@"
EOF
  chmod +x "$BIN_DIR/yt-dlp"
else
  echo "Leaving existing $BIN_DIR/yt-dlp in place; use ytkiosk-yt-dlp for the venv copy."
fi

echo
echo "YTKiosk installed. Run: ytkiosk"
echo "If your shell cannot find it, add ~/.local/bin to PATH or run: $BIN_DIR/ytkiosk"
echo "Checking runtime dependencies:"
"$BIN_DIR/ytkiosk-doctor"
