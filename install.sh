#!/usr/bin/env bash
set -euo pipefail

SOURCE_URL="${YTKIOSK_SOURCE_URL:-https://github.com/mojomast/ytkiosk/archive/refs/heads/main.tar.gz}"
INSTALL_VERSION="2026-06-21.2"
APP_DIR="${YTKIOSK_APP_DIR:-$HOME/.local/share/ytkiosk}"
BIN_DIR="$HOME/.local/bin"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "YTKiosk is Linux-only." >&2
  exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.deno/bin:$PATH"
echo "YTKiosk installer $INSTALL_VERSION"

missing_system=()
command -v python3 >/dev/null 2>&1 || missing_system+=(python3)
python3 - <<'PY' >/dev/null 2>&1 || missing_system+=(python3-tk)
import tkinter
PY
command -v mpv >/dev/null 2>&1 || missing_system+=(mpv)
command -v curl >/dev/null 2>&1 || missing_system+=(curl)
command -v tar >/dev/null 2>&1 || missing_system+=(tar)
command -v xset >/dev/null 2>&1 || missing_system+=(x11-xserver-utils)
command -v xdg-open >/dev/null 2>&1 || missing_system+=(xdg-utils)

if ((${#missing_system[@]})); then
  if command -v apt-get >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
    echo "Installing missing system packages with sudo: ${missing_system[*]}"
    sudo apt-get update
    sudo apt-get install -y ca-certificates "${missing_system[@]}"
  else
    echo "Missing system packages: ${missing_system[*]}" >&2
    echo "Install them with your OS package manager, then rerun this installer." >&2
    echo "Continuing with user-space Python/Deno installation where possible." >&2
  fi
fi

if ! command -v deno >/dev/null 2>&1; then
  curl -fsSL https://deno.land/install.sh | sh
  export PATH="$HOME/.deno/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL "$SOURCE_URL" | tar -xz -C "$tmpdir" --strip-components=1
mkdir -p "$APP_DIR" "$BIN_DIR"
uv venv --clear "$APP_DIR/venv"
uv pip install --python "$APP_DIR/venv/bin/python" "$tmpdir" yt-dlp

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
cat > "$BIN_DIR/yt-dlp" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/venv/bin/yt-dlp" "\$@"
EOF
chmod +x "$BIN_DIR/ytkiosk" "$BIN_DIR/ytkiosk-doctor" "$BIN_DIR/yt-dlp"

echo
echo "YTKiosk installed. Run: ytkiosk"
echo "If your shell cannot find it, add ~/.local/bin to PATH or run: $BIN_DIR/ytkiosk"
echo "Checking runtime dependencies:"
"$BIN_DIR/ytkiosk-doctor" || true
