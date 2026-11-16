# -*- coding: utf-8 -*-
"""Tab 2 — Kho hoạt động (bảng lọc hoạt động ĐRL).
Chủ trì: Thành viên 5. STUB do Thành viên 1 tạo để tích hợp app.py."""

STUB_INFO = {"owner": "Thành viên 5", "files": "drl/ui_tab2_activities.py",
             "plan": "Bảng lọc theo Điều/tiêu chí, thời gian, nguồn; nút 'Đánh dấu tham gia'."}

def render():
    import streamlit as st
    from drl import database as db
    st.subheader("🗂️ Tab 2 — Kho hoạt động ĐRL")
    acts = db.list_activities(only_upcoming=True, limit=20)
    if acts:
        st.caption(f"Xem trước {len(acts)} hoạt động sắp tới trong DB (bản đầy đủ do TV5 hoàn thiện):")
        st.dataframe(
            [{"Hoạt động": a["title"], "TC": a["criterion_code"], "Điểm": a["drl_points"],
               "Thời gian": a["start_time"], "Đơn vị": a["organizer"]} for a in acts],
            use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có hoạt động — chạy `python -m drl.seed_data` để nạp dữ liệu mẫu.")
    st.markdown(f"**Phụ trách:** {STUB_INFO['owner']}  \n**Dự kiến:** {STUB_INFO['plan']}")
