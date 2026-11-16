# -*- coding: utf-8 -*-
"""Tab 5 — Đồng bộ Extension (hcmus.drl.vn & CTĐB).
Chủ trì: Thành viên 3 (chrome_plugin/*). STUB do TV1 tạo."""

STUB_INFO = {"owner": "Thành viên 3", "files": "chrome_plugin/manifest.json, content.js, popup.js, popup.html",
             "plan": "Hướng dẫn cài Chrome Extension + kiểm tra dữ liệu đồng bộ; link tới devtests/."}

def render():
    import streamlit as st
    st.subheader("🔌 Tab 5 — Đồng bộ Extension")
    st.markdown(
        "1. Mở `chrome://extensions` → bật **Developer mode**  \n"
        "2. **Load unpacked** → chọn thư mục `chrome_plugin/`  \n"
        "3. Đăng nhập cổng điểm rèn luyện (`hcmus.drl.vn`) → bấm **Đồng bộ** trên popup"
    )
    st.info("Extension và kịch bản kiểm thử (devtests/) đang được Thành viên 3 hoàn thiện.")
    st.markdown(f"**Phụ trách:** {STUB_INFO['owner']}  \n**Dự kiến:** {STUB_INFO['plan']}")
