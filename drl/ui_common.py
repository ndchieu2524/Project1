"""Thành phần giao diện dùng chung cho 6 tab Streamlit."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from . import config, database, nlp_engine

# ---------------------------------------------------------------------------
# CSS & thương hiệu
# ---------------------------------------------------------------------------
BRAND_CSS = """
<style>
    .main .block-container {padding-top: 1.2rem; max-width: 1280px;}
    .sdrs-hero {
        background: linear-gradient(120deg, #0b2a5b 0%, #1445a0 55%, #1f6feb 100%);
        color: white; padding: 1.15rem 1.4rem; border-radius: 14px; margin-bottom: 1rem;
        box-shadow: 0 6px 18px rgba(11,42,91,.18);
    }
    .sdrs-hero h1 {font-size: 1.42rem; margin: 0 0 .25rem 0; color: white;}
    .sdrs-hero p {margin: 0; opacity: .92; font-size: .92rem;}
    .sdrs-badge {
        display: inline-block; padding: .12rem .55rem; border-radius: 999px;
        font-size: .74rem; font-weight: 600; white-space: nowrap;
    }
    .sdrs-badge {border: 1px solid rgba(15,23,42,.08);}
    .bd-verified {background:#dcfce7; color:#166534;}
    .bd-potential {background:#fef3c7; color:#92400e;}
    .bd-candidate {background:#dbeafe; color:#1e40af;}
    .bd-insufficient {background:#fee2e2; color:#991b1b;}
    .bd-notrel {background:#e5e7eb; color:#374151;}
    /* MỌI khối nền sáng BẮT BUỘC khai báo màu chữ.
       Thiếu `color` ⇒ Streamlit theme tối sẽ tô chữ trắng trên nền nhạt → mất chữ. */
    .sdrs-card {
        border: 1px solid #e2e8f0; border-radius: 12px; padding: .85rem 1rem;
        background: #ffffff; color: #0f172a; margin-bottom: .7rem;
    }
    .sdrs-card h4 {margin: 0 0 .35rem 0; font-size: .98rem; color: #0f172a;}
    .sdrs-card p, .sdrs-card div, .sdrs-card span, .sdrs-card li {color: #1e293b;}
    .sdrs-note {
        background:#eff6ff; border-left:4px solid #1d4ed8; padding:.65rem .9rem;
        border-radius:8px; font-size:.86rem; margin:.35rem 0 .8rem 0;
        color:#1e3a8a;
    }
    .sdrs-warn {
        background:#fef2f2; border-left:4px solid #dc2626; padding:.65rem .9rem;
        border-radius:8px; font-size:.88rem; margin:.35rem 0 .8rem 0;
        color:#7f1d1d;
    }
    .sdrs-ok {
        background:#f0fdf4; border-left:4px solid #16a34a; padding:.65rem .9rem;
        border-radius:8px; font-size:.88rem; margin:.35rem 0 .8rem 0;
        color:#14532d;
    }
    .sdrs-demo-tag {
        background:#111827; color:#fde68a; font-size:.68rem; padding:.08rem .45rem;
        border-radius:6px; font-weight:700; letter-spacing:.02em;
    }
    .sdrs-route-step {
        border-left: 5px solid #16a34a; background:#f0fdf4; border-radius: 8px;
        padding: .6rem .85rem; margin-bottom: .5rem; color:#0f172a;
    }
    .sdrs-route-step.potential {border-left-color:#d97706; background:#fffbeb;}
    .sdrs-route-step .ttl {font-weight: 650; font-size: .95rem;}
    .sdrs-route-step .meta {font-size: .83rem; color:#475569; margin-top:.15rem;}
    .sdrs-route-step .ttl {color:#0f172a;}
    div[data-testid="stMetricValue"] {font-size: 1.35rem;}
    .sdrs-footer {color:#64748b; font-size:.78rem; margin-top:1.5rem;
        border-top:1px solid #e2e8f0; padding-top:.6rem;}

    /* ===================================================================
       LƯỚI AN TOÀN: kể cả khi người dùng ép theme tối (hoặc trình duyệt
       bật forced dark), mọi khối nền sáng vẫn giữ chữ đậm đọc được.
       Đây là lớp bảo vệ thứ hai sau .streamlit/config.toml.
       =================================================================== */
    .sdrs-note, .sdrs-note * {color:#1e3a8a !important;}
    .sdrs-warn, .sdrs-warn * {color:#7f1d1d !important;}
    .sdrs-ok, .sdrs-ok * {color:#14532d !important;}
    .sdrs-card, .sdrs-card * {color:#0f172a !important;}
    .sdrs-card h4 {color:#0f172a !important;}
    .sdrs-route-step, .sdrs-route-step * {color:#0f172a !important;}
    .sdrs-route-step .meta, .sdrs-route-step .meta * {color:#475569 !important;}
    /* Bảng dữ liệu: chữ đậm trên nền sáng, không phụ thuộc theme */
    div[data-testid="stDataFrame"] {background:#fff;}
    /* Nhãn badge giữ nguyên màu chữ đã khai báo */
    .sdrs-badge.bd-verified {color:#166534 !important;}
    .sdrs-badge.bd-potential {color:#92400e !important;}
    .sdrs-badge.bd-candidate {color:#1e40af !important;}
    .sdrs-badge.bd-insufficient {color:#991b1b !important;}
    .sdrs-badge.bd-notrel {color:#374151 !important;}
</style>
"""


def inject_css() -> None:
    st.markdown(BRAND_CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="sdrs-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def label_badge(label: str) -> str:
    cls = {
        config.LABEL_VERIFIED: "bd-verified",
        config.LABEL_POTENTIAL: "bd-potential",
        config.LABEL_EVENT_CANDIDATE: "bd-candidate",
        config.LABEL_INSUFFICIENT: "bd-insufficient",
        config.LABEL_NOT_RELEVANT: "bd-notrel",
    }.get(label, "bd-notrel")
    icon = config.LABEL_ICONS.get(label, "")
    return f'<span class="sdrs-badge {cls}">{icon} {label}</span>'


def demo_tag() -> str:
    return '<span class="sdrs-demo-tag">[DEMO]</span>'


def md_in_html(text: str) -> str:
    """Chuyển markdown nội tuyến sang HTML để hiển thị BÊN TRONG khối styled.

    Vì sao cần: khi dùng ``unsafe_allow_html=True``, Streamlit KHÔNG parse markdown
    bên trong thẻ HTML. Kết quả là người dùng thấy dấu sao thô ``**[DEMO]**`` thay
    vì chữ đậm — đây là lỗi thật đã gặp trên ảnh chụp giao diện.
    """
    import html as _html
    import re as _re

    escaped = _html.escape(str(text or ""), quote=False)
    escaped = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = _re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = _re.sub(r"`([^`]+?)`", r"<code>\1</code>", escaped)
    return escaped.replace("\n", "<br>")


def note_box(text: str) -> None:
    st.markdown(f'<div class="sdrs-note">{md_in_html(text)}</div>', unsafe_allow_html=True)


def warn_box(text: str) -> None:
    st.markdown(f'<div class="sdrs-warn">{md_in_html(text)}</div>', unsafe_allow_html=True)


def ok_box(text: str) -> None:
    st.markdown(f'<div class="sdrs-ok">{md_in_html(text)}</div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        f'<div class="sdrs-footer">Smart DRL Assistant HCMUS – MVP. '
        f'{md_in_html(config.DISCLAIMER)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Định dạng bảng hiển thị
# ---------------------------------------------------------------------------
def to_int(value, default: int = 0) -> int:
    """Ép int an toàn: None / NaN / '' / chuỗi lạ → default (Pandas trả NaN cho cột rỗng)."""
    try:
        if value is None:
            return default
        if isinstance(value, float) and value != value:  # NaN
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default: float = 0.0) -> float:
    """Ép float an toàn tương tự ``to_int``."""
    try:
        if value is None:
            return default
        result = float(value)
        return default if result != result else result
    except (TypeError, ValueError):
        return default


ACTIVITY_DISPLAY_COLUMNS = {
    "id": "ID",
    "title": "Hoạt động",
    "organizer": "Đơn vị tổ chức",
    "location": "Địa điểm",
    "campus": "Cơ sở",
    "start_time": "Bắt đầu",
    "end_time": "Kết thúc",
    "registration_deadline": "Hạn đăng ký",
    "expected_score": "Điểm (ước lượng)",
    "criterion_code": "Tiêu chí",
    "relevance_label": "Nhãn",
    "verification_status": "Xác minh",
    "is_missing_time": "Thiếu TG",
    "is_missing_location": "Thiếu ĐĐ",
    "is_missing_content": "Thiếu ND",
    "_done": "Đã tham gia",
}

def activities_to_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Bảng hiển thị. Điểm của hoạt động LUÔN hiện dạng khoảng (vd "3–5đ").

    Bài đăng của trường không công bố điểm chính thức; app chỉ ước lượng theo
    thông lệ 3–5đ/hoạt động, nên không được hiện một con số như thể chắc chắn.
    """
    from . import score_estimate

    out_df = df.copy()
    if "expected_score" in out_df.columns:
        ranges = []
        for _, row in out_df.iterrows():
            est = score_estimate.estimate_for_activity(row.to_dict())
            ranges.append(score_estimate.format_range(est["min"], est["max"]))
        out_df["expected_score"] = ranges
    if "_done" in out_df.columns:
        out_df["_done"] = out_df["_done"].apply(lambda v: "✅" if to_int(v) else "")
    cols = [c for c in ACTIVITY_DISPLAY_COLUMNS if c in out_df.columns]
    out = out_df[cols].copy()
    out = out.rename(columns=ACTIVITY_DISPLAY_COLUMNS)
    for col in ("Thiếu TG", "Thiếu ĐĐ", "Thiếu ND"):
        if col in out.columns:
            out[col] = out[col].apply(lambda v: "⚠" if to_int(v) == 1 else "")
    return out

def _warning_text(record: dict) -> str:
    """Cột cảnh báo dạng CHỮ — thay cho việc tô nền màu.

    Tô màu bằng pandas Styler dễ sinh ô chữ trắng trên nền hồng khi người dùng
    bật dark mode → không đọc được. Dùng emoji + chữ thì theme nào cũng rõ.
    """
    missing = []
    if to_int(record.get("is_missing_time")) == 1:
        missing.append("thời gian")
    if to_int(record.get("is_missing_location")) == 1:
        missing.append("địa điểm")
    if to_int(record.get("is_missing_content")) == 1:
        missing.append("nội dung")
    if missing:
        return "⚠️ Thiếu " + ", ".join(missing)
    return "✅ Đủ"


def style_activity_table(flag_df: pd.DataFrame, style_df: pd.DataFrame) -> pd.DataFrame:
    """Ghép dữ liệu hiển thị với cột cảnh báo dạng chữ (không dùng màu nền)."""
    out = style_df.copy()
    flags = []
    for idx in range(len(out)):
        record = flag_df.iloc[idx].to_dict() if idx < len(flag_df) else {}
        flags.append(_warning_text(record))
    out["Tình trạng"] = flags
    return out


def show_activities_table(df: pd.DataFrame, height: int = 430, key: str = "tbl") -> None:
    if df.empty:
        st.info("Không có dữ liệu phù hợp bộ lọc.")
        return
    display = activities_to_display_df(df)
    st.dataframe(
        style_activity_table(df.reset_index(drop=True), display),
        width="stretch", height=height, hide_index=True, key=key,
    )


# ---------------------------------------------------------------------------
# Đồng bộ gói JSON từ Chrome Extension
# ---------------------------------------------------------------------------
REQUIRED_SYNC_KEYS = ["sync_source", "student_profile", "drl_progress", "timetable"]


def _to_float_or_none(value):
    """Đổi sang float; None/chuỗi rỗng/không hợp lệ → None (KHÁC với 0)."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_sync_payload(payload: dict) -> tuple[bool, list[str]]:
    """Kiểm tra cấu trúc gói JSON Schema 2 trước khi ghi vào DB."""
    errors: list[str] = []
    for key in REQUIRED_SYNC_KEYS:
        if key not in payload:
            errors.append(f"Thiếu khoá bắt buộc: '{key}'")
    profile = payload.get("student_profile") or {}
    if not str(profile.get("student_id") or "").strip():
        errors.append("student_profile.student_id không được rỗng")
    if not str(profile.get("semester") or "").strip():
        errors.append("student_profile.semester không được rỗng")
    try:
        float(profile.get("current_total_score") or 0)
    except (TypeError, ValueError):
        errors.append("student_profile.current_total_score phải là số")
    for idx, row in enumerate(payload.get("drl_progress") or []):
        if not row.get("criterion_code"):
            errors.append(f"drl_progress[{idx}] thiếu criterion_code")
    for idx, row in enumerate(payload.get("timetable") or []):
        for key in ("course_code", "day_of_week", "start_time", "end_time"):
            if not row.get(key):
                errors.append(f"timetable[{idx}] thiếu '{key}'")
    return (len(errors) == 0), errors


def apply_sync_payload(payload: dict, db_path=None) -> dict:
    """Ghi gói đồng bộ vào SQLite: tiêu chí → hồ sơ → tiến độ → thời khóa biểu."""
    profile_in = payload["student_profile"]
    student_id = str(profile_in["student_id"]).strip()
    semester = str(profile_in["semester"]).strip()
    is_demo = bool(payload.get("is_demo"))
    progress_rows = payload.get("drl_progress") or []

    # 1. Cập nhật danh mục tiêu chí (nếu gói mang theo tên/max_score)
    #
    # LỖI TỪNG GẶP: extension gửi max_score = null khi trang ĐRL không hiển thị
    # điểm tối đa (rất hay xảy ra). Code cũ lấy `or 0` → mọi max_score thành 0 →
    # biểu đồ tiến độ có "Còn thiếu = max − current" = 0 hết, cột nào cũng đầy
    # 100%, nhìn như thể sinh viên đã đạt điểm tối đa ở mọi tiêu chí.
    #
    # Cách xử lý đúng: ưu tiên max_score trong gói → nếu trống thì lấy từ KHUNG
    # QUY CHẾ đã có trong DB → nếu vẫn không có thì để None (không bịa ra 0).
    # Nếu gói không kèm điểm tối đa mà danh mục cũng trống → nạp khung quy chế,
    # để "còn thiếu bao nhiêu điểm" vẫn tính được thay vì hiện 0 khắp nơi.
    # Khung quy chế 5 nhóm là NGUỒN CHUẨN cho tên nhóm và điểm tối đa. Danh mục
    # phải tồn tại TRƯỚC khi ghi tiến độ, nếu không mỗi dòng quét về sẽ tự tạo
    # một tiêu chí rác với tên lấy từ bài quét (hoặc "x") và trần 0.
    database.ensure_rule_framework(db_path)

    missing_max: list[str] = []
    for row in progress_rows:
        code = row.get("criterion_code")
        if not code:
            continue
        catalog = database.get_criteria_dict(db_path)
        existing = catalog.get(code)
        incoming_max = _to_float_or_none(row.get("max_score"))
        existing_max = _to_float_or_none((existing or {}).get("max_score"))
        max_score = incoming_max if incoming_max is not None else existing_max
        # Tên: khung quy chế thắng vì đó là văn bản chính thức của trường. Chỉ
        # dùng tên trong gói khi tiêu chí này KHÔNG có trong khung.
        framework_name = str((existing or {}).get("name") or "").strip()
        packet_name = str(row.get("name") or "").strip()
        name = framework_name or packet_name or code
        if max_score is None:
            missing_max.append(code)
        database.upsert_criterion({
            "code": code,
            "name": name,
            "category": (existing or {}).get("category", ""),
            "max_score": max_score if max_score is not None else 0.0,
            "mandatory": bool(row.get("mandatory", (existing or {}).get("mandatory", 0))),
            "evidence_required": (existing or {}).get("evidence_required", ""),
            "rule_reference": (existing or {}).get("rule_reference", ""),
            "is_demo": (existing or {}).get("is_demo", int(is_demo)),
        }, db_path)

    # 2. Hồ sơ sinh viên (giữ nguyên target_score cũ nếu có)
    old_profile = database.get_profile(student_id, semester, db_path)
    target = float(old_profile.get("target_score") or 0) or 90.0

    # Phân biệt 2 trường hợp khác nhau (đây từng là lỗi):
    #   (a) gói KHÔNG CÓ trường điểm      → giữ điểm cũ (gói chỉ chứa TKB)
    #   (b) gói CÓ trường điểm = 0        → ĐIỂM THẬT LÀ 0, phải ghi 0
    # Trước đây code lấy `bool(old_score)` nên trường hợp (b) vẫn giữ điểm cũ:
    # người dùng nhập JSON 0 điểm mà màn hình vẫn hiện 61 điểm của dữ liệu DEMO.
    raw_total = profile_in.get("current_total_score")
    has_score = raw_total is not None and str(raw_total).strip() != ""
    new_total = None
    if has_score:
        try:
            new_total = float(raw_total)
        except (TypeError, ValueError):
            new_total = None
    kept_old_score = False
    if new_total is None:
        # (a) không có trường điểm → giữ nguyên giá trị cũ, KHÔNG bịa ra 0.
        #     None nghĩa là "chưa từng đồng bộ điểm" → giữ None, không phải 0.0
        #     (0.0 sẽ hiện "Điểm hiện tại đã có: 0" — đúng lỗi người dùng báo).
        old_raw = old_profile.get("current_total_score")
        if old_raw is not None and str(old_raw).strip() != "":
            new_total = float(old_raw)
            kept_old_score = True
        else:
            new_total = None

    incoming_score_type = profile_in.get("score_type") or ""
    if new_total and not kept_old_score and incoming_score_type:
        score_type = incoming_score_type
    else:
        score_type = old_profile.get("score_type") or config.SCORE_TYPE_OFFICIAL

    database.upsert_profile({
        "student_id": student_id,
        "full_name": profile_in.get("full_name") or old_profile.get("full_name", ""),
        "faculty": profile_in.get("faculty") or old_profile.get("faculty", ""),
        "semester": semester,
        "current_total_score": new_total,
        "score_type": score_type,
        "target_score": target,
        # Phải là "có bảng tiêu chí thật sự hay không", KHÔNG phải "đã từng có".
        # Nếu để `or old_...` thì sau khi xoá bảng, cờ vẫn = 1 và giao diện
        # tưởng còn dữ liệu chi tiết.
        "has_detailed_criteria": bool(progress_rows),
    }, db_path)

    # 3. Tiến độ từng tiêu chí.
    #    Ba trường hợp, phải xử lý KHÁC nhau:
    #      • có bảng tiêu chí   → thay toàn bộ
    #      • không có + KHÔNG có điểm → giữ nguyên (gói chỉ chứa TKB)
    #      • không có + CÓ điểm mới   → XOÁ bảng cũ, vì bảng cũ mâu thuẫn với
    #        tổng điểm mới (tổng 0 mà tiêu chí vẫn hiện 18, 10…)
    cleared_progress = False
    if progress_rows:
        # Chặn trạng thái TỰ MÂU THUẪN duy nhất: gói khai TỔNG = 0 mà bảng tiêu chí
        # lại có điểm. Khi đó bảng vô nghĩa (0 điểm thì mọi tiêu chí phải 0) → bỏ bảng.
        #
        # KHÔNG tính lại tổng điểm từ bảng: gói quét có thể chỉ liệt kê MỘT PHẦN
        # tiêu chí (tổng 61 mà bảng chỉ có dòng 18 điểm). Lấy bảng làm nguồn sẽ
        # làm điểm thật của sinh viên bị tụt — đó là lỗi, không phải cách sửa.
        # Lệch kiểu "thiếu dòng" chỉ cần hiển thị ghi chú ở dashboard.
        rows_sum = 0.0
        for row in progress_rows:
            try:
                rows_sum += float(row.get("current_score") or 0)
            except (TypeError, ValueError):
                pass
        if (has_score and not kept_old_score and new_total is not None
                and float(new_total) < 0.5 and rows_sum > 0.5):
            database.clear_criterion_progress(student_id, semester, db_path)
            n_progress = 0
            cleared_progress = True
        else:
            database.replace_criterion_progress(student_id, semester, progress_rows, db_path)
            n_progress = len(progress_rows)
    elif has_score and not kept_old_score:
        database.clear_criterion_progress(student_id, semester, db_path)
        n_progress = 0
        cleared_progress = True
    else:
        # Không có bảng tiêu chí mới → KHÔNG giữ bảng cũ nếu nó cộng lại khác
        # tổng điểm đang có (bảng cũ mâu thuẫn thì phải bỏ, không hiển thị sai).
        existing_rows = database.get_criterion_progress(student_id, semester, db_path)
        if existing_rows is not None and len(existing_rows):
            try:
                old_sum = float(pd.to_numeric(existing_rows["current_score"],
                                              errors="coerce").fillna(0).sum())
            except Exception:  # noqa: BLE001
                old_sum = 0.0
            if (float(new_total or 0) > 0.5
                    and abs(old_sum - float(new_total or 0)) >= 0.5 and not kept_old_score):
                database.clear_criterion_progress(student_id, semester, db_path)
                cleared_progress = True
                existing_rows = existing_rows.iloc[0:0]
        n_progress = len(existing_rows) if existing_rows is not None else 0

    # 4. Thời khóa biểu
    timetable_rows = [dict(r) for r in (payload.get("timetable") or [])]
    if timetable_rows:
        database.replace_schedule(student_id, semester, timetable_rows,
                                  synced_from=payload.get("sync_source", config.SYNC_SOURCE_TAG),
                                  is_demo=is_demo, db_path=db_path)

    database.log_action("SYNC_FROM_EXTENSION", {
        "student_id": student_id,
        "semester": semester,
        "sync_source": payload.get("sync_source"),
        "synced_at": payload.get("synced_at"),
        "n_progress": len(progress_rows),
        "n_timetable": len(timetable_rows),
        "kept_previous_score": kept_old_score,
        "is_demo": is_demo,
    }, db_path)
    return {
        "student_id": student_id,
        "semester": semester,
        "n_progress": n_progress,
        "n_timetable": len(timetable_rows),
        "kept_previous_score": kept_old_score,
        "kept_previous_progress": (not bool(progress_rows)) and not cleared_progress,
        "cleared_previous_progress": cleared_progress,
    }


def parse_sync_json_text(text: str) -> tuple[Optional[dict], list[str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"JSON không hợp lệ: {exc}"]
    if not isinstance(payload, dict):
        return None, ["Nội dung JSON phải là một object {...}"]
    ok, errors = validate_sync_payload(payload)
    return (payload if ok else None), errors


# ---------------------------------------------------------------------------
# Hiển thị & tải file
# ---------------------------------------------------------------------------
def download_json_button(data: dict | list, filename: str, label: str, key: str) -> None:
    st.download_button(
        label,
        data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=filename,
        mime="application/json",
        key=key,
    )


def download_csv_button(df: pd.DataFrame, filename: str, label: str, key: str) -> None:
    st.download_button(
        label,
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def parse_dt(value: Optional[str]):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def fmt_deadline_note(value: Optional[str]) -> str:
    dt = parse_dt(value)
    if not dt:
        return ""
    delta = (dt - datetime.now()).days
    if delta < 0:
        return "⛔ Hạn đã qua"
    if delta == 0:
        return "⏰ Hạn hôm nay"
    return f"⏳ còn {delta} ngày"


def profile_summary_oneliner(profile: dict) -> str:
    if not profile:
        return "Chưa có hồ sơ sinh viên."
    raw_score = profile.get("current_total_score")
    if raw_score is None or str(raw_score).strip() == "":
        score_txt = "**chưa đồng bộ điểm** (gói JSON không kèm tổng điểm ĐRL)"
    else:
        score_txt = f"Điểm hiện tại **{float(raw_score):g}**"
    return (
        f"MSSV **{profile.get('student_id')}** · {profile.get('semester')} · "
        f"{score_txt}/mục tiêu **{float(profile.get('target_score') or 0):g}** · "
        f"Nguồn: {config.SCORE_TYPE_LABELS.get(profile.get('score_type'), profile.get('score_type'))}"
    )


def ensure_database_ready() -> None:
    """Gọi 1 lần khi khởi động: tạo schema + DỌN SẠCH dữ liệu mẫu còn sót.

    Không còn công tắc nào bật lại được: bản này không sinh hoạt động, hồ sơ hay
    thời khóa biểu mẫu trong bất kỳ trường hợp nào (kể cả khi DB trống).

    Đồng thời dọn dữ liệu mẫu của **bản cũ** — người dùng nâng cấp tại chỗ vẫn
    còn ``[DEMO] Nguyễn Văn A``, 11 hoạt động mẫu và bảng tiến độ 61 điểm trong
    DB. Không dọn thì màn hình vẫn trộn dữ liệu giả với dữ liệu thật.
    """
    database.init_db()
    try:
        removed = database.purge_all_demo_data()
    except Exception:  # noqa: BLE001
        return
    total = sum(int(v or 0) for v in removed.values())
    if total:
        st.session_state["demo_purged_on_start"] = removed


def ai_settings_from_session() -> tuple[str, str, str]:
    return (
        st.session_state.get("ai_provider", "LOCAL"),
        st.session_state.get("ai_key", ""),
        st.session_state.get("ai_model", ""),
    )


def criteria_records() -> list[dict]:
    return database.get_criteria().fillna("").to_dict("records")
