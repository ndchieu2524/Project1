"""TAB 3 – Kho Hoạt động & Cảnh báo Dữ liệu Khuyết (Pandas Explorer)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config, database, score_estimate, nlp_engine
from . import ui_common as ui

VIEW_ALL = "Tất cả bài đăng OSA"
VIEW_POTENTIAL = "Hoạt động Tiềm năng (POTENTIAL_DRL)"
VIEW_VERIFIED = "Đã xác minh (VERIFIED_DRL)"
VIEW_INSUFFICIENT = "Bài thiếu thông tin (INSUFFICIENT_INFO)"
VIEW_NOT_RELEVANT = "Bài không liên quan (NOT_RELEVANT)"
VIEW_CANDIDATE = "Chưa rõ quyền lợi ĐRL (EVENT_CANDIDATE)"


def _filtered(df: pd.DataFrame, view: str) -> pd.DataFrame:
    mapping = {
        VIEW_POTENTIAL: config.LABEL_POTENTIAL,
        VIEW_VERIFIED: config.LABEL_VERIFIED,
        VIEW_INSUFFICIENT: config.LABEL_INSUFFICIENT,
        VIEW_NOT_RELEVANT: config.LABEL_NOT_RELEVANT,
        VIEW_CANDIDATE: config.LABEL_EVENT_CANDIDATE,
    }
    if view in mapping:
        df = df[df["relevance_label"] == mapping[view]]
    return df


def _verify_panel(activity_id: int) -> None:
    record = database.get_activity(activity_id)
    if not record:
        st.error("Không tìm thấy hoạt động.")
        return
    st.markdown(f"#### 🛠️ Duyệt hoạt động #{activity_id} {ui.label_badge(record.get('relevance_label', ''))}",
                unsafe_allow_html=True)
    st.markdown(f"**{record.get('title')}**")
    cols = st.columns(4)
    cols[0].write(f"⏰ {record.get('start_time') or '—'} → {record.get('end_time') or '—'}")
    cols[1].write(f"📍 {record.get('location') or '—'}")
    _est = score_estimate.estimate_for_activity(record)
    cols[2].write(f"🏆 ~{score_estimate.format_range(_est['min'], _est['max'])} "
                  f"(ước lượng)<br/><small>{_est['label']}</small>",
                  unsafe_allow_html=True)
    cols[3].write(f"🎯 {record.get('criterion_code') or '—'}")

    # Chi tiết bóc tách thêm: thời lượng, diễn giả, hạn nộp, và CÂU GỐC để đối chiếu
    d1, d2, d3 = st.columns(3)
    duration = record.get("duration_minutes")
    d1.write(f"⏳ Thời lượng: **{duration} phút**" if duration else "⏳ Thời lượng: —")
    d2.write(f"🎤 Diễn giả: **{record.get('speaker')}**" if record.get("speaker")
             else "🎤 Diễn giả: —")
    d3.write(f"📝 Hạn đăng ký: **{record.get('registration_deadline')}**"
             if record.get("registration_deadline") else "📝 Hạn đăng ký: —")
    proof = [("Ngày diễn ra", record.get("start_raw")),
             ("Kết thúc", record.get("end_raw"))]
    proof = [(k, v) for k, v in proof if v]
    if proof:
        with st.expander("🔍 Câu gốc dùng để bóc ngày (đối chiếu)"):
            st.caption("Hệ thống KHÔNG đoán: mỗi ngày đều truy vết được về câu gốc dưới đây.")
            for label, raw in proof:
                st.markdown(f"**{label}** — trích từ bài đăng:")
                st.code(str(raw)[:400], language=None)
    if record.get("post_url"):
        st.caption(f"Nguồn: {record['post_url']} · phương thức: {record.get('fetch_method') or '—'}")
    flags = [name for key, name in [("is_missing_time", "Thời gian"),
                                    ("is_missing_location", "Địa điểm"),
                                    ("is_missing_content", "Nội dung"),
                                    ("is_missing_score", "Điểm ĐRL")]
             if ui.to_int(record.get(key)) == 1]
    if flags:
        ui.warn_box("Hoạt động đang thiếu: **" + ", ".join(flags) + "**. "
                    "Chỉ nên xác minh khi đã bổ sung đủ 4 nhóm thông tin.")

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            new_label = st.selectbox(
                "Nhãn sau duyệt", config.RELEVANCE_LABELS,
                index=config.RELEVANCE_LABELS.index(record.get("relevance_label")
                                                    if record.get("relevance_label") in config.RELEVANCE_LABELS
                                                    else config.LABEL_POTENTIAL),
                key=f"v_label_{activity_id}",
            )
            current_status = record.get("verification_status") or config.VERIFY_NONE
            new_status = st.selectbox(
                "Trạng thái xác minh", config.VERIFICATION_STATUSES,
                index=(config.VERIFICATION_STATUSES.index(current_status)
                       if current_status in config.VERIFICATION_STATUSES else 0),
                key=f"v_status_{activity_id}",
            )
        with c2:
            st.caption("Điểm của hoạt động là **ước lượng** (thông lệ 3–5đ), không phải "
                       "điểm chính thức. Để trống nếu chưa muốn chỉnh.")
            sc_a, sc_b = st.columns(2)
            est = score_estimate.estimate_for_activity(record)
            new_min = sc_a.number_input("Ước lượng thấp", min_value=0.0, max_value=30.0,
                                        value=float(est["min"]), step=0.5,
                                        key=f"v_score_min_{activity_id}")
            new_max = sc_b.number_input("Ước lượng cao", min_value=0.0, max_value=30.0,
                                        value=float(est["max"]), step=0.5,
                                        key=f"v_score_max_{activity_id}")
            if new_max < new_min:
                st.error("Ước lượng cao phải ≥ ước lượng thấp.")
            new_score = (new_min + new_max) / 2
            criteria = database.get_criteria()
            codes = ["(giữ nguyên)"] + list(criteria["code"])
            current_code = record.get("criterion_code")
            new_code = st.selectbox(
                "Mã tiêu chí", codes,
                index=codes.index(current_code) if current_code in codes else 0,
                key=f"v_code_{activity_id}",
            )
        note = st.text_area(
            "Ghi chú của Admin (bắt buộc khi chuyển sang VERIFIED_DRL)", height=80,
            key=f"v_note_{activity_id}",
            placeholder="VD: Đã đối chiếu danh sách điểm danh do Đoàn Khoa cung cấp ngày …",
        )
        parent_candidates = database.get_activities()
        parent_candidates = parent_candidates[parent_candidates["id"] != activity_id]
        parent_options = ["(không gắn)"] + [
            f"#{row['id']} – {str(row['title'])[:70]}" for _, row in parent_candidates.iterrows()]
        parent_choice = st.selectbox("Gắn vào sự kiện gốc (parent_activity_id)", parent_options,
                                     key=f"v_parent_{activity_id}")

        if st.button("💾 Cập nhật hoạt động", type="primary", key=f"v_submit_{activity_id}"):
            if new_label == config.LABEL_VERIFIED and not note.strip():
                st.error("Chuyển sang VERIFIED_DRL yêu cầu ghi chú căn cứ xác minh "
                         "(quy chế / danh sách điểm danh).")
            elif new_label == config.LABEL_VERIFIED and new_max <= 0:
                st.error("VERIFIED_DRL phải có ước lượng điểm > 0 (không tự bịa điểm).")
            else:
                # Nhãn VERIFIED_DRL luôn đi kèm trạng thái đã xác minh – tránh dữ liệu
                # tự mâu thuẫn (VERIFIED nhưng vẫn NEEDS_HUMAN_REVIEW).
                effective_status = new_status
                if new_label == config.LABEL_VERIFIED and new_status in (
                        config.VERIFY_NONE, config.VERIFY_NEEDS_REVIEW):
                    effective_status = config.VERIFY_ADMIN_APPROVED
                if new_label != config.LABEL_VERIFIED and new_status in (
                        config.VERIFY_ADMIN_APPROVED, config.VERIFY_RULE_CITED):
                    effective_status = config.VERIFY_NEEDS_REVIEW
                updates = {
                    "expected_score": new_score if new_max > 0 else None,
                    "expected_score_min": new_min if new_max > 0 else None,
                    "expected_score_max": new_max if new_max > 0 else None,
                    "score_estimate_source": config.SCORE_ESTIMATE_SOURCE_ADMIN,
                    # Mọi hoạt động đều có ước lượng → không còn khái niệm "thiếu điểm"
                    "is_missing_score": 0,
                }
                if new_code != "(giữ nguyên)":
                    updates["criterion_code"] = new_code
                database.update_activity(activity_id, updates)
                database.set_verification_status(activity_id, effective_status,
                                                 label=new_label,
                                                 note=note.strip() or None)
                if parent_choice != "(không gắn)":
                    parent_id = int(parent_choice.split("–")[0].strip().lstrip("#"))
                    database.link_parent_activity(activity_id, parent_id)
                database.log_action("ADMIN_REVIEW", {
                    "activity_id": activity_id, "label": new_label,
                    "status": effective_status, "note": note[:200]})
                st.toast(f"Đã cập nhật hoạt động #{activity_id} → {new_label} "
                         f"({effective_status}).", icon="✅")
                st.rerun()


def render() -> None:
    ui.hero(
        "🗂️ Kho Hoạt động & Cảnh báo Dữ liệu Khuyết",
        "Bảng Pandas đa bộ lọc · ô thiếu Thời gian/Địa điểm/Nội dung/Điểm được tô đỏ · "
        "Admin duyệt chuyển trạng thái sang VERIFIED_DRL.",
    )
    activities = database.get_activities()
    if activities.empty:
        ui.note_box(
            "Kho đang trống. Ứng dụng **không có dữ liệu mẫu** — hãy mở "
            "**🌐 Thu thập TỰ ĐỘNG** và bấm *🚀 Bắt đầu thu thập* để lấy hoạt động thật "
            "từ 4 cổng công khai của trường."
        )
        return

    stats = database.dashboard_stats()

    # --- Dữ liệu mẫu còn sót (từ bản cũ) → cảnh báo + nút dọn ---
    n_demo_all = int((activities["is_demo"] == 1).sum()) if "is_demo" in activities else 0
    n_real = len(activities) - n_demo_all
    if n_demo_all:
        cw1, cw2 = st.columns([3, 1])
        with cw1:
            ui.warn_box(
                f"Kho còn **{n_demo_all} hoạt động mẫu** từ bản cũ. Bản này **không tạo** "
                "dữ liệu mẫu nữa — bấm nút bên phải để xoá sạch."
            )
        with cw2:
            if st.button("🧽 Xoá hoạt động mẫu", key="purge_demo_tab3", width="stretch"):
                removed = database.purge_demo_activities()
                st.success(f"Đã xoá **{removed['activities']}** hoạt động mẫu "
                           f"và **{removed['posts']}** bài đăng mẫu.")
                st.rerun()
    elif n_real:
        st.caption(f"Kho có **{n_real}** hoạt động thu thập THẬT từ cổng trường.")

    # --- Tách hoạt động còn dùng được / đã diễn ra ---
    from datetime import datetime as _dt

    def _parse_day(value) -> "object":
        raw = str(value or "")
        if len(raw) < 10:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return _dt.strptime(raw[:16] if ":" in raw else raw[:10], fmt).date()
            except ValueError:
                continue
        return None

    def _verdict(row) -> str:
        """Phân loại theo NGÀY KẾT THÚC: hội nghị nhiều ngày vẫn tính là còn diễn ra.

        Chỉ dựa vào ngày bắt đầu sẽ ẩn nhầm sự kiện đang diễn ra (ví dụ hội nghị
        09–16/11 khi hôm nay là 14/11) — đây là lỗi đã gặp trên dữ liệu thật.
        """
        end_day = _parse_day(row.get("end_time")) or _parse_day(row.get("start_time"))
        if end_day is None:
            return "unknown"
        return "past" if end_day < _dt.now().date() else "upcoming"

    _today = _dt.now().date()
    activities = activities.copy()
    activities["_when"] = activities.apply(_verdict, axis=1)
    n_past = int((activities["_when"] == "past").sum())
    if n_past and n_real:
        st.warning(
            f"Có **{n_past}** hoạt động thật **đã diễn ra**. Bạn có thể bấm nút bên dưới "
            "để ẩn chúng, hoặc xoá hẳn ở Tab 🌐 Thu thập TỰ ĐỘNG."
        )

    cols = st.columns(5)
    cols[0].metric("Tổng hoạt động", stats["n_activities"])
    cols[1].metric("Đã xác minh", stats["n_verified"])
    cols[2].metric("Tiềm năng", stats["n_potential"])
    cols[3].metric("Thiếu thông tin", stats["n_insufficient"])
    cols[4].metric("Không liên quan", stats["n_not_relevant"])

    view = st.radio("Bộ lọc trạng thái", [
        VIEW_ALL, VIEW_POTENTIAL, VIEW_VERIFIED, VIEW_INSUFFICIENT,
        VIEW_NOT_RELEVANT, VIEW_CANDIDATE,
    ], horizontal=True)

    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        keyword = st.text_input("Tìm theo tên / đơn vị tổ chức", placeholder="vd: hội thảo, hiến máu…")
    with fcol2:
        criteria = database.get_criteria()
        code_choice = st.multiselect("Tiêu chí", list(criteria["code"]))
    with fcol3:
        only_missing = st.checkbox("Chỉ dòng thiếu dữ liệu", value=False)
        hide_past = st.checkbox("⏳ Ẩn hoạt động đã diễn ra", value=True,
                                help="Chỉ hiện hoạt động còn diễn ra hoặc chưa có ngày.")
    with fcol4:
        campus_choice = st.multiselect("Cơ sở", config.CAMPUSES)

    df = _filtered(activities, view)
    if keyword.strip():
        kw = nlp_engine.strip_accents(keyword.strip())
        mask = (
            df["title"].fillna("").apply(lambda t: kw in nlp_engine.strip_accents(t))
            | df["organizer"].fillna("").apply(lambda t: kw in nlp_engine.strip_accents(t))
        )
        df = df[mask]
    if code_choice:
        df = df[df["criterion_code"].isin(code_choice)]
    if hide_past and "_when" in df.columns:
        df = df[df["_when"] != "past"]
    if only_missing:
        miss_cols = [c for c in ("is_missing_time", "is_missing_location", "is_missing_content")
                     if c in df.columns]
        if miss_cols:
            df = df[df[miss_cols].sum(axis=1) > 0]
    if campus_choice:
        df = df[df["campus"].isin(campus_choice)]

    # Cột "Đã tham gia": tiến độ DỰ ĐOÁN cộng dồn theo các dòng có dấu ✅.
    from . import progress_predict as pp
    done_ids = pp.completed_ids()
    if not df.empty:
        df = df.copy()
        df["_done"] = df["id"].apply(lambda v: 1 if int(v) in done_ids else 0)

    note = (f"Hiển thị **{len(df)}** / {len(activities)} hoạt động · "
            "cột **Tình trạng** cho biết trường nào còn thiếu.")
    st.caption(note)
    ui.show_activities_table(df, height=440, key="explorer_table")
    ui.download_csv_button(
        ui.activities_to_display_df(df), "smart_drl_activities.csv",
        "⬇️ Xuất bảng hiện tại ra CSV", "dl_explorer",
    )

    st.divider()
    st.subheader("✅ Duyệt & cập nhật hoạt động (Admin)")
    if df.empty:
        st.caption("Không có dòng nào để duyệt với bộ lọc hiện tại.")
    else:
        options = [f"#{row['id']} – {str(row['title'])[:90]}" for _, row in df.iterrows()]
        picked = st.selectbox("Chọn hoạt động để duyệt", options, key="verify_pick")
        activity_id = int(picked.split("–")[0].strip().lstrip("#"))
        _verify_panel(activity_id)

    # --- Chi tiết bài đăng gốc ---
    with st.expander("📄 Xem bài đăng gốc & cây liên kết sự kiện (Event Update Linking)"):
        posts = database.get_posts()
        if posts.empty:
            st.caption("Chưa có bài đăng gốc.")
        else:
            pick_post = st.selectbox(
                "Chọn bài đăng", [f"#{r['id']} – {(r['raw_text'] or '')[:80]}…" for _, r in posts.iterrows()],
                key="post_pick")
            post_id = int(pick_post.split("–")[0].strip().lstrip("#"))
            post = database.get_post(post_id)
            st.markdown(f"**URL:** {post.get('url')}  \n"
                        f"**Phương thức:** `{post.get('fetch_method')}` · "
                        f"**Thu thập:** {post.get('collected_at')} · "
                        f"**content_hash:** `{(post.get('content_hash') or '')[:24]}…` · "
                        f"**external_post_id:** `{post.get('external_post_id') or '—'}`")
            if ui.to_int(post.get("is_demo")):
                st.markdown(ui.demo_tag() + " Bài đăng mẫu, không phải dữ liệu thật.",
                            unsafe_allow_html=True)
            st.text_area("Nội dung gốc", post.get("raw_text", ""), height=180,
                         key=f"raw_{post_id}", disabled=True)

            related = activities[activities["source_post_id"] == post_id]
            if not related.empty:
                for _, row in related.iterrows():
                    parent = ui.to_int(row.get("parent_activity_id"))
                    parent_note = (f" ⤴ bài cập nhật của hoạt động #{parent}"
                                   if parent else "")
                    st.write(f"- Hoạt động **#{row['id']}** – {row['title']} "
                             f"({row['relevance_label']}){parent_note}")

            dup = posts[posts["content_hash"] == post.get("content_hash")]
            if len(dup) > 1:
                st.caption(
                    f"⚠️ content_hash này xuất hiện ở {len(dup)} bản ghi (IDs: "
                    f"{list(dup['id'])}). MVP chấp nhận trùng lặp – hash là tiền đề chống trùng sau này."
                )
