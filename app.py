# -*- coding: utf-8 -*-
"""
app.py — ĐIỂM KHỞI ĐỘNG & TÍCH HỢP của Smart DRL Assistant
==========================================================
Chủ trì: Thành viên 1 (Kiến trúc hệ thống, Database & Tích hợp)

Chạy:  streamlit run app.py

Nguyên tắc tích hợp:
  - Mỗi tab UI là một module drl/ui_tab*.py độc lập do từng thành viên phụ trách.
    Nếu module của thành viên đó CHƯA có / LỖI, tab hiển thị placeholder thay vì
    làm sập toàn bộ ứng dụng (defensive import).
  - App tự khởi tạo schema SQLite và tự seed dữ liệu mẫu ở lần chạy đầu tiên
    (khi bảng sources rỗng) để demo luôn có dữ liệu.
"""

from __future__ import annotations

import importlib
import sys
import traceback

import streamlit as st

from drl.config import APP_DESCRIPTION, APP_NAME, APP_VERSION
from drl import database as db

# ---------------------------------------------------------------------------
# KHỞI TẠO DATABASE (tự động, idempotent)
# ---------------------------------------------------------------------------

def bootstrap_database() -> None:
    db.init_db()
    try:
        if not db.list_sources():
            from drl.seed_data import seed_all
            seed_all()
    except Exception:
        # Không để lỗi seed chặn việc khởi động UI — hiển thị lỗi trong sidebar
        st.session_state["bootstrap_error"] = traceback.format_exc()


bootstrap_database()

# ---------------------------------------------------------------------------
# CẤU HÌNH TRANG + SIDEBAR
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=f"{APP_NAME} — HCMUS",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from drl.ui_sidebar import render_sidebar
    render_sidebar()
except Exception:
    st.sidebar.warning("Sidebar chưa sẵn sàng.")

if "bootstrap_error" in st.session_state:
    with st.sidebar.expander("⚠️ Lỗi bootstrap DB", expanded=False):
        st.code(st.session_state["bootstrap_error"])

st.title(f"🎓 {APP_NAME}")
st.caption(APP_DESCRIPTION + f"  ·  v{APP_VERSION}")

# ---------------------------------------------------------------------------
# 6 TAB — mỗi tab do một (nhóm) thành viên phụ trách
# ---------------------------------------------------------------------------

TAB_SPECS = [
    ("📊 Dashboard",            "drl.ui_tab1_dashboard", "Thành viên 5"),
    ("🗂️ Kho hoạt động",        "drl.ui_tab2_activities", "Thành viên 5"),
    ("🧭 Lộ trình tối ưu",      "drl.ui_tab3_pathway",    "Thành viên 5"),
    ("🕸️ Thu thập dữ liệu",     "drl.ui_tab4_crawler",    "Thành viên 2"),
    ("🔌 Đồng bộ Extension",    "drl.ui_tab5_extension",  "Thành viên 3"),
    ("🤖 Đánh giá NLP & ML",    "drl.ui_tab6_ml",         "Thành viên 4"),
]


def render_tab(module_name: str, owner: str) -> None:
    """Import + render module tab; placeholder nếu module lỗi/chưa có."""
    try:
        module = importlib.import_module(module_name)
        module.render()
    except ModuleNotFoundError:
        st.info(f"Module `{module_name}` chưa được tạo — đang chờ {owner}.")
    except Exception:
        st.error(f"Module `{module_name}` ({owner}) lỗi khi render:")
        st.code(traceback.format_exc())


tabs = st.tabs([spec[0] for spec in TAB_SPECS])
for tab, (_, module_name, owner) in zip(tabs, TAB_SPECS):
    with tab:
        render_tab(module_name, owner)

# ---------------------------------------------------------------------------
# FOOTER — thông tin tích hợp (TV1)
# ---------------------------------------------------------------------------

st.divider()
col_a, col_b = st.columns([2, 1])
with col_a:
    st.caption("Kiến trúc: Streamlit UI → drl/database.py (SQLite) → drl/config.py (Quy chế ĐRL HCMUS). "
               "Module nghiệp vụ do TV2 (Crawler) · TV3 (Extension) · TV4 (NLP/AI) · TV5 (Pathway/UI) phát triển.")
with col_b:
    try:
        stats = db.get_db_stats()
        st.caption(f"DB: {stats['sources']} nguồn · {stats['source_posts']} bài viết · "
                   f"{stats['activities']} hoạt động")
    except Exception:
        st.caption("DB chưa sẵn sàng.")
