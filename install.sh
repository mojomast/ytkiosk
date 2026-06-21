#!/usr/bin/env bash
set -euo pipefail

SOURCE_URL="${YTKIOSK_SOURCE_URL:-https://github.com/mojomast/ytkiosk/archive/refs/heads/main.tar.gz}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "YTKiosk is Linux-only." >&2
  exit 1
fi

export PATH="$HOME/.local/bin:$HOME/.deno/bin:$PATH"

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
uv tool install --force "$tmpdir"
uv tool install --force yt-dlp

echo
echo "YTKiosk installed. Run: ytkiosk"
echo "Checking runtime dependencies:"
ytkiosk-doctor || true
