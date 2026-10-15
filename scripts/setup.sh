#!/usr/bin/env bash
# Cài đặt AI Video Creator trên macOS (Apple Silicon). Chạy lại nhiều lần vẫn an toàn.
#   ./scripts/setup.sh            cài tất cả
#   ./scripts/setup.sh models     chỉ tải mô hình tách nền
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3.13}"

REALESRGAN_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip"
RIFE_URL="https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-macos.zip"
MODEL_BASE="https://github.com/danielgatis/rembg/releases/download/v0.0.0"

# Download with resume + retries, then check md5 (large files over flaky networks).
fetch() {
  local url="$1" dest="$2" md5="${3:-}"
  mkdir -p "$(dirname "$dest")"
  if [ -n "$md5" ] && [ -f "$dest" ] && [ "$(md5 -q "$dest")" = "$md5" ]; then return 0; fi
  for attempt in 1 2 3 4 5 6 7 8; do
    if curl -fL --retry 5 --retry-delay 3 -C - -o "$dest.part" "$url"; then break; fi
    echo "  tải lại lần $attempt..."; sleep 3
  done
  if [ -n "$md5" ] && [ "$(md5 -q "$dest.part")" != "$md5" ]; then
    echo "✖ Sai checksum: $url"; rm -f "$dest.part"; return 1
  fi
  mv "$dest.part" "$dest"
}

install_models() {
  echo "▶ Mô hình tách nền (rembg)"
  fetch "$MODEL_BASE/BiRefNet-general-epoch_244.onnx" \
    "$HOME/.rembg/models/birefnet-general/birefnet-general.onnx" 7a35a0141cbbc80de11d9c9a28f52697
  fetch "$MODEL_BASE/isnet-general-use.onnx" \
    "$HOME/.rembg/models/isnet-general-use/isnet-general-use.onnx" fc16ebd8b0c10d971d3513d564d01e29
}

install_binaries() {
  echo "▶ Real-ESRGAN và RIFE (bản ncnn cho macOS)"
  local tmp; tmp="$(mktemp -d)"
  if [ ! -x bin/realesrgan/realesrgan-ncnn-vulkan ]; then
    fetch "$REALESRGAN_URL" "$tmp/re.zip"
    unzip -q "$tmp/re.zip" -d "$tmp/re"
    mkdir -p bin/realesrgan && cp "$tmp/re/realesrgan-ncnn-vulkan" bin/realesrgan/ && cp -R "$tmp/re/models" bin/realesrgan/
  fi
  if [ ! -x bin/rife/rife-ncnn-vulkan ]; then
    fetch "$RIFE_URL" "$tmp/rife.zip"
    unzip -q "$tmp/rife.zip" -d "$tmp/rife"
    local dir; dir="$(find "$tmp/rife" -maxdepth 1 -mindepth 1 -type d | head -1)"
    mkdir -p bin/rife && cp "$dir/rife-ncnn-vulkan" bin/rife/ && cp -R "$dir/rife-v4.6" bin/rife/
  fi
  rm -rf "$tmp"
  chmod +x bin/realesrgan/realesrgan-ncnn-vulkan bin/rife/rife-ncnn-vulkan
  xattr -dr com.apple.quarantine bin 2>/dev/null || true
}

install_python() {
  echo "▶ Python ($PY) + thư viện"
  command -v "$PY" >/dev/null || { echo "✖ Cần $PY (brew install python@3.13)"; exit 1; }
  [ -d .venv ] || "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
}

install_frontend() {
  echo "▶ Giao diện React"
  (cd frontend && npm install --no-audit --no-fund && npm run build)
}

check_tools() {
  echo "▶ Kiểm tra"
  command -v ffmpeg >/dev/null || { echo "✖ Thiếu ffmpeg (brew install ffmpeg)"; exit 1; }
  command -v claude >/dev/null || echo "⚠ Không thấy lệnh claude — bước viết prompt sẽ lỗi"
  [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ] || echo "⚠ Không thấy Google Chrome"
  (cd backend && ../.venv/bin/python -m pytest -q tests/test_media_integration.py) && echo "✔ Real-ESRGAN, RIFE, ffmpeg chạy được"
}

case "${1:-all}" in
  models) install_models ;;
  all) install_python; install_binaries; install_models; install_frontend; check_tools
       echo "✔ Xong. Chạy: ./scripts/start.sh" ;;
  *) echo "Dùng: $0 [all|models]"; exit 1 ;;
esac
