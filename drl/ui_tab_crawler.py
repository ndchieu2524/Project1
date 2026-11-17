"""Tab 2: Thu thập TỰ ĐỘNG hoạt động từ các cổng công khai của HCMUS.

Khác với Tab 3 (dán link thủ công), tab này tự đi lấy dữ liệu từ:
    * Phòng Công tác Sinh viên  – API JSON công khai (457 bài)
    * Trường HCMUS – Lịch sự kiện – The Events Calendar REST API (55 sự kiện)
    * Trường HCMUS – Tin tức/Thông báo – WordPress REST API
    * Khoa CNTT – trang thông báo HTML

Toàn bộ chạy trong tiến trình Streamlit (không cần Chrome extension, không cần
đăng nhập). Facebook bị chặn với mọi request không có cookie nên tab này nói
rõ điều đó thay vì giả vờ thu thập được.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config, crawler, database
from . import ui_common as ui

STATE_KEY = "crawl_last_result"


def _status_badge(ok: bool) -> str:
    return "✅" if ok else "❌"


def _gate_row(res: dict) -> None:
    """Hiển thị kết quả cổng chặn "đủ thông tin mới vào kho"."""
    n_past = int(res.get("skipped_past") or 0)
    incomplete = res.get("incomplete") or []
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Đủ thông tin → lưu", int(res.get("n_activities") or 0))
    c2.metric("⏳ Bỏ (đã diễn ra)", n_past)
    c3.metric("⛔ Bỏ (thiếu thông tin)", len(incomplete))
    if incomplete:
        with st.expander(f"⛔ {len(incomplete)} mục bị chặn vì THIẾU thông tin "
                         f"(bấm để xem lý do)"):
            st.caption(
                "Nguyên tắc: **thà để trống còn hơn điền sai**. Các mục này chưa vào kho "
                "vì không xác định được đủ ngày diễn ra / địa điểm / đơn vị tổ chức. "
                "Bạn có thể mở link gốc để xem chi tiết và nhập tay nếu cần."
            )
            st.dataframe(
                pd.DataFrame(incomplete)[
                    ["title", "missing_text", "source", "url"]
                ].rename(columns={
                    "title": "Tiêu đề", "missing_text": "Thiếu",
                    "source": "Nguồn", "url": "Link gốc",
                }),
                hide_index=True, width="stretch", height=300,
            )


def _render_sources_overview() -> None:
    st.subheader("🌐 Nguồn dữ liệu công khai được hỗ trợ")
    rows = [
        {
            "Nguồn": crawler.SOURCE_TYPE_LABELS["ctsv_api"],
            "URL gốc": "https://ctsv.hcmus.edu.vn",
            "Cách đọc": "API JSON `/api/news` (có phân trang)",
            "Dữ liệu có sẵn": "Tiêu đề, nội dung đầy đủ, ngày đăng, chuyên mục, tác giả",
            "Tự động": "✅",
        },
        {
            "Nguồn": crawler.SOURCE_TYPE_LABELS["hcmus_events"],
            "URL gốc": "https://hcmus.edu.vn/events/",
            "Cách đọc": "The Events Calendar REST API",
            "Dữ liệu có sẵn": "**Có sẵn start/end + địa điểm + đơn vị tổ chức**",
            "Tự động": "✅",
        },
        {
            "Nguồn": crawler.SOURCE_TYPE_LABELS["hcmus_posts"],
            "URL gốc": "https://hcmus.edu.vn",
            "Cách đọc": "WordPress REST API `/wp-json/wp/v2/posts`",
            "Dữ liệu có sẵn": "Tiêu đề, nội dung HTML, ngày đăng",
            "Tự động": "✅",
        },
        {
            "Nguồn": crawler.SOURCE_TYPE_LABELS["fit_news"],
            "URL gốc": "https://fit.hcmus.edu.vn/tin-tuc/c/thong-bao-chung",
            "Cách đọc": "Phân tích HTML danh sách thông báo",
            "Dữ liệu có sẵn": "Tiêu đề, mô tả ngắn, ngày đăng, link bài",
            "Tự động": "✅",
        },
        {
            "Nguồn": "Facebook fanpage (Đoàn trường, CTSV, CLB…)",
            "URL gốc": "https://www.facebook.com/…",
            "Cách đọc": "❌ Chặn mọi request không đăng nhập",
            "Dữ liệu có sẵn": "—",
            "Tự động": "❌ (dùng Extension/dán tay)",
        },
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption(
        "Tất cả URL trên là trang **công khai** của Trường. Hệ thống chỉ đọc, "
        "không đăng nhập, không vượt CAPTCHA, không gửi dữ liệu ra ngoài."
    )


def _render_controls() -> dict:
    st.subheader("⚙️ Cấu hình lượt thu thập")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        chosen = st.multiselect(
            "Chọn nguồn cần thu thập",
            options=[k for k, _ in crawler.SOURCE_CHOICES],
            default=[k for k, _ in crawler.SOURCE_CHOICES],
            format_func=lambda k: crawler.SOURCE_TYPE_LABELS.get(k, k),
            key="crawl_sources",
        )
    with c2:
        max_pages = st.number_input(
            "Số trang mỗi nguồn", min_value=1, max_value=crawler.MAX_PAGES_HARD_LIMIT,
            value=2, step=1, key="crawl_pages",
            help="1 trang ≈ 50 bài. Càng nhiều trang càng lâu.",
        )
    with c3:
        per_page = st.number_input(
            "Số mục mỗi trang", min_value=10, max_value=50, value=30, step=10,
            key="crawl_per_page",
        )
    activity_only = st.checkbox(
        "Chỉ giữ nội dung giống HOẠT ĐỘNG (hội thảo, cuộc thi, tình nguyện…)",
        value=True, key="crawl_activity_only",
        help="Bỏ tin học phí, bảo hiểm y tế, học bổng, lịch thi… để kho không bị nhiễu.",
    )
    upcoming_only = st.checkbox(
        "⏳ Chỉ lấy hoạt động CHƯA DIỄN RA",
        value=True, key="crawl_upcoming_only",
        help="Bỏ mọi hoạt động đã kết thúc (theo ngày kết thúc trong bài). "
             "Mục không ghi ngày được giữ lại để bạn tự kiểm tra.",
    )
    return {
        "sources": chosen,
        "max_pages": int(max_pages),
        "per_page": int(per_page),
        "activity_only": activity_only,
        "upcoming_only": upcoming_only,
    }


def _run_crawl(cfg: dict) -> None:
    if not cfg["sources"]:
        st.warning("Hãy chọn ít nhất một nguồn.")
        return
    prog = st.progress(0.0, text="Đang chuẩn bị…")
    log: list[str] = []

    def on_progress(msg: str) -> None:
        log.append(str(msg))
        prog.progress(min(0.95, 0.1 + 0.08 * len(log)), text=str(msg)[:110])

    try:
        records, status = crawler.crawl_to_records(
            source_keys=cfg["sources"],
            max_pages=cfg["max_pages"],
            per_page=cfg["per_page"],
            activity_only=cfg["activity_only"],
            upcoming_only=cfg.get("upcoming_only", True),
            progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        prog.empty()
        st.error(f"Lỗi khi thu thập: {type(exc).__name__}: {exc}")
        return
    prog.empty()

    st.session_state[STATE_KEY] = {"records": records, "status": status}
    st.success(f"Đã thu thập **{len(records)}** mục từ {len(status)} nguồn.")
    st.dataframe(pd.DataFrame(status), hide_index=True, width="stretch")
    if not records:
        ui.warn_box(
            "Không thu được mục nào. Kiểm tra kết nối Internet, hoặc tắt bộ lọc "
            "«Chỉ giữ nội dung giống HOẠT ĐỘNG» rồi thử lại."
        )


def _render_results() -> None:
    data = st.session_state.get(STATE_KEY)
    if not data or not data.get("records"):
        return
    records: list[dict] = data["records"]
    st.divider()
    st.subheader(f"📋 Xem trước {len(records)} mục thu được")

    df = pd.DataFrame(records)
    if "is_invitation" in df.columns:
        n_inv = int(df["is_invitation"].sum())
        st.caption(
            f"Trong đó **{n_inv}** mục có lời mời đăng ký/tham dự "
            f"(cột *Mời tham gia* = ✅) — đây thường là hoạt động bạn có thể tham gia thật."
        )
        df = df.copy()
        df["is_invitation"] = df["is_invitation"].map(lambda v: "✅" if v else "")
    show_cols = [c for c in ("source_key", "is_invitation", "title", "published_at",
                             "start_time", "end_time", "location", "organizer", "url")
                 if c in df.columns]
    st.dataframe(
        df[show_cols].rename(columns={
            "source_key": "Nguồn", "is_invitation": "Mời tham gia", "title": "Tiêu đề",
            "published_at": "Ngày đăng",
            "start_time": "Bắt đầu", "end_time": "Kết thúc", "location": "Địa điểm",
            "organizer": "Đơn vị", "url": "Link gốc",
        }),
        hide_index=True, width="stretch", height=420,
    )

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        if st.button("💾 Lưu tất cả vào SQLite (phân tích NLP tự động)",
                     type="primary", key="save_crawl"):
            sp = st.spinner("Đang lưu và phân tích…")
            with sp:
                res = crawler.save_crawled_posts(records)
            st.success(
                f"Đã lưu **{res['n_posts']} bài đăng** → **{res['n_activities']} hoạt động** "
                f"vào database (chỉ mục ĐỦ thông tin)."
            )
            _gate_row(res)
            if res["by_label"]:
                st.write("Phân loại tự động:", ", ".join(
                    f"**{k}**: {v}" for k, v in sorted(res["by_label"].items())
                ))
            if res["by_source"]:
                st.caption("Theo nguồn: " + ", ".join(
                    f"{crawler.SOURCE_TYPE_LABELS.get(k, k)} = {v}"
                    for k, v in res["by_source"].items()
                ))
            if res["errors"]:
                with st.expander(f"⚠️ {len(res['errors'])} mục lỗi khi lưu"):
                    for e in res["errors"]:
                        st.text(e)
            st.info("Mở **Tab 4 – Kho hoạt động** để xem dữ liệu vừa lưu.")
    with c2:
        st.download_button(
            "⬇️ Tải bản xem trước (CSV)",
            data=df[show_cols].to_csv(index=False).encode("utf-8-sig"),
            file_name="hcmus_crawled_preview.csv",
            mime="text/csv",
            key="dl_crawl_csv",
        )
    with c3:
        if st.button("🗑️ Xoá bản xem trước", key="clear_crawl"):
            st.session_state.pop(STATE_KEY, None)
            st.rerun()


def _render_database_summary() -> None:
    st.divider()
    st.subheader("🗄️ Tình trạng database")
    try:
        acts = database.get_activities()
        sources = database.get_sources()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Chưa đọc được database: {exc}")
        return

    real = acts[acts["is_demo"] == 0] if "is_demo" in acts else acts
    m1, m2, m3 = st.columns(3)
    m1.metric("Tổng hoạt động", len(acts))
    m2.metric("Hoạt động sắp/đang diễn ra", len(real),
              help="Đã qua bộ lọc: chỉ giữ hoạt động chưa diễn ra")
    m3.metric("Nguồn đã cấu hình", len(sources))

    if not sources.empty:
        st.markdown("**Các nguồn đã ghi nhận trong bảng `Sources`:**")
        show = sources.rename(columns={
            "id": "ID", "name": "Tên nguồn", "url": "URL", "source_type": "Loại",
            "connection_status": "Trạng thái", "last_synced_at": "Đồng bộ lần cuối",
        })
        st.dataframe(show, hide_index=True, width="stretch")

    if not real.empty:
        st.markdown("**Hoạt động thật mới nhất (10 dòng):**")
        cols = [c for c in ("title", "organizer", "location", "start_time", "end_time",
                            "relevance_label") if c in real.columns]
        st.dataframe(
            real[cols].sort_values("start_time", ascending=False).head(10).rename(columns={
                "title": "Tiêu đề", "organizer": "Đơn vị", "location": "Địa điểm",
                "start_time": "Bắt đầu", "end_time": "Kết thúc", "relevance_label": "Nhãn",
            }),
            hide_index=True, width="stretch",
        )


def _render_cleanup_tools() -> None:
    """Dọn kho: xoá hoạt động thật đã kết thúc."""
    st.divider()
    st.subheader("🧽 Dọn hoạt động ĐÃ DIỄN RA")
    try:
        acts = database.get_activities()
        n_real = int((acts["is_demo"] == 0).sum()) if "is_demo" in acts else 0
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Không đọc được database: {exc}")
        return
    st.caption(
        f"Kho đang có **{n_real}** hoạt động thật. Nếu trong đó còn sự kiện đã kết thúc "
        "(do lượt thu thập trước lấy cả lịch sử), bấm nút dưới để xoá. "
        "Hoạt động **không rõ ngày** được giữ nguyên vì chưa kết luận được là đã qua."
    )
    if st.button("🧽 Xoá hoạt động thật đã kết thúc", key="purge_expired"):
        res = database.purge_expired_real_activities()
        st.success(f"Đã xoá **{res['deleted']}** hoạt động đã kết thúc.")
        st.rerun()


def _render_dedup_tools() -> None:
    """Công cụ gộp trùng lặp – hữu ích khi đã chạy thu thập nhiều lần."""
    st.divider()
    st.subheader("🧹 Gộp hoạt động trùng lặp")
    st.caption(
        "Chính sách MVP: **cho phép trùng** — mỗi lượt thu thập ghi thêm bản mới để "
        "giữ lịch sử. Khi bạn thấy kho quá nhiều bản lặp, bấm nút dưới để gộp: "
        "hệ thống giữ **một** bản cho mỗi hoạt động (bản có điểm cao nhất / đầy đủ "
        "thông tin nhất) và bổ sung các trường còn trống từ bản khác."
    )
    try:
        dup = database.count_duplicates()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Không đếm được trùng lặp: {exc}")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Bản ghi trùng (cùng bài)", dup.get("dup_by_post_id", 0))
    c2.metric("Hoạt động trùng tiêu đề", dup.get("dup_by_title", 0))
    c3.metric("Tổng dư thừa", dup.get("dup_by_title", 0))

    total = dup.get("dup_by_title", 0)
    if total == 0:
        st.success("Không phát hiện hoạt động trùng. Kho dữ liệu đang sạch.")
        return
    if st.button(f"🧹 Gộp {total} bản trùng ngay", type="primary", key="merge_dups"):
        res = database.merge_duplicates()
        st.success(
            f"Đã gộp **{res['groups_merged']}** nhóm, xoá **{res['rows_deleted']}** bản dư thừa."
        )
        st.rerun()


def _auto_crawl_if_empty() -> None:
    """Lần đầu mở app: tự thu thập dữ liệu thật, không bắt người dùng bấm gì.

    Chỉ chạy khi DB **chưa có hoạt động thật nào** và người dùng chưa tắt tính năng
    này. Lỗi mạng không làm hỏng app – chỉ hiện cảnh báo.
    """
    if st.session_state.get("auto_crawl_done"):
        return
    if st.session_state.get("auto_crawl_disabled"):
        return
    try:
        acts = database.get_activities()
        n_real = int((acts["is_demo"] == 0).sum()) if "is_demo" in acts else 0
    except Exception:  # noqa: BLE001
        return
    if n_real > 0:
        st.session_state["auto_crawl_done"] = True
        return

    st.session_state["auto_crawl_done"] = True
    st.info(
        "🚀 **Lần đầu khởi động:** đang tự động thu thập hoạt động thật từ 4 cổng công khai "
        "của trường. Quá trình mất khoảng 10–30 giây…"
    )
    prog = st.progress(0.0, text="Đang kết nối cổng trường…")

    def on_progress(msg: str) -> None:
        prog.progress(min(0.95, 0.15 + 0.1 * len(msg)), text=str(msg)[:110])

    try:
        records, status = crawler.crawl_to_records(
            max_pages=2, per_page=30, activity_only=True, upcoming_only=True,
            progress=on_progress,
        )
    except Exception as exc:  # noqa: BLE001
        prog.empty()
        ui.warn_box(
            f"Không tự thu thập được ({type(exc).__name__}). Có thể do máy không có Internet "
            "hoặc cổng trường tạm đóng. Bấm **🚀 Bắt đầu thu thập** bên dưới để thử lại, "
            "hoặc dùng **📥 Thu thập OSA (thủ công)** để dán bài đăng."
        )
        return
    prog.empty()

    if not records:
        ui.warn_box("Không thu được mục nào. Bấm **🚀 Bắt đầu thu thập** để thử lại.")
        return

    with st.spinner(f"Đang lưu & phân tích {len(records)} mục…"):
        res = crawler.save_crawled_posts(records)
    st.success(
        f"✅ Đã tự thu thập **{res['n_activities']} hoạt động THẬT** từ "
        f"{len(status)} nguồn và lưu vào database. Mở **Tab 🗂️ Kho hoạt động** để xem."
    )
    _gate_row(res)
    st.dataframe(pd.DataFrame(status), hide_index=True, width="stretch")


def render() -> None:
    ui.hero(
        "🌐 Thu thập TỰ ĐỘNG từ cổng công khai HCMUS",
        "Tự động đi tìm hoạt động/sự kiện/workshop trên web trường và lưu vào database. "
        "Không cần dán link, không cần đăng nhập.",
    )
    if st.session_state.get("auto_crawl_disabled"):
        st.caption("ℹ️ Tự động thu thập lần đầu đang TẮT. Bấm nút bên dưới để chạy thủ công.")
    else:
        _auto_crawl_if_empty()

    tab_a, tab_b, tab_c = st.tabs([
        "🚀 Thu thập ngay", "🌐 Danh sách nguồn", "🗄️ Trạng thái database",
    ])
    with tab_a:
        st.markdown(
            "Bấm **Bắt đầu thu thập** — hệ thống sẽ gọi trực tiếp API công khai của "
            "Phòng CTSV, Lịch sự kiện Trường, Tin tức Trường và trang Khoa CNTT, "
            "sau đó bóc tách thời gian / địa điểm / đơn vị và lưu vào SQLite."
        )
        cfg = _render_controls()
        st.divider()
        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button("🚀 Bắt đầu thu thập", type="primary", key="start_crawl"):
                _run_crawl(cfg)
            if st.checkbox("Tắt tự động thu thập lần đầu", key="auto_crawl_off",
                           value=bool(st.session_state.get("auto_crawl_disabled"))):
                st.session_state["auto_crawl_disabled"] = True
            else:
                st.session_state["auto_crawl_disabled"] = False
        with col_b:
            if st.button("🩺 Kiểm tra nguồn còn sống không", key="health_crawl"):
                with st.spinner("Đang kiểm tra…"):
                    rows = crawler.health_check()
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        _render_results()
        _render_cleanup_tools()
        _render_dedup_tools()
    with tab_b:
        _render_sources_overview()
    with tab_c:
        _render_database_summary()
