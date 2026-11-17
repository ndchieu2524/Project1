"""Tab Thời khóa biểu – lịch tuần kiểu Google Calendar, chỉnh sửa được.

Người dùng có thể thêm **hoạt động cá nhân** (đi làm, học thêm, việc gia đình)
để lộ trình ĐRL biết họ bận lúc nào — đây là thông tin trường không có.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from . import calendar_view, config, database
from . import ui_common as ui

STATE_KEY = "schedule_deleting"

#: Màu gợi ý cho từng loại mục
TYPE_COLORS = {"class": "blue", "personal": "amber"}
COLOR_LABELS = {
    "blue": "🔵 Xanh dương",
    "green": "🟢 Xanh lá",
    "amber": "🟠 Cam",
    "red": "🔴 Đỏ",
    "purple": "🟣 Tím",
    "slate": "⚫ Xám",
}
WEEKDAY_OPTIONS = {
    "Monday": "Thứ 2", "Tuesday": "Thứ 3", "Wednesday": "Thứ 4",
    "Thursday": "Thứ 5", "Friday": "Thứ 6", "Saturday": "Thứ 7", "Sunday": "Chủ nhật",
}


def _current_student() -> tuple[str, str]:
    """Lấy MSSV + học kỳ đang dùng, ƯU TIÊN hồ sơ trong DB.

    Trước đây hàm này lấy từ session_state nên khi Tab 1 chưa chạy trong cùng
    lượt render, MSSV rỗng → mọi việc bận bị lưu dưới khoá 'UNKNOWN' và
    KHÔNG hiện trong lịch của hồ sơ thật. Đây là lỗi đã gặp khi kiểm thử.
    """
    profile = st.session_state.get("student_profile") or {}
    student_id = str(profile.get("student_id") or "").strip()
    semester = str(profile.get("semester") or "").strip()

    if not student_id:
        try:
            saved = database.latest_profile()
            if saved:
                student_id = str(saved.get("student_id") or "").strip()
                semester = semester or str(saved.get("semester") or "").strip()
        except Exception:  # noqa: BLE001
            pass
    return student_id or "UNKNOWN", semester or "—"


def _load(student_id: str) -> pd.DataFrame:
    try:
        return database.get_schedule(student_id)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _week_nav() -> date:
    """Điều hướng tuần: trước / hôm nay / sau."""
    if "schedule_week_start" not in st.session_state:
        today = date.today()
        st.session_state["schedule_week_start"] = today - timedelta(days=today.weekday())
    c1, c2, c3, c4 = st.columns([1, 1, 4, 1])
    start: date = st.session_state["schedule_week_start"]
    with c1:
        if st.button("◀ Tuần trước", key="wk_prev", width="stretch"):
            st.session_state["schedule_week_start"] = start - timedelta(days=7)
            st.rerun()
    with c2:
        if st.button("Hôm nay", key="wk_today", width="stretch"):
            today = date.today()
            st.session_state["schedule_week_start"] = today - timedelta(days=today.weekday())
            st.rerun()
    with c3:
        end = start + timedelta(days=6)
        st.markdown(
            f"<div style='text-align:center;font-weight:650;color:#0f172a;padding-top:.35rem'>"
            f"Tuần {start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')}</div>",
            unsafe_allow_html=True,
        )
    with c4:
        if st.button("Tuần sau ▶", key="wk_next", width="stretch"):
            st.session_state["schedule_week_start"] = start + timedelta(days=7)
            st.rerun()
    return st.session_state["schedule_week_start"]


def _render_add_form(student_id: str, semester: str) -> None:
    """Form thêm hoạt động cá nhân."""
    with st.form("add_schedule", clear_on_submit=True, border=True):
        st.markdown("#### ➕ Thêm việc bận của bạn")
        st.caption(
            "Thêm những việc **trường không biết**: đi làm thêm, học thêm ngoại ngữ, "
            "sinh hoạt câu lạc bộ, việc gia đình… Lộ trình ĐRL sẽ tránh những khung giờ này."
        )
        c1, c2 = st.columns([2, 1])
        with c1:
            name = st.text_input("Tên việc *", placeholder="VD: Đi làm thêm ca tối")
        with c2:
            kind = st.selectbox(
                "Loại", ["personal", "class"],
                format_func=lambda k: database.SCHEDULE_TYPES.get(k, k),
            )

        c3, c4, c5 = st.columns(3)
        with c3:
            weekday = st.selectbox(
                "Thứ", list(WEEKDAY_OPTIONS.keys()),
                format_func=lambda k: WEEKDAY_OPTIONS[k],
            )
        with c4:
            start = st.time_input("Bắt đầu", value=datetime(2026, 1, 1, 18, 0).time())
        with c5:
            end = st.time_input("Kết thúc", value=datetime(2026, 1, 1, 21, 0).time())

        c6, c7, c8 = st.columns(3)
        with c6:
            room = st.text_input("Địa điểm (tuỳ chọn)", placeholder="VD: Quán cà phê Q.5")
        with c7:
            color = st.selectbox(
                "Màu", list(COLOR_LABELS.keys()),
                index=list(COLOR_LABELS).index(TYPE_COLORS.get("personal", "amber")),
                format_func=lambda k: COLOR_LABELS[k],
            )
        with c8:
            repeat = st.checkbox("Lặp hằng tuần", value=True)

        notes = st.text_input("Ghi chú (tuỳ chọn)", placeholder="VD: ca này không đổi được")

        submitted = st.form_submit_button("➕ Thêm vào lịch", type="primary",
                                          width="stretch")
        if submitted:
            if len(name.strip()) < 2:
                st.error("Vui lòng nhập tên việc (ít nhất 2 ký tự).")
            elif end <= start:
                st.error("Giờ kết thúc phải SAU giờ bắt đầu.")
            else:
                database.add_schedule_entry(student_id, semester, {
                    "course_name": name.strip(),
                    "course_code": "PERSONAL" if kind == "personal" else "CLASS",
                    "day_of_week": weekday,
                    "start_time": start.strftime("%H:%M"),
                    "end_time": end.strftime("%H:%M"),
                    "room": room.strip(),
                    "event_type": kind,
                    "color": color,
                    "notes": notes.strip(),
                    "repeat_until": "" if repeat else date.today().isoformat(),
                })
                st.success(f"Đã thêm **{name.strip()}** vào {WEEKDAY_OPTIONS[weekday]} "
                           f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}.")
                st.rerun()


def _render_edit_panel(student_id: str, df: pd.DataFrame) -> None:
    """Danh sách + sửa + xoá từng mục."""
    if df.empty:
        st.info("Lịch đang trống. Thêm việc bận đầu tiên ở form phía trên, "
                "hoặc đồng bộ thời khóa biểu từ Tab 📊 Tổng quan.")
        return

    st.markdown("#### ✏️ Sửa hoặc xoá một mục")
    labels = {}
    for row in df.itertuples():
        day = WEEKDAY_OPTIONS.get(str(row.day_of_week), str(row.day_of_week))
        kind_icon = "🔒" if str(getattr(row, "event_type", "class")) == "personal" else "📚"
        labels[int(row.id)] = (
            f"{kind_icon} {day} {row.start_time}–{row.end_time} · {row.course_name}"
        )

    chosen = st.selectbox(
        "Chọn mục cần sửa", list(labels.keys()),
        format_func=lambda i: labels[i], key="sched_edit_pick",
    )
    entry = database.get_schedule_entry(chosen)
    if not entry:
        return

    with st.form(f"edit_schedule_{chosen}", border=True):
        c1, c2 = st.columns([2, 1])
        with c1:
            new_name = st.text_input("Tên", value=str(entry.get("course_name") or ""))
        with c2:
            kind_keys = list(database.SCHEDULE_TYPES.keys())
            cur_kind = str(entry.get("event_type") or "class")
            new_kind = st.selectbox(
                "Loại", kind_keys,
                index=kind_keys.index(cur_kind) if cur_kind in kind_keys else 0,
                format_func=lambda k: database.SCHEDULE_TYPES.get(k, k),
                key=f"ek_{chosen}",
            )

        c3, c4, c5 = st.columns(3)
        day_keys = list(WEEKDAY_OPTIONS.keys())
        cur_day = str(entry.get("day_of_week") or "Monday")
        with c3:
            new_day = st.selectbox(
                "Thứ", day_keys,
                index=day_keys.index(cur_day) if cur_day in day_keys else 0,
                format_func=lambda k: WEEKDAY_OPTIONS[k], key=f"ed_{chosen}",
            )
        def _to_time(value, fallback):
            try:
                return datetime.strptime(str(value)[:5], "%H:%M").time()
            except (ValueError, TypeError):
                return fallback

        with c4:
            new_start = st.time_input("Bắt đầu", value=_to_time(
                entry.get("start_time"), datetime(2026, 1, 1, 18, 0).time()),
                key=f"es_{chosen}")
        with c5:
            new_end = st.time_input("Kết thúc", value=_to_time(
                entry.get("end_time"), datetime(2026, 1, 1, 21, 0).time()),
                key=f"ee_{chosen}")

        c6, c7 = st.columns(2)
        with c6:
            new_room = st.text_input("Địa điểm", value=str(entry.get("room") or ""),
                                     key=f"er_{chosen}")
        with c7:
            color_keys = list(COLOR_LABELS.keys())
            cur_color = str(entry.get("color") or "slate")
            new_color = st.selectbox(
                "Màu", color_keys,
                index=color_keys.index(cur_color) if cur_color in color_keys else 0,
                format_func=lambda k: COLOR_LABELS[k], key=f"ec_{chosen}",
            )

        new_notes = st.text_input("Ghi chú", value=str(entry.get("notes") or ""),
                                  key=f"en_{chosen}")

        b1, b2 = st.columns(2)
        with b1:
            save = st.form_submit_button("💾 Lưu thay đổi", type="primary",
                                         width="stretch")
        with b2:
            delete = st.form_submit_button("🗑️ Xoá mục này", width="stretch")

        if save:
            if new_end <= new_start:
                st.error("Giờ kết thúc phải sau giờ bắt đầu.")
            else:
                database.update_schedule_entry(chosen, {
                    "course_name": new_name.strip(),
                    "day_of_week": new_day,
                    "start_time": new_start.strftime("%H:%M"),
                    "end_time": new_end.strftime("%H:%M"),
                    "room": new_room.strip(),
                    "event_type": new_kind,
                    "color": new_color,
                    "notes": new_notes.strip(),
                })
                st.success("Đã lưu thay đổi.")
                st.rerun()
        if delete:
            database.delete_schedule_entry(chosen)
            st.warning(f"Đã xoá **{labels.get(chosen, '')}**.")
            st.rerun()


def _migrate_orphan_entries(student_id: str) -> int:
    """Chuyển các mục lỡ lưu dưới khoá 'UNKNOWN' về đúng MSSV.

    Xảy ra khi người dùng thêm việc bận trước lúc hệ thống biết MSSV của họ.
    Không chuyển thì lịch trông như "mất dữ liệu" dù dữ liệu vẫn còn trong DB.
    """
    if student_id in ("", "UNKNOWN"):
        return 0
    orphans = database.get_schedule("UNKNOWN")
    if orphans.empty:
        return 0
    moved = 0
    for row in orphans.itertuples():
        try:
            database.update_schedule_entry(int(row.id), {}, db_path=None)
            with database.transaction() as conn:
                conn.execute(
                    "UPDATE StudentSchedule SET student_id = ? WHERE id = ?",
                    (student_id, int(row.id)),
                )
            moved += 1
        except Exception:  # noqa: BLE001
            continue
    return moved


def _render_empty_hint(student_id: str, semester: str, df: pd.DataFrame) -> None:
    """Lịch trống: chỉ hướng dẫn, KHÔNG nạp tiết học mẫu."""
    if not df.empty:
        return
    ui.note_box(
        "Chưa có tiết học nào. Ứng dụng **không nạp thời khóa biểu mẫu** — lịch phải là lịch thật "
        "của bạn: mở Chrome Extension ở cổng CTĐB và bấm **Quét trang**, hoặc thêm tay bằng "
        "nút **➕ Thêm mục** (giờ học, việc bận cá nhân)."
    )


def render() -> None:
    ui.hero(
        "🗓️ Thời khóa biểu & Việc bận cá nhân",
        "Lịch tuần kiểu Google Calendar — xem giờ học, và thêm những việc bận "
        "bên ngoài (đi làm, học thêm, việc gia đình) để lộ trình ĐRL tránh đúng khung giờ.",
    )

    student_id, semester = _current_student()
    moved = _migrate_orphan_entries(student_id)
    if moved:
        st.info(f"Đã chuyển **{moved}** mục bạn thêm trước đó về đúng hồ sơ **{student_id}**.")
    df = _load(student_id)

    # --- Thống kê nhanh ---
    if not df.empty:
        n_class = int((df.get("event_type", pd.Series(dtype=str)) != "personal").sum())
        n_personal = int((df.get("event_type", pd.Series(dtype=str)) == "personal").sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("📚 Môn học / lịch trường", n_class)
        c2.metric("🔒 Việc bận tự thêm", n_personal)
        total_h = 0.0
        for row in df.itertuples():
            try:
                ts = datetime.strptime(str(row.start_time)[:5], "%H:%M")
                te = datetime.strptime(str(row.end_time)[:5], "%H:%M")
                total_h += max(0.0, (te - ts).total_seconds() / 3600)
            except (ValueError, TypeError):
                continue
        c3.metric("⏱️ Tổng giờ/tuần", f"{total_h:.1f}h")

    st.divider()
    week_start = _week_nav()

    # --- Lịch ---
    events = calendar_view.schedule_to_events(df)
    if events:
        st.markdown(
            calendar_view.build_week_grid(events, week_start=week_start),
            unsafe_allow_html=True,
        )
        st.caption("🟦 Môn học trên lớp · 🟨 Việc bận cá nhân · "
                   "Rê chuột vào khối để xem chi tiết.")
    else:
        st.info("Chưa có mục nào trên lịch — thêm ở form bên dưới để thấy lịch tuần.")

    _render_empty_hint(student_id, semester, df)

    st.divider()
    tab_add, tab_edit = st.tabs(["➕ Thêm việc bận", "✏️ Sửa / Xoá"])
    with tab_add:
        _render_add_form(student_id, semester)
    with tab_edit:
        _render_edit_panel(student_id, _load(student_id))

    st.divider()
    with st.expander("💡 Vì sao nên khai báo việc bận?"):
        st.markdown(
            "- Lộ trình ĐRL ở tab **🧭 Lộ trình tối ưu** chỉ xếp hoạt động vào những "
            "khung giờ bạn **thực sự rảnh**.\n"
            "- Nếu không khai báo, hệ thống có thể gợi ý một workshop trùng giờ đi làm "
            "của bạn.\n"
            "- Dữ liệu này **chỉ lưu trên máy bạn** trong file SQLite, không gửi đi đâu.\n"
            "- Màu **🟨 vàng** là việc bận do bạn tự thêm, **🟦 xanh** là lịch trường đồng bộ về."
        )
