# -*- coding: utf-8 -*-
"""Sidebar dùng chung — Thành viên 1 (tích hợp) + Thành viên 5 (hoàn thiện UI)."""

def render_sidebar():
    import streamlit as st
    from drl.config import APP_NAME, APP_VERSION, DRL_REGULATION_SOURCE
    from drl import database as db

    st.sidebar.title(f"🎓 {APP_NAME}")
    st.sidebar.caption(f"Phiên bản {APP_VERSION} — Nhóm 5 · HCMUS")

    profile = db.get_student_profile()
    st.sidebar.markdown("### 👤 Sinh viên")
    if profile.get("student_id"):
        st.sidebar.markdown(
            f"**{profile['full_name']}**  \n"
            f"MSSV: `{profile['student_id']}`  \n"
            f"Lớp: {profile['class_name']} · Khóa {profile['cohort']}  \n"
            f"HK hiện tại: {profile['current_semester']}  \n"
            f"Mục tiêu ĐRL: **{profile['target_drl']} điểm**"
        )
    else:
        st.sidebar.info("Chưa có hồ sơ — chạy `python -m drl.seed_data`.")

    with st.sidebar.expander("🗄️ Trạng thái Database"):
        try:
            stats = db.get_db_stats()
            st.write({k: v for k, v in stats.items() if k != "activities_by_component"})
        except Exception as exc:  # bảng chưa tạo
            st.warning(f"Chưa khởi tạo DB: {exc}")

    st.sidebar.caption(f"📜 Nguồn quy chế: {DRL_REGULATION_SOURCE}")
