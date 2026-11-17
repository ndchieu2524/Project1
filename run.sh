#!/usr/bin/env bash
# ============================================================
#  Smart DRL Assistant - HCMUS (MVP)  ·  macOS / Linux
#  Chay:  bash run.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo "=========================================================="
echo "   Smart DRL Assistant - HCMUS (MVP)"
echo "=========================================================="

echo "[1/3] Kiểm tra Python..."
command -v python3 >/dev/null 2>&1 || {
  echo "  [LỖI] Chưa cài Python 3. Tải tại https://www.python.org/downloads/"; exit 1;
}
python3 --version

echo "[2/3] Cài thư viện (lần đầu 1-3 phút)..."
python3 -m pip install --quiet --no-warn-script-location --disable-pip-version-check \
  streamlit pandas networkx scikit-learn matplotlib google-generativeai openpyxl requests

# Tắt màn hình chào email của Streamlit (chỉ ảnh hưởng máy của bạn)
mkdir -p "$HOME/.streamlit"
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

echo "[3/3] Khởi động tại http://localhost:8501 (Ctrl+C để dừng)..."
(
  for _ in $(seq 1 180); do
    if curl -sf -o /dev/null http://localhost:8501/ 2>/dev/null; then
      (open http://localhost:8501 2>/dev/null || xdg-open http://localhost:8501 2>/dev/null || true)
      break
    fi
    sleep 1
  done
) &

exec python3 -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
