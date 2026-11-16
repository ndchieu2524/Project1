# -*- coding: utf-8 -*-
"""Tab 4 — Thu thập dữ liệu (Crawler).
Chủ trì: Thành viên 2 (drl/crawler.py, drl/ui_tab_crawler.py). STUB do TV1 tạo."""

STUB_INFO = {"owner": "Thành viên 2", "files": "drl/crawler.py, drl/ui_tab_crawler.py",
             "plan": "Nút chạy crawl theo nguồn (ctsv_api, hcmus_events, hcmus_posts, fit_news, fb_rss) + xem log."}

def render():
    import streamlit as st
    from drl import database as db
    st.subheader("🕸️ Tab 4 — Thu thập dữ liệu")
    sources = db.list_sources()
    st.markdown("**Nguồn đang cấu hình trong DB:**")
    for s in sources:
        badge = "🟢" if s["is_active"] else "⚪"
        st.markdown(f"{badge} `{s['code']}` — {s['name']} ({s['type']})")
    st.info("Chức năng crawl & log đang được Thành viên 2 hoàn thiện.")
    st.markdown(f"**Phụ trách:** {STUB_INFO['owner']}  \n**Dự kiến:** {STUB_INFO['plan']}")
