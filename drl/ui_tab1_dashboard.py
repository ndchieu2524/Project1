"""TAB 1 – Dashboard & Đồng bộ Plugin (Portal CTĐB & hcmus.drl.vn)."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from . import config, database
from . import ui_common as ui


def _range_txt(lo, hi) -> str:
    """Chuỗi khoảng điểm: '12–20đ' hoặc '4đ'."""
    lo_f, hi_f = float(lo or 0), float(hi or 0)
    if abs(lo_f - hi_f) < 0.01:
        return f"{lo_f:g}đ"
    return f"{lo_f:g}–{hi_f:g}đ"


def _metric_row(profile: dict, pred: dict) -> None:
    """4 ô số liệu của Dashboard.

    Điểm chính thức (nếu đã quét hcmus.drl.vn) và điểm DỰ ĐOÁN đứng RIÊNG nhau:
    trộn hai nguồn sẽ khiến người dùng không biết con số nào cộng vào đâu.
    """
    # None = CHƯA đồng bộ điểm (gói JSON chỉ có TKB). 0 = thật sự 0 điểm.
    raw_score = profile.get("current_total_score")
    has_score = raw_score is not None and str(raw_score).strip() != ""
    current = float(raw_score) if has_score else 0.0
    target = float(profile.get("target_score") or 0)
    totals = pred["totals"]
    pred_min, pred_max = totals["min"], totals["max"]
    capacity = totals["max_score"]

    c1, c2, c3, c4 = st.columns(4)
    if has_score:
        c1.metric("① Điểm chính thức (hcmus.drl.vn)", f"{current:g}",
                  delta="đã quét từ trang trường", delta_color="off",
                  help="Số điểm chính thức đọc được khi quét trang hcmus.drl.vn. "
                       "Đây là nguồn duy nhất quyết định kết quả học kỳ.")
    else:
        c1.metric("① Điểm chính thức (hcmus.drl.vn)", "chưa đồng bộ",
                  delta="KHÔNG phải 0 điểm", delta_color="off",
                  help="Gói JSON này chỉ chứa thời khóa biểu, hoặc bạn chưa quét trang "
                       "hcmus.drl.vn — hệ thống CHƯA biết điểm của bạn.")

    c2.metric("② Tiến độ DỰ ĐOÁN", _range_txt(pred_min, pred_max),
              delta=f"từ {totals['n_activities']} HĐ đã tham gia"
                    if totals["n_activities"] else "chưa đánh dấu HĐ nào",
              delta_color="off",
              help="Mỗi hoạt động bạn đánh dấu hoàn thành sẽ được cộng ước lượng "
                   "3–5đ vào đúng nhóm tiêu chí. Đây là DỰ ĐOÁN, không phải điểm "
                   "chính thức — điểm thật do Phòng CTSV duyệt.")

    if capacity:
        # Dự đoán / trần điểm, kèm khoảng còn lại.
        room_min = max(0.0, capacity - pred_max)
        room_max = max(0.0, capacity - pred_min)
        c3.metric("③ Còn có thể đạt", _range_txt(room_min, room_max),
                  delta=f"theo trần {capacity:g}đ của 5 nhóm", delta_color="off",
                  help="= điểm tối đa của 5 nhóm trừ đi phần dự đoán nhanh nhất / "
                       "chậm nhất. Cộng dồn không bao giờ vượt trần từng nhóm.")
    else:
        c3.metric("③ Còn có thể đạt", "chưa rõ trần điểm",
                  delta="nạp khung quy chế ở Tab 📜", delta_color="off",
                  help="Chưa có khung quy chế nên không biết điểm tối đa của nhóm.")

    gap = max(0.0, target - pred_max)
    c4.metric("④ Mục tiêu học kỳ", f"{target:g}",
              delta=(f"dự đoán còn thiếu {gap:g} điểm" if gap > 0
                     else "dự đoán đã đạt mục tiêu"),
              delta_color="inverse" if gap > 0 else "normal",
              help="So mục tiêu với CẬN TRÊN của khoảng dự đoán. Đây là dự đoán, "
                   "không phải cam kết điểm.")


def _progress_chart(pred: dict) -> None:
    """Biểu đồ tiến độ DỰ ĐOÁN theo từng nhóm tiêu chí.

    Mỗi cột = [điểm dự đoán] + [phần còn trống tới điểm tối đa]. Hai lớp này cộng
    lại luôn bằng đúng điểm tối đa của nhóm, nhờ vậy nhìn là biết đang ở đâu trên
    thang 20/20/30/15/15.
    """
    rows = [r for r in pred["rows"] if r["max_score"]]
    if not rows:
        return
    chart_rows = []
    for r in rows:
        cap = float(r["max_score"])
        chart_rows.append({
            "Nhóm": r["criterion_code"],
            "Dự đoán (thấp)": round(float(r["pred_min"]), 2),
            "Còn trống": round(max(0.0, cap - float(r["pred_min"])), 2),
        })
    chart_df = pd.DataFrame(chart_rows).set_index("Nhóm")
    cap_map = {r["criterion_code"]: r["max_score"] for r in rows}
    st.caption(
        "Dự đoán / điểm tối đa từng nhóm — "
        + " · ".join(f"{code}: {cap_map[code]:g}đ" for code in chart_df.index)
    )
    st.bar_chart(chart_df, stack=True, height=260,
                 color=["#2563eb", "#e2e8f0"])


def _render_predict_panel(sid: str) -> None:
    """Bảng tiến độ DỰ ĐOÁN + chỗ đánh dấu hoạt động đã hoàn thành."""
    from . import progress_predict as pp

    pred = pp.predict_progress(semester=None)
    st.subheader("📈 Tiến độ DỰ ĐOÁN từng nhóm tiêu chí")
    ui.note_box(
        "Bảng này **không** phải điểm chính thức. Mỗi nhóm giữ nguyên điểm tối đa của "
        "trang trường; khi bạn bấm **Đã tham gia** một hoạt động, khoảng dự đoán 3–5đ "
        "của hoạt động đó được **cộng ngay** vào nhóm tương ứng (không vượt trần)."
    )
    if pred["rows"]:
        st.dataframe(pp.progress_dataframe(pred), width="stretch", hide_index=True,
                     height=260)
        st.caption("**" + pp.summarize(pred) + "** · mọi con số là dự đoán.")
    if pred["overflow"]:
        detail = " · ".join(
            f"**{o['criterion_code']}** {o['min']:g}đ > trần {o['max_score']:g}đ"
            for o in pred["overflow"])
        ui.warn_box(
            "Một số nhóm đã **vượt trần** nên phần dư không được cộng: " + detail
            + ". Đây là giới hạn của quy chế, không phải lỗi dữ liệu."
        )


def _render_done_panel(sid: str) -> None:
    """Đánh dấu / bỏ đánh dấu hoạt động đã hoàn thành → tiến độ tự cập nhật."""
    from . import progress_predict as pp, score_estimate

    st.subheader("✅ Đánh dấu hoạt động đã tham gia")
    activities = database.get_activities(include_demo=False)
    if activities.empty:
        ui.note_box(
            "Kho đang trống nên chưa có gì để đánh dấu. Mở tab "
            "**🌐 Thu thập TỰ ĐỘNG** bấm *Bắt đầu thu thập* để lấy hoạt động thật "
            "từ cổng trường."
        )
        return
    done = pp.completed_ids()
    options = ["— chọn hoạt động —"]
    labels: dict[str, int] = {}
    for _, r in activities.iterrows():
        aid = int(r["id"])
        est = score_estimate.estimate_for_activity(r.to_dict())
        mark = "✔ " if aid in done else ""
        label = (f"{mark}#{aid} · {str(r['title'])[:72]} · "
                 f"{r.get('criterion_code') or 'chưa rõ tiêu chí'} · "
                 f"~{score_estimate.format_range(est['min'], est['max'])}")
        options.append(label)
        labels[label] = aid

    c1, c2 = st.columns([3, 1])
    with c1:
        picked = st.selectbox("Chọn hoạt động", options, key="done_pick")
    with c2:
        st.caption("Điểm cộng là **dự đoán** 3–5đ, không phải điểm chính thức.")
    col_a, col_b = st.columns(2)
    if picked != options[0]:
        aid = labels[picked]
        with col_a:
            if st.button("✅ Đã tham gia hoạt động này", type="primary",
                         width="stretch", key="done_mark_btn"):
                added = database.mark_activity_done(aid, student_id=sid)
                st.toast("Đã cộng dự đoán 3–5đ vào tiến độ." if added
                         else "Hoạt động này đã được đánh dấu trước đó.", icon="✅")
                st.rerun()
        with col_b:
            if st.button("↩️ Bỏ đánh dấu", width="stretch", key="done_unmark_btn"):
                removed = database.unmark_activity_done(aid, student_id=sid)
                st.toast("Đã bỏ đánh dấu và trừ lại phần dự đoán." if removed
                         else "Hoạt động này chưa được đánh dấu.", icon="↩️")
                st.rerun()

    completed = database.get_completed_activities(student_id=sid)
    if completed.empty:
        st.caption("Chưa đánh dấu hoạt động nào — tiến độ dự đoán đang là 0đ.")
    else:
        with st.expander(f"📌 {len(completed)} hoạt động đã đánh dấu hoàn thành"):
            show = completed[["activity_id", "title", "criterion_code",
                              "expected_score_min", "expected_score_max",
                              "completed_at"]].copy()
            show["expected_score_min"] = show["expected_score_min"].map(
                lambda v: "" if v is None else f"{float(v):g}")
            show["expected_score_max"] = show["expected_score_max"].map(
                lambda v: "" if v is None else f"{float(v):g}")
            show = show.rename(columns={
                "activity_id": "ID", "title": "Hoạt động",
                "criterion_code": "Nhóm", "expected_score_min": "Dự đoán thấp",
                "expected_score_max": "Dự đoán cao", "completed_at": "Đánh dấu lúc",
            })
            st.dataframe(show, width="stretch", hide_index=True, height=220)
            if st.button("🧹 Bỏ đánh dấu TẤT CẢ", key="done_reset_btn"):
                n = database.clear_completed_activities(student_id=sid)
                st.toast(f"Đã bỏ đánh dấu {n} hoạt động.", icon="🧹")
                st.rerun()


def _render_sync_section() -> None:
    """Đồng bộ hồ sơ từ Chrome Extension. Không có lựa chọn dữ liệu mẫu."""
    st.subheader("🔌 Đồng bộ từ Chrome Extension")
    ui.note_box(
        "Mở extension → chọn **Quét trang** khi đang đăng nhập cổng thời khóa biểu và "
        "hcmus.drl.vn → bấm **Xuất hcmus_sync.json** rồi tải lên đây (hoặc dán JSON)."
    )
    sync_mode = st.radio(
        "Cách nạp dữ liệu",
        ["Tải file hcmus_sync.json", "Dán chuỗi JSON"],
        horizontal=True, label_visibility="collapsed",
    )
    payload = None
    payload_origin = ""

    if sync_mode == "Tải file hcmus_sync.json":
        uploaded = st.file_uploader("Chọn file JSON", type=["json"], key="sync_upload")
        if uploaded is not None:
            payload_origin = f"file:{uploaded.name}:{uploaded.size}"
            try:
                payload = json.loads(uploaded.getvalue().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                st.error(f"File JSON không đọc được: {exc}")
    elif sync_mode == "Dán chuỗi JSON":
        text = st.text_area("Dán nội dung JSON", height=150, key="sync_paste",
                            placeholder='{"sync_source": "HCMUS_CHROME_EXTENSION_V1", ...}')
        if text.strip():
            import hashlib
            payload_origin = "paste:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            payload, parse_errors = ui.parse_sync_json_text(text)
            if parse_errors:
                st.error("⚠️ " + " · ".join(parse_errors[:3]))
                payload = None

    # --- Kiểm tra & áp dụng: CHỈ chạy khi người dùng bấm nút và chưa áp dụng bản này ---
    applied_origin = st.session_state.get("sync_applied_origin")
    if payload:
        ok, errors = ui.validate_sync_payload(payload)
        if not ok:
            st.error("Gói JSON chưa đúng chuẩn Schema 2:")
            for err in errors[:6]:
                st.write(f"- {err}")
        else:
            if payload.get("is_demo"):
                ui.warn_box(
                    "Gói JSON này tự khai báo là dữ liệu mẫu (`is_demo = true`). "
                    "Hãy dùng gói quét từ chính tài khoản của bạn."
                )
            if applied_origin == payload_origin and payload_origin:
                st.success("Gói JSON này đã được áp dụng trong phiên hiện tại (không ghi lặp lại).")
            elif st.button("📥 Áp dụng gói JSON vào hồ sơ", type="primary", key="apply_sync_btn"):
                info = ui.apply_sync_payload(payload)
                st.session_state["sync_applied_origin"] = payload_origin
                st.success(
                    f"Đã đồng bộ MSSV {info['student_id']} – {info['semester']}: "
                    f"{info['n_progress']} tiêu chí, {info['n_timetable']} tiết học."
                )
                if info.get("kept_previous_score"):
                    ui.warn_box(
                        "Gói JSON **không kèm tổng điểm ĐRL** (thường là gói chỉ chứa thời khóa biểu). "
                        "Hệ thống **giữ nguyên điểm đã đồng bộ trước đó** – không ghi đè bằng 0."
                    )
                if info.get("cleared_previous_progress"):
                    ui.warn_box(
                        "Gói JSON có **tổng điểm mới nhưng không kèm bảng tiêu chí**, nên bảng "
                        "tiêu chí CŨ đã được **xoá** — nếu giữ lại thì tổng điểm và bảng chi tiết "
                        "sẽ mâu thuẫn nhau (ví dụ tổng 0 mà mỗi tiêu chí vẫn hiện điểm). "
                        "Quét thêm trang **hcmus.drl.vn** để lấy lại bảng chi tiết."
                    )
                elif info.get("kept_previous_progress"):
                    ui.warn_box(
                        "Gói JSON **không kèm bảng tiêu chí chi tiết** và cũng không có tổng điểm "
                        "→ giữ nguyên tiến độ tiêu chí cũ. Hãy quét thêm trang **hcmus.drl.vn**."
                    )
                st.rerun()


def _render_sync_section_only() -> None:
    """Trang thay thế khi CHƯA có hồ sơ: chỉ hiện phần đồng bộ, không số liệu giả."""
    _render_sync_section()


def render() -> None:
    ui.hero(
        "📊 Dashboard & Đồng bộ Plugin HCMUS",
        "Tổng quan Điểm rèn luyện – đồng bộ Thời khóa biểu CTĐB và tiến độ tiêu chí từ "
        "Chrome Extension, hoàn toàn không lưu mật khẩu cổng trường.",
    )

    profile = database.latest_profile()
    if not profile:
        ui.note_box(
            "Chưa có hồ sơ sinh viên. Hãy **đồng bộ JSON từ Chrome Extension** ở mục "
            "*Đồng bộ từ Chrome Extension* bên dưới. Ứng dụng **không tạo dữ liệu mẫu** – "
            "mọi con số hiển thị đều là số thật của bạn."
        )
        _render_sync_section_only()
        return

    sid = profile["student_id"]
    semester = profile["semester"]
    progress_df = database.get_criterion_progress(sid, semester)
    schedule_df = database.get_schedule(sid)

    # --- Cảnh báo tổng: dữ liệu đang xem là MẪU hay THẬT? ---
    # Dữ liệu mẫu đã được dọn tự động lúc khởi động; chỉ báo MỘT LẦN để người
    # dùng biết vì sao số liệu cũ biến mất (không phải lỗi mất dữ liệu thật).
    purged = st.session_state.pop("demo_purged_on_start", None)
    if purged:
        bits = []
        for key, label in (("profiles", "hồ sơ mẫu"), ("activities", "hoạt động mẫu"),
                           ("posts", "bài đăng mẫu"), ("progress", "dòng tiêu chí mẫu"),
                           ("schedule", "buổi lịch mẫu")):
            if int(purged.get(key) or 0):
                bits.append(f"**{int(purged[key])}** {label}")
        if bits:
            ui.note_box(
                "Đã tự động dọn dữ liệu mẫu của bản cũ khỏi database ("
                + ", ".join(bits) + "). Bản này **chỉ dùng dữ liệu thật** — hãy đồng bộ "
                "`hcmus_sync.json` từ Chrome Extension để nạp số liệu của chính bạn."
            )

    # --- Lộ trình đã tính (không tính lại AI) ---
    from . import progress_predict as pp, pathway
    route_activities = []
    try:
        result = pathway.compute_optimal_pathway(student_id=sid, semester=semester)
        if "route" in result:
            route_activities = result["route"]["activities"]
    except Exception:  # noqa: BLE001
        pass

    pred = pp.predict_progress()
    _metric_row(profile, pred)
    st.caption(ui.profile_summary_oneliner(profile))

    # --- Cảnh báo: chưa quét được điểm chính thức ---
    # "Chưa đồng bộ" KHÁC "0 điểm". Không có điểm chính thức chỉ ảnh hưởng mục
    # tiêu so với điểm thật, không chặn phần tiến độ dự đoán.
    has_detail = bool(profile.get("has_detailed_criteria")) and not progress_df.empty
    raw_score = profile.get("current_total_score")
    score_missing = raw_score is None or str(raw_score).strip() == ""
    if score_missing:
        ui.note_box(
            "Chưa có **điểm chính thức** từ hcmus.drl.vn (gói JSON chỉ chứa thời khóa "
            "biểu, hoặc bạn chưa quét trang ĐRL). Đây **không phải 0 điểm** — phần "
            "tiến độ bên dưới là **dự đoán** và vẫn hoạt động bình thường."
        )

    left, right = st.columns([1.15, 1])

    with left:
        st.subheader("🎯 Đặt mục tiêu học kỳ")
        with st.form("target_form", border=True):
            col_a, col_b = st.columns(2)
            new_target = col_a.number_input("Mục tiêu điểm ĐRL (0–100)", min_value=0.0,
                                            max_value=100.0,
                                            value=float(profile.get("target_score") or 90), step=1.0)
            new_semester = col_b.text_input("Học kỳ", value=semester)
            col_c, col_d = st.columns(2)
            new_sid = col_c.text_input("MSSV", value=sid)
            new_name = col_d.text_input("Họ tên", value=profile.get("full_name") or "")
            new_faculty = st.text_input("Khoa", value=profile.get("faculty") or "")
            if st.form_submit_button("💾 Lưu mục tiêu", type="primary"):
                database.upsert_profile({
                    **profile,
                    "student_id": new_sid.strip() or sid,
                    "full_name": new_name,
                    "faculty": new_faculty,
                    "semester": new_semester.strip() or semester,
                    "target_score": new_target,
                    "has_detailed_criteria": int(has_detail),
                })
                database.log_action("UPDATE_TARGET", {"student_id": new_sid, "target": new_target})
                st.success("Đã lưu mục tiêu học kỳ.")
                st.rerun()

        _progress_chart(pred)

    with right:
        _render_sync_section()

    # --- Tiến độ DỰ ĐOÁN + TKB ---
    st.divider()
    _render_predict_panel(sid)
    st.divider()
    _render_done_panel(sid)
    st.divider()
    st.subheader("🗓️ Thời khóa biểu CTĐB đã đồng bộ")
    if schedule_df.empty:
        st.info("Chưa có thời khóa biểu. Hãy đồng bộ từ Chrome Extension.")
    else:
        cols = [c for c in ("course_code", "course_name", "day_of_week", "start_time",
                            "end_time", "room", "campus") if c in schedule_df.columns]
        show = schedule_df[cols].copy()
        show["day_of_week"] = show["day_of_week"].map(
            lambda d: config.WEEKDAY_VI.get(d, d))
        show = show.rename(columns={
            "course_code": "Mã môn", "course_name": "Tên môn", "day_of_week": "Thứ",
            "start_time": "Bắt đầu", "end_time": "Kết thúc", "room": "Phòng",
            "campus": "Cơ sở",
        })
        st.dataframe(show, width="stretch", hide_index=True, height=320)

    # --- Lộ trình tóm tắt ---
    st.divider()
    st.subheader("🧭 Tóm tắt lộ trình đề xuất (chi tiết ở Tab 4)")
    if not route_activities:
        st.info("Chưa có hoạt động hợp lệ để lập lộ trình – hãy phân tích thêm bài đăng OSA ở Tab 2.")
    else:
        _done_ids = pp.completed_ids()
        for idx, act in enumerate(route_activities, start=1):
            verified = act.get("relevance_label") == config.LABEL_VERIFIED
            cls = "sdrs-route-step" if verified else "sdrs-route-step potential"
            tag = "ĐÃ XÁC MINH" if verified else "TIỀM NĂNG"
            done_mark = " · ✅ đã tham gia" if int(act.get("id") or 0) in _done_ids else ""
            # Một dòng duy nhất: Streamlit tách khối HTML ở dòng trống khiến
            # phần đóng thẻ bị escape và hiện thành chữ thô.
            st.markdown(
                f'<div class="{cls}">'
                f'<div class="ttl">{idx}. {act.get("title")}</div>'
                f'<div class="meta">⏰ {act.get("start_time")} → {act.get("end_time")} · '
                f'📍 {act.get("location") or "chưa rõ"} · '
                f'🏆 ~{_range_txt(act.get("expected_score_min"), act.get("expected_score_max"))} '
                f'({tag}) {act.get("criterion_code") or ""}{done_mark}</div></div>',
                unsafe_allow_html=True,
            )
        st.caption(
            "Điểm mỗi hoạt động là **dự đoán 3–5đ** và chỉ chính thức sau khi Phòng "
            "CTSV duyệt. Đánh dấu **Đã tham gia** ở trên để cộng dự đoán vào tiến độ."
        )

    # --- Audit log ---
    with st.expander("🧾 Nhật ký thao tác gần đây (AuditLogs)"):
        logs = database.recent_audit(25)
        if logs.empty:
            st.caption("Chưa có thao tác nào.")
        else:
            st.dataframe(logs.rename(columns={"action": "Hành động", "details": "Chi tiết",
                                              "created_at": "Thời điểm"}),
                         width="stretch", hide_index=True, height=260)
