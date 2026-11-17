"""Kiểm tra nhanh: thư mục này là bản MỚI (có thu thập tự động) hay bản CŨ?

Chạy:  python check_version.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRL = ROOT / "drl"

print("=" * 68)
print(" KIỂM TRA PHIÊN BẢN – SMART DRL ASSISTANT HCMUS")
print("=" * 68)
print(f"Thư mục đang kiểm tra:\n  {ROOT}\n")

checks = [
    ("drl/crawler.py", "Bộ thu thập tự động 4 nguồn công khai"),
    ("drl/ui_tab_crawler.py", "Tab giao diện Thu thập TỰ ĐỘNG"),
    ("drl/ui_tab3_explorer.py", "Tab Kho hoạt động"),
    ("drl/pathway.py", "Lộ trình NetworkX"),
    ("app.py", "Cửa vào ứng dụng"),
    ("run.bat", "Trình khởi chạy Windows"),
]
all_ok = True
for rel, desc in checks:
    exists = (ROOT / rel).exists()
    all_ok &= exists
    print(f"  {'✅' if exists else '❌'}  {rel:<28} {desc}")

# Kiểm tra số tab thật trong app.py
app_py = (ROOT / "app.py").read_text(encoding="utf-8") if (ROOT / "app.py").exists() else ""
# Đếm số tab khai báo trong app.py (mỗi mục có hậu tố render)
n_tabs = app_py.count("render),")
has_crawler_tab = "ui_tab_crawler" in app_py

print()
if has_crawler_tab and n_tabs >= 7:
    print(f"✅ ĐÂY LÀ BẢN MỚI – có {n_tabs} tab, bao gồm '🌐 Thu thập TỰ ĐỘNG'.")
    print("   Chạy:  run.bat   (hoặc  python -m streamlit run app.py )")
    print("   Lần đầu mở app, hệ thống sẽ TỰ thu thập hoạt động thật từ web trường.")
    sys.exit(0)

print(f"❌ ĐÂY LÀ BẢN CŨ – chỉ có {n_tabs} tab, KHÔNG có tab Thu thập TỰ ĐỘNG.")
print("   Nguyên nhân thường gặp: bạn đang chạy thư mục giải nén từ lần trước.")
print("   Cách sửa:")
print("     1. Đóng cửa sổ cmd đang chạy app.")
print("     2. Giải nén lại file smart_drl_assistant.zip vào thư mục MỚI.")
print("     3. Vào thư mục mới, chạy run.bat")
if not all_ok:
    print("\n   (Một số tệp bắt buộc đang thiếu – xem dấu ❌ ở trên.)")
sys.exit(1)
