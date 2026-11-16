# -*- coding: utf-8 -*-
"""Tab 3 — Lộ trình tối ưu (gợi ý chuỗi hoạt động đạt mục tiêu ĐRL).
Chủ trì: Thành viên 5 (thuật toán networkx trong drl/pathway.py). STUB do TV1 tạo."""

STUB_INFO = {"owner": "Thành viên 5", "files": "drl/ui_tab3_pathway.py, drl/pathway.py",
             "plan": "Chọn điểm mục tiêu (mặc định 90) → gợi ý chuỗi hoạt động graph/shortest-path, không trùng lịch CTĐB."}

def render():
    import streamlit as st
    from drl.config import PATHWAY_DEFAULT_TARGET, PATHWAY_TARGET_OPTIONS
    st.subheader("🧭 Tab 3 — Lộ trình tối ưu")
    target = st.selectbox("Điểm ĐRL mục tiêu (học kỳ)", PATHWAY_TARGET_OPTIONS,
                          index=PATHWAY_TARGET_OPTIONS.index(PATHWAY_DEFAULT_TARGET))
    st.info(f"Module gợi ý lộ trình đến {target} điểm đang được Thành viên 5 xây dựng (thuật toán networkx).")
    st.markdown(f"**Phụ trách:** {STUB_INFO['owner']}  \n**Dự kiến:** {STUB_INFO['plan']}")
