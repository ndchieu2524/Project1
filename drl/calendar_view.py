"""Dựng lịch tuần dạng Google Calendar bằng HTML thuần.

Vì sao tự sinh HTML thay vì dùng thư viện JS:
  - Ứng dụng chạy Streamlit, không có bundler cho React component.
  - Thư viện lịch từ CDN sẽ **không tải được** khi mở offline hoặc trong iframe
    không có mạng, lịch sẽ trắng trơn.
  - HTML/CSS thuần thì luôn hiển thị, không phụ thuộc mạng.

Toạ độ: mỗi ngày là 1 cột; mỗi mục là 1 khối đặt tuyệt đối theo giờ.
Các mục **trùng giờ** được chia đôi bề ngang để không che nhau.
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

#: Lịch hiển thị từ 6:00 đến 22:00 (đủ cho lịch học + đi làm + sinh hoạt)
DAY_START_HOUR = 6
DAY_END_HOUR = 22
#: Chiều cao 1 giờ (px) — tổng chiều cao = (22-6)*56 = 896px
HOUR_HEIGHT = 56

WEEKDAYS_VI = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"]
#: Ánh xạ nhiều cách ghi thứ → chỉ số 0..6 (0 = Thứ 2)
WEEKDAY_INDEX = {
    "monday": 0, "mon": 0, "thứ 2": 0, "thu 2": 0, "t2": 0, "2": 0,
    "tuesday": 1, "tue": 1, "thứ 3": 1, "thu 3": 1, "t3": 1, "3": 1,
    "wednesday": 2, "wed": 2, "thứ 4": 2, "thu 4": 2, "t4": 2, "4": 2,
    "thursday": 3, "thu": 3, "thứ 5": 3, "thu 5": 3, "t5": 3, "5": 3,
    "friday": 4, "fri": 4, "thứ 6": 4, "thu 6": 4, "t6": 4, "6": 4,
    "saturday": 5, "sat": 5, "thứ 7": 5, "thu 7": 5, "t7": 5, "7": 5,
    "sunday": 6, "sun": 6, "chủ nhật": 6, "chu nhat": 6, "cn": 6, "8": 6,
}


def weekday_index(value) -> Optional[int]:
    """Chuyển 'Monday' / 'Thứ 2' / 'T2' → 0..6. Không nhận ra → None."""
    key = str(value or "").strip().lower()
    return WEEKDAY_INDEX.get(key)


def _parse_hm(value: str) -> Optional[int]:
    """'18:30' → 1110 (phút tính từ 0:00)."""
    text = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S", "%Hh%M"):
        try:
            t = datetime.strptime(text, fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return None


def _escape(text) -> str:
    return html.escape(str(text or ""), quote=True)


def build_week_grid(events: Iterable[dict], week_start: Optional[date] = None,
                    show_weekend: bool = True) -> str:
    """Sinh HTML lịch tuần.

    ``events``: mỗi dict có ``title``, ``day_of_week`` (hoặc ``event_date``),
    ``start_time``, ``end_time``, ``color``, ``subtitle``, ``kind``.
    """
    week_start = week_start or (date.today() - timedelta(days=date.today().weekday()))
    n_days = 7 if show_weekend else 5
    total_hours = DAY_END_HOUR - DAY_START_HOUR
    grid_h = total_hours * HOUR_HEIGHT

    # --- Phân loại sự kiện vào từng cột ngày ---
    by_day: dict[int, list[dict]] = {i: [] for i in range(n_days)}
    overflow: list[str] = []
    for ev in events:
        idx = weekday_index(ev.get("day_of_week"))
        # Hoạt động có ngày cụ thể: chỉ hiện nếu nằm trong tuần đang xem
        ev_date = str(ev.get("event_date") or "").strip()
        if ev_date:
            try:
                d = datetime.strptime(ev_date[:10], "%Y-%m-%d").date()
            except ValueError:
                d = None
            if d is not None:
                idx = (d - week_start).days
                if idx < 0 or idx >= n_days:
                    continue
        if idx is None or idx >= n_days:
            continue
        start = _parse_hm(ev.get("start_time"))
        end = _parse_hm(ev.get("end_time"))
        if start is None:
            continue
        if end is None or end <= start:
            end = start + 60
        # Cắt phần ngoài khung giờ hiển thị
        top_min = max(start, DAY_START_HOUR * 60)
        bot_min = min(end, DAY_END_HOUR * 60)
        if bot_min <= top_min:
            overflow.append(str(ev.get("title") or ""))
            continue
        by_day[idx].append({
            **ev,
            "_start": top_min,
            "_end": bot_min,
            "_title": str(ev.get("title") or ev.get("course_name") or "—"),
            "_subtitle": str(ev.get("subtitle") or ev.get("room") or ""),
            "_color": ev.get("color") or "#475569",
        })

    # --- Tính cột cho các mục trùng giờ (thuật toán xếp lịch đơn giản) ---
    for idx in by_day:
        items = sorted(by_day[idx], key=lambda e: (e["_start"], e["_end"]))
        clusters: list[list[dict]] = []
        for item in items:
            placed = False
            for cluster in clusters:
                if any(item["_start"] < other["_end"] and other["_start"] < item["_end"]
                       for other in cluster):
                    cluster.append(item)
                    placed = True
                    break
            if not placed:
                clusters.append([item])
        for cluster in clusters:
            width = 100.0 / len(cluster)
            for pos, item in enumerate(cluster):
                item["_left"] = pos * width
                item["_width"] = width

    # --- Header: thứ + ngày trong tuần ---
    head_cells = ['<div class="cal-gutter"></div>']
    for i in range(n_days):
        d = week_start + timedelta(days=i)
        is_today = d == date.today()
        head_cells.append(
            f'<div class="cal-head{" cal-today" if is_today else ""}">'
            f'<span class="cal-dow">{WEEKDAYS_VI[i]}</span>'
            f'<span class="cal-date">{d.day:02d}/{d.month:02d}</span></div>'
        )

    # --- Cột giờ bên trái ---
    gutter = ['<div class="cal-gutter cal-times">']
    for hour in range(DAY_START_HOUR, DAY_END_HOUR):
        gutter.append(f'<div class="cal-hour"><span>{hour:02d}:00</span></div>')
    gutter.append("</div>")

    # --- Lưới giờ + sự kiện ---
    cols = []
    for i in range(n_days):
        cells = []
        for hour in range(DAY_START_HOUR, DAY_END_HOUR):
            cells.append('<div class="cal-cell"></div>')
        blocks = []
        for item in by_day[i]:
            top = (item["_start"] - DAY_START_HOUR * 60) / 60 * HOUR_HEIGHT
            height = max(22, (item["_end"] - item["_start"]) / 60 * HOUR_HEIGHT - 2)
            start_txt = f"{item['_start'] // 60:02d}:{item['_start'] % 60:02d}"
            end_txt = f"{item['_end'] // 60:02d}:{item['_end'] % 60:02d}"
            kind_class = " cal-personal" if item.get("kind") == "personal" else " cal-class"
            tooltip = f"{item['_title']} · {start_txt}–{end_txt}"
            if item["_subtitle"]:
                tooltip += f" · {item['_subtitle']}"
            blocks.append(
                f'<div class="cal-event{kind_class}" style="top:{top:.1f}px;'
                f'height:{height:.1f}px;left:{item.get("_left", 0):.1f}%;'
                f'width:calc({item.get("_width", 100):.1f}% - 3px);'
                f'border-left-color:{_escape(item["_color"])}" '
                f'title="{_escape(tooltip)}">'
                f'<b>{_escape(item["_title"])}</b>'
                f'<i>{start_txt}–{end_txt}</i>'
                + (f'<i class="cal-room">{_escape(item["_subtitle"])}</i>'
                   if item["_subtitle"] else "")
                + "</div>"
            )
        cols.append(
            f'<div class="cal-col">{"".join(cells)}{"".join(blocks)}</div>'
        )

    css = _CALENDAR_CSS.replace("__GRID_H__", str(grid_h)).replace("__N__", str(n_days))
    return f"""<style>{css}</style>
<div class="cal-wrap">
  <div class="cal-headrow">{''.join(head_cells)}</div>
  <div class="cal-body">
    {''.join(gutter)}
    <div class="cal-grid">{''.join(cols)}</div>
  </div>
</div>"""


_CALENDAR_CSS = """
.cal-wrap {font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  border:1px solid #e2e8f0; border-radius:12px; overflow:hidden; background:#fff;}
.cal-headrow {display:grid; grid-template-columns: 62px repeat(__N__, 1fr);
  border-bottom:1px solid #e2e8f0; background:#f8fafc;}
.cal-head {padding:.45rem .3rem; text-align:center; color:#334155;
  border-left:1px solid #eef2f7;}
.cal-head .cal-dow {display:block; font-size:.74rem; font-weight:600; color:#64748b;
  text-transform:uppercase; letter-spacing:.03em;}
.cal-head .cal-date {display:block; font-size:.98rem; font-weight:700; color:#0f172a;}
.cal-head.cal-today {background:#e0edff;}
.cal-head.cal-today .cal-date {color:#1f6feb;}
.cal-body {display:grid; grid-template-columns: 62px 1fr;}
.cal-gutter.cal-times {border-right:1px solid #e2e8f0; background:#fcfdff;}
.cal-hour {height:__HOUR_H__px; position:relative;}
.cal-hour span {position:absolute; top:-8px; right:6px; font-size:.7rem; color:#94a3b8;}
.cal-grid {display:grid; grid-template-columns: repeat(__N__, 1fr); position:relative;
  height:__GRID_H__px; background-image: repeating-linear-gradient(
    to bottom, #eef2f7 0, #eef2f7 1px, transparent 1px, transparent __HOUR_H__px);}
.cal-col {position:relative; border-left:1px solid #eef2f7;}
.cal-col:first-child {border-left:none;}
.cal-cell {height:__HOUR_H__px;}
.cal-event {position:absolute; border-radius:6px; padding:2px 4px 2px 6px;
  overflow:hidden; cursor:default; border-left:3px solid; font-size:.72rem;
  line-height:1.25; box-shadow:0 1px 2px rgba(15,23,42,.08);}
/* Nền nhạt + CHỮ ĐẬM tường minh: không bao giờ bị chữ trắng trên nền sáng */
.cal-event.cal-class {background:#dbeafe; color:#12306b;}
.cal-event.cal-personal {background:#fef3c7; color:#6b4a04;}
.cal-event b {display:block; font-weight:700; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis;}
.cal-event i {display:block; font-style:normal; font-size:.68rem; opacity:.85;}
.cal-event .cal-room {white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
"""
_CALENDAR_CSS = _CALENDAR_CSS.replace("__HOUR_H__", str(HOUR_HEIGHT))


def schedule_to_events(df) -> list[dict]:
    """Chuyển DataFrame thời khóa biểu → danh sách sự kiện cho lịch."""
    if df is None or len(df) == 0:
        return []
    events = []
    for _, row in df.iterrows():
        is_personal = str(row.get("event_type") or "class") == "personal"
        events.append({
            "title": row.get("course_name") or row.get("course_code") or "—",
            "subtitle": " · ".join(
                p for p in (row.get("room"), row.get("notes")) if p and str(p) != "nan"
            ),
            "day_of_week": row.get("day_of_week"),
            "event_date": row.get("event_date"),
            "start_time": row.get("start_time"),
            "end_time": row.get("end_time"),
            "color": SCHEDULE_COLOR_FALLBACK.get(str(row.get("color") or ""), "#475569"),
            "kind": "personal" if is_personal else "class",
            "id": row.get("id"),
        })
    return events


SCHEDULE_COLOR_FALLBACK = {
    "blue": "#1f6feb", "green": "#16a34a", "amber": "#d97706",
    "red": "#dc2626", "purple": "#7c3aed", "slate": "#475569",
}
