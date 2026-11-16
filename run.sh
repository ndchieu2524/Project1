#!/usr/bin/env bash
# ============================================================
# run.sh — Khởi động Smart DRL Assistant (Linux/macOS)
# Tạo venv (nếu chưa có) -> cài dependencies -> chạy Streamlit
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "[run] Tạo môi trường ảo venv..."
    python3 -m venv venv
fi

echo "[run] Cài đặt dependencies..."
"venv/bin/python" -m pip install --upgrade pip >/dev/null
"venv/bin/python" -m pip install -r requirements.txt

echo "[run] Seed dữ liệu mẫu (nếu DB trống)..."
"venv/bin/python" -m drl.seed_data

echo "[run] Khởi động ứng dụng tại http://localhost:8501"
exec "venv/bin/python" -m streamlit run app.py --server.port=8501
