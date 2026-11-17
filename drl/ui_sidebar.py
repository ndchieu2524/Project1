"""Sidebar: thông tin phiên bản + cấu hình AI (Gemini/OpenAI) có fallback nội bộ."""
from __future__ import annotations

import streamlit as st

from . import __app_name__, __version__, config, database
from .ai_engine import test_connection

PROVIDERS = {
    "LOCAL": "🧠 NLP nội bộ (Regex/Heuristic) – không cần API Key",
    "GEMINI": "✨ Google Gemini (Structured JSON)",
    "OPENAI": "🤖 OpenAI (JSON mode)",
}

DEFAULT_MODELS = {
    "GEMINI": "gemini-2.5-flash",
    "OPENAI": "gpt-4o-mini",
}


def _render_version_block() -> None:
    """Hiển thị phiên bản + đường dẫn thư mục đang chạy để không nhầm bản cũ/bản mới."""
    from pathlib import Path as _Path

    import streamlit as _st

    app_dir = _Path(__file__).resolve().parent.parent
    has_crawler = (_Path(__file__).resolve().parent / "crawler.py").exists()

    _st.markdown(f"### 🎓 {__app_name__}")
    _st.caption(f"Phiên bản **{__version__}** · MVP phục vụ đồ án")
    if not has_crawler:
        _st.error(
            "⚠️ **ĐANG CHẠY BẢN CŨ** – thư mục này không có `drl/crawler.py` nên "
            "KHÔNG có tab Thu thập tự động. Hãy tắt cửa sổ cmd và chạy lại từ thư mục mới giải nén."
        )
    with _st.expander("🔎 Đang chạy từ thư mục nào?", expanded=False):
        _st.code(str(app_dir), language="text")
        _st.caption(
            "Nếu đường dẫn này trỏ tới thư mục giải nén CŨ (ví dụ có `(1)`, `(2)` hoặc bản trước), "
            "bạn đang chạy sai bản. Hãy đóng cửa sổ cmd rồi chạy `run.bat` trong thư mục mới."
        )
        if has_crawler:
            _st.success("✅ Có `drl/crawler.py` – bản này hỗ trợ Thu thập TỰ ĐỘNG.")
    _st.markdown("---")


def render() -> None:
    with st.sidebar:
        _render_version_block()

        st.markdown("#### 🤖 Cấu hình AI (tuỳ chọn)")
        provider_keys = list(PROVIDERS.keys())
        current_provider = st.session_state.get("ai_provider", "LOCAL")
        provider = st.selectbox(
            "Nhà cung cấp AI",
            provider_keys,
            index=provider_keys.index(current_provider) if current_provider in provider_keys else 0,
            format_func=lambda k: PROVIDERS[k],
            key="ai_provider_select",
        )
        st.session_state["ai_provider"] = provider

        if provider != "LOCAL":
            api_key = st.text_input(
                f"{provider} API Key", type="password", key="ai_key_input",
                value=st.session_state.get("ai_key", ""),
                help="Key chỉ lưu trong bộ nhớ phiên Streamlit của bạn, KHÔNG ghi vào database, "
                     "KHÔNG ghi log.",
            )
            st.session_state["ai_key"] = api_key
            default_model = DEFAULT_MODELS.get(provider, "")
            model = st.text_input("Model", value=st.session_state.get("ai_model") or default_model,
                                  key="ai_model_input")
            st.session_state["ai_model"] = model
            if st.button("🔌 Kiểm tra kết nối", key="test_ai_conn"):
                if not api_key.strip():
                    st.error("Chưa nhập API Key.")
                else:
                    with st.spinner("Đang kiểm tra…"):
                        ok, message = test_connection(provider, api_key.strip(), model)
                    (st.success if ok else st.error)(message)
            st.caption(
                "Nếu API lỗi/hết hạn mức, ứng dụng tự động **fallback** về bộ phân tích NLP nội bộ – "
                "không bao giờ dừng chạy."
            )
        else:
            st.session_state["ai_key"] = ""
            st.session_state["ai_model"] = ""
            st.caption(
                "Đang dùng bộ phân tích nội bộ (Regex/Heuristic + kiểm tra ràng buộc). "
                "Mọi chức năng vẫn chạy đầy đủ khi không có mạng."
            )

        st.markdown("---")
        st.markdown("#### 🔐 Cam kết bảo mật")
        st.caption(
            "• Không lưu mật khẩu CTĐB / hcmus.drl.vn / Facebook.\n\n"
            "• Extension chỉ đọc DOM khi bạn đã tự đăng nhập.\n\n"
            "• Không vượt CAPTCHA, không giả lập đăng nhập ở backend."
        )

        st.markdown("---")
        st.markdown("#### 🧾 Dữ liệu")
        stats = database.dashboard_stats()
        st.caption(
            f"{stats['n_posts']} bài đăng · {stats['n_activities']} hoạt động\n\n"
            f"{stats['n_criteria']} tiêu chí · {stats['n_schedule']} tiết TKB"
        )
        if stats["n_posts"] == 0:
            st.caption("Kho đang trống — mở tab **🌐 Thu thập TỰ ĐỘNG** để lấy dữ liệu thật.")

        st.markdown("---")
        st.caption(
            "Nguồn OSA mặc định: https://www.facebook.com/osa.hcmus\n\n"
            "Cổng TKB: https://portal.ctdb.hcmus.edu.vn/\n\n"
            "Cổng ĐRL: https://hcmus.drl.vn/"
        )
        st.caption(f"⚠️ {config.DISCLAIMER}")
