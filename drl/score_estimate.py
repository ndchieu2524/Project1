"""Ước lượng điểm ĐRL cho một HOẠT ĐỘNG – luôn là khoảng, không phải sự thật.

Vì sao phải là khoảng
---------------------
Bài đăng của trường/Đoàn/Khoa gần như không bao giờ nói "hoạt động này được bao
nhiêu điểm rèn luyện". Điểm chỉ được chốt sau khi có danh sách điểm danh và được
Phòng CTSV/Hội đồng duyệt trên hcmus.drl.vn. Thực tế mỗi hoạt động thường được
cộng khoảng 3–5 điểm tuỳ quy mô và tiêu chí.

Hệ quả cho thiết kế
-------------------
1. KHÔNG được trình bày một con số duy nhất như thể đó là điểm chắc chắn.
2. KHÔNG được loại hoạt động khỏi lộ trình chỉ vì bài đăng không ghi điểm.
3. Khi cộng nhiều hoạt động, cộng cả hai cận → tổng cũng là một khoảng.
4. Điểm chính thức của SINH VIÊN vẫn chỉ lấy từ hcmus.drl.vn; cột điểm ở đây là
   điểm của HOẠT ĐỘNG, không phải điểm rèn luyện của sinh viên.

Cách quy đổi
------------
``expected_score`` (điểm giữa) vẫn được giữ để xếp hạng lộ trình, nhưng luôn đi
kèm ``min``/``max`` và ``source`` để giao diện nói rõ mức độ tin cậy.
"""
from __future__ import annotations

from typing import Iterable, Optional

from . import config

#: Điểm giữa mặc định khi bài đăng không nói gì.
DEFAULT_MID = (config.SCORE_ESTIMATE_MIN + config.SCORE_ESTIMATE_MAX) / 2


def estimate_for_activity(activity: dict) -> dict:
    """Trả về ``{min, max, mid, source, label}`` cho một hoạt động.

    Quy tắc:
      • Có ``expected_score_min``/``max`` trong DB (đã lưu trước đó) → dùng lại.
      • Bài đăng có nhắc điểm cụ thể (``score_estimate_source = POST_MENTION``
        hoặc ``expected_score`` có giá trị nhưng chưa có min/max) → coi đó là
        ĐIỂM GIỮA, khoảng ±1 nhưng không vượt ra ngoài [3, 5] trừ khi bài nêu rõ.
      • Không có gì → khoảng mặc định 3–5 điểm.
    """
    raw_min = _to_float(activity.get("expected_score_min"))
    raw_max = _to_float(activity.get("expected_score_max"))
    source = str(activity.get("score_estimate_source") or "").strip()

    if raw_min is not None and raw_max is not None:
        lo, hi = sorted((raw_min, raw_max))
        return {
            "min": lo,
            "max": hi,
            "mid": round((lo + hi) / 2, 2),
            "source": source or config.SCORE_ESTIMATE_SOURCE_DEFAULT,
            "label": config.SCORE_ESTIMATE_LABELS.get(
                source or config.SCORE_ESTIMATE_SOURCE_DEFAULT, "Ước lượng"),
        }

    posted = _to_float(activity.get("expected_score"))
    if posted is not None and posted > 0:
        # Bài đăng có nêu một con số → vẫn chỉ là ước lượng, cho khoảng hẹp quanh nó
        # nhưng mặc định kẹp trong 3–5 nếu con số nằm ngoài thông lệ.
        lo = max(config.SCORE_ESTIMATE_MIN, posted - 1.0) if posted <= 10 else posted
        hi = min(config.SCORE_ESTIMATE_MAX, posted + 1.0) if posted <= 10 else posted
        if lo > hi:
            lo, hi = sorted((lo, hi))
        src = source or config.SCORE_ESTIMATE_SOURCE_POST
        return {
            "min": round(lo, 2),
            "max": round(hi, 2),
            "mid": round((lo + hi) / 2, 2),
            "source": src,
            "label": config.SCORE_ESTIMATE_LABELS.get(src, "Ước lượng"),
        }

    return {
        "min": config.SCORE_ESTIMATE_MIN,
        "max": config.SCORE_ESTIMATE_MAX,
        "mid": DEFAULT_MID,
        "source": config.SCORE_ESTIMATE_SOURCE_DEFAULT,
        "label": config.SCORE_ESTIMATE_LABELS[config.SCORE_ESTIMATE_SOURCE_DEFAULT],
    }


def estimate_fields(activity: dict) -> dict:
    """Sinh đúng các cột cần ghi vào bảng ``Activities``."""
    est = estimate_for_activity(activity)
    return {
        "expected_score": est["mid"],
        "expected_score_min": est["min"],
        "expected_score_max": est["max"],
        "score_estimate_source": est["source"],
    }


def total_range(activities: Iterable[dict]) -> dict:
    """Cộng khoảng điểm của nhiều hoạt động → ``{min, max, mid, n}``.

    Khi cộng nhiều ước lượng, cộng cả hai cận (không cộng điểm giữa rồi ±).
    Đây là lý do tổng hiển thị dạng "khoảng 12–20đ", đúng bản chất dữ liệu.
    """
    lo = hi = 0.0
    n = 0
    for act in activities:
        est = estimate_for_activity(act)
        lo += est["min"]
        hi += est["max"]
        n += 1
    return {"min": round(lo, 2), "max": round(hi, 2),
            "mid": round((lo + hi) / 2, 2), "n": n}


def format_range(lo, hi, suffix: str = "đ") -> str:
    """Chuỗi hiển thị: ``3–5đ`` (dùng gạch ngang en-dash như văn bản tiếng Việt)."""
    lo_f = _to_float(lo)
    hi_f = _to_float(hi)
    if lo_f is None and hi_f is None:
        return "—"
    if lo_f is None:
        lo_f = hi_f
    if hi_f is None:
        hi_f = lo_f
    if abs(lo_f - hi_f) < 0.01:
        return f"{lo_f:g}{suffix}"
    return f"{lo_f:g}–{hi_f:g}{suffix}"


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
