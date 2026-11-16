# -*- coding: utf-8 -*-
"""Tab 1 — Dashboard (tiến độ ĐRL tổng quan).
Chủ trì: Thành viên 5. STUB do Thành viên 1 tạo để tích hợp app.py.
TV5 thay toàn bộ nội dung bằng biểu đồ tiến độ từng tiêu chí."""

STUB_INFO = {"owner": "Thành viên 5", "files": "drl/ui_tab1_dashboard.py",
             "plan": "Biểu đồ tiến độ từng Điều ĐRL, thẻ điểm dự kiến, huy chương mục tiêu."}

def render():
    import streamlit as st
    st.subheader("📊 Tab 1 — Dashboard")
    st.info("Module đang được Thành viên 5 xây dựng.")
    st.markdown(f"**Phụ trách:** {STUB_INFO['owner']}  \n**Dự kiến:** {STUB_INFO['plan']}")
