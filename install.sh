#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${YTKIOSK_REPO_URL:-https://github.com/mojomast/ytkiosk.git}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "YTKiosk is Linux-only." >&2
  exit 1
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y \
    ca-certificates \
    curl \
    git \
    mpv \
    python3 \
    python3-tk \
    x11-xserver-utils \
    xdg-utils
else
  echo "apt-get not found; install python3, python3-tk, mpv, git, curl, xset, and xdg-open manually." >&2
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
  sudo curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp
  sudo chmod 755 /usr/local/bin/yt-dlp
fi

if ! command -v deno >/dev/null 2>&1; then
  curl -fsSL https://deno.land/install.sh | sh
  if [[ -x "$HOME/.deno/bin/deno" ]]; then
    sudo install -m 755 "$HOME/.deno/bin/deno" /usr/local/bin/deno
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv tool install --force "git+$REPO_URL"

echo
echo "YTKiosk installed. Run: ytkiosk"
echo "Checking runtime dependencies:"
ytkiosk-doctor || true
