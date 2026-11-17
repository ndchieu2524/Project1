"""Tiến độ ĐRL **DỰ ĐOÁN** – cộng dồn điểm khi sinh viên hoàn thành hoạt động.

Vì sao phải là "dự đoán"
------------------------
Điểm rèn luyện trên hcmus.drl.vn chỉ được chốt sau khi Phòng CTSV duyệt. Bài đăng
hoạt động của trường **không** công bố điểm. Vì vậy phần tiến độ trong app là
một mô hình dự đoán, không phải bản sao của trang trường:

1. Khung tiêu chí chỉ giữ **5 nhóm thật** của trang trường, mỗi nhóm có
   **điểm tối đa** (20/20/30/15/15 = 100đ).
2. Mỗi hoạt động được gán **một khoảng điểm dự đoán** (thông lệ 3–5đ).
3. Khi sinh viên bấm **"Đã tham gia"**, khoảng điểm đó được cộng dồn vào đúng
   nhóm tiêu chí của hoạt động → tiến độ cập nhật ngay.
4. Cộng dồn **không bao giờ vượt điểm tối đa** của nhóm.
5. Mọi con số hiển thị là **khoảng** ("12–20đ") và luôn có nhãn "dự đoán".

Quan hệ với điểm chính thức
---------------------------
Điểm chính thức trên hcmus.drl.vn (nếu đã quét) được giữ riêng và **không** bị
trộn vào tiến độ dự đoán: trộn hai nguồn sẽ tạo ra những bảng "0 điểm chính
thức nhưng dự đoán 20" mà không ai biết con số nào đang được cộng vào đâu.
"""
from __future__ import annotations

from typing import Iterable, Optional

from . import config, database, score_estimate

#: Nhãn dùng chung cho mọi con số do module này sinh ra.
PREDICT_BADGE = "DỰ ĐOÁN"


# ---------------------------------------------------------------------------
# Đọc dữ liệu
# ---------------------------------------------------------------------------
def _table_columns(db_path=None) -> set[str]:
    """Tên cột hiện có của bảng ``Activities`` (DB cũ có thể chưa migrate)."""
    conn = database.get_connection(db_path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(Activities)")}
    finally:
        conn.close()


def load_activities(db_path=None) -> list[dict]:
    """Toàn bộ hoạt động thật (không có dữ liệu mẫu) dưới dạng list dict."""
    df = database.get_activities(include_demo=False, db_path=db_path)
    if df.empty:
        return []
    return df.to_dict("records")


def completed_ids(db_path=None) -> set[int]:
    """ID các hoạt động đã được đánh dấu hoàn thành."""
    df = database.get_completed_activities(db_path=db_path)
    if df is None or df.empty:
        return set()
    return {int(v) for v in df["activity_id"].tolist()}


# ---------------------------------------------------------------------------
# Dựng bảng tiến độ dự đoán
# ---------------------------------------------------------------------------
def _framework(db_path=None) -> list[dict]:
    """Khung 5 nhóm + điểm tối đa. Luôn bảo đảm khung tồn tại."""
    database.ensure_rule_framework(db_path)
    df = database.get_criteria(db_path)
    if df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "criterion_code": str(r["code"]),
            "name": str(r.get("name") or r["code"]),
            "max_score": float(r.get("max_score") or 0) or None,
        })
    return rows


def _activity_range(act: dict) -> tuple[float, float]:
    est = score_estimate.estimate_for_activity(act)
    return float(est["min"]), float(est["max"])


def predict_progress(db_path=None, semester: Optional[str] = None) -> dict:
    """Tính tiến độ dự đoán từ các hoạt động đã hoàn thành.

    Trả về::

        {
          "rows": [ {criterion_code, name, max_score, pred_min, pred_max,
                     n_activities, filled} ... ],
          "totals": {"min", "max", "mid", "max_score", "n_activities"},
          "completed": [ {activity_id, title, code, min, max, start_time} ... ],
          "overflow": [ {criterion_code, name, min, max, max_score, cut_min, cut_max} ... ],
        }

    ``max_score = None`` nghĩa là khung quy chế chưa có nhóm đó → không cắt trần.
    Điểm chính thức trên trang trường **không** được trộn vào đây.
    """
    framework = _framework(db_path)
    by_code = {row["criterion_code"]: row for row in framework}
    for row in framework:
        row.update({"pred_min": 0.0, "pred_max": 0.0, "n_activities": 0, "filled": False})

    done = completed_ids(db_path)
    acts = [a for a in load_activities(db_path) if int(a.get("id") or 0) in done]

    completed_rows: list[dict] = []
    unknown_code_rows: list[dict] = []
    for act in acts:
        lo, hi = _activity_range(act)
        code = str(act.get("criterion_code") or "").strip()
        item = {
            "activity_id": int(act["id"]),
            "title": str(act.get("title") or f"Hoạt động #{act['id']}"),
            "code": code or "CHƯA_RÕ",
            "min": lo,
            "max": hi,
            "start_time": act.get("start_time"),
        }
        completed_rows.append(item)
        if code not in by_code:
            # Hoạt động chưa rõ tiêu chí VẪN được tính vào tổng (yêu cầu (k)):
            # không bao giờ loại hoạt động chỉ vì thiếu thông tin.
            unknown_code_rows.append(item)
            continue
        row = by_code[code]
        row["pred_min"] += lo
        row["pred_max"] += hi
        row["n_activities"] += 1

    # Cắt trần từng nhóm theo điểm tối đa (nếu biết).
    overflow: list[dict] = []
    for row in framework:
        cap = row["max_score"]
        if cap is not None and row["pred_min"] > cap:
            overflow.append({
                "criterion_code": row["criterion_code"],
                "name": row["name"],
                "min": round(row["pred_min"], 2),
                "max": round(row["pred_max"], 2),
                "max_score": cap,
                "cut_min": round(row["pred_min"] - cap, 2),
                "cut_max": round(max(0.0, row["pred_max"] - cap), 2),
            })
        if cap is not None:
            row["pred_min"] = min(row["pred_min"], cap)
            row["pred_max"] = min(row["pred_max"], cap)
        row["pred_min"] = round(row["pred_min"], 2)
        row["pred_max"] = round(row["pred_max"], 2)
        row["filled"] = bool(cap and cap > 0 and row["pred_min"] >= cap)

    # Hoạt động chưa rõ tiêu chí: cộng vào tổng nhưng hiện thành dòng riêng.
    for item in unknown_code_rows:
        framework.append({
            "criterion_code": item["code"],
            "name": "Hoạt động chưa rõ tiêu chí",
            "max_score": None,
            "pred_min": round(item["min"], 2),
            "pred_max": round(item["max"], 2),
            "n_activities": 1,
            "filled": False,
        })

    known = [r for r in framework if r["max_score"] is not None]
    total_min = round(sum(r["pred_min"] for r in framework), 2)
    total_max = round(sum(r["pred_max"] for r in framework), 2)
    capacity = round(sum(float(r["max_score"]) for r in known), 2) if known else None

    return {
        "rows": framework,
        "totals": {
            "min": total_min,
            "max": total_max,
            "mid": round((total_min + total_max) / 2, 2),
            "max_score": capacity,
            "n_activities": len(completed_rows),
        },
        "completed": sorted(completed_rows, key=lambda r: str(r.get("start_time") or "")),
        "overflow": overflow,
    }


def summarize(pred: dict) -> str:
    """Câu tóm tắt một dòng: ``Dự đoán 12–20đ trên tổng 100đ · 4 hoạt động``."""
    t = pred["totals"]
    txt = f"{t['min']:g}–{t['max']:g}đ" if t["max"] > t["min"] else f"{t['min']:g}đ"
    cap = f" trên tổng {t['max_score']:g}đ" if t["max_score"] else ""
    n = t["n_activities"]
    if n == 0:
        return f"Dự đoán 0đ{cap} · chưa có hoạt động nào được đánh dấu"
    return f"Dự đoán {txt}{cap} · {n} hoạt động đã hoàn thành"


def progress_dataframe(pred: dict):
    """Bảng ``Tiến độ dự đoán`` để hiển thị (đã đổi tên cột sang tiếng Việt)."""
    import pandas as pd

    rows = []
    for r in pred["rows"]:
        cap = r["max_score"]
        pred_txt = (f"{r['pred_min']:g}–{r['pred_max']:g}"
                    if abs(r["pred_max"] - r["pred_min"]) > 0.01
                    else f"{r['pred_min']:g}")
        rows.append({
            "Mã": r["criterion_code"],
            "Nhóm tiêu chí": r["name"],
            "Điểm tối đa": (f"{cap:g}" if cap else "chưa rõ"),
            "Dự đoán đạt": pred_txt,
            "Còn có thể đạt": (f"{max(0.0, cap - r['pred_max']):g}" if cap
                               else "—"),
            "Số HĐ": r["n_activities"],
        })
    return pd.DataFrame(rows)
