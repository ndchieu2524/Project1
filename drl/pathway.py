"""Tối ưu lộ trình hoạt động bằng đồ thị NetworkX.

Bài toán: chọn chuỗi hoạt động sao cho tổng điểm ĐRL kỳ vọng lớn nhất, với ràng buộc:
    1. Không trùng bất kỳ tiết học nào trong Thời khóa biểu CTĐB.
    2. Hoạt động kế tiếp chỉ bắt đầu sau khi hoạt động trước kết thúc CỘNG thời
       gian di chuyển giữa cơ sở (NVC ↔ Linh Trung = 45 phút; cùng cơ sở/Online = 0).
    3. Trần điểm của từng tiêu chí (max_score) không bị vượt quá.

Quy trình (đúng mục 7 đề bài):
    Bước 1 – Lọc xung đột với Thời khóa biểu CTĐB.
    Bước 2 – Dựng DAG nx.DiGraph(): đỉnh = hoạt động hợp lệ, cạnh u→v nếu
             end(u) + travel(u,v) + buffer ≤ start(v).
    Bước 3 – Tìm đường đi tối ưu. Vì ràng buộc trần điểm theo tiêu chí khiến
             bài toán trở thành "Knapsack trên DAG" (không còn là đường đi dài
             nhất thuần tuý), module cài đặt CẢ HAI:
               (a) ``nx.dag_longest_path`` trên trọng số đỉnh – phương án nhanh,
                   có thể vượt trần tiêu chí;
               (b) Quy hoạch động theo thứ tự topo với state = dư địa điểm còn
                   lại của từng tiêu chí – phương án TÔN TRỌNG TRẦN 100%.
             Hàm ``compute_optimal_pathway`` dùng (b) làm kết quả chính và trả
             kèm (a) để so sánh minh bạch.
    Bước 4 – Sinh lời giải thích lộ trình (AI hoặc template nội bộ).

Lưu ý minh bạch: tính tối ưu là "tối ưu có ràng buộc" theo dữ liệu hiện có
(giờ kết thúc của một số bài có thể là giả định – được đánh dấu trong
``assumptions``/``gap_note`` của từng hoạt động).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import networkx as nx
import pandas as pd

from . import config, database, score_estimate

DATETIME_FMT = "%Y-%m-%d %H:%M"
DAY_INDEX = {day: idx for idx, day in enumerate(config.WEEKDAY_ORDER)}


# ---------------------------------------------------------------------------
# Tiện ích thời gian
# ---------------------------------------------------------------------------
def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    for fmt in (DATETIME_FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip()[:19], fmt)
        except ValueError:
            continue
    return None


def travel_minutes(campus_from: str, campus_to: str) -> int:
    """Thời gian di chuyển giữa 2 cơ sở theo cấu hình TRAVEL_MATRIX."""
    a = campus_from or "NVC"
    b = campus_to or "NVC"
    if a == b:
        return 0
    return config.TRAVEL_MATRIX.get((a, b), config.DEFAULT_TRAVEL_MINUTES)


def _weekday_key(dt: datetime) -> str:
    return config.WEEKDAY_ORDER[dt.weekday()]


def _combine(weekday: str, hhmm: str, reference: datetime) -> Optional[datetime]:
    """Ghép (thứ, giờ) của thời khóa biểu vào tuần tham chiếu của lộ trình."""
    if weekday not in DAY_INDEX or not hhmm:
        return None
    try:
        hour, minute = [int(x) for x in str(hhmm).strip().split(":")[:2]]
    except (ValueError, TypeError):
        return None
    delta_days = DAY_INDEX[weekday] - reference.weekday()
    base = reference + timedelta(days=delta_days)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Bước 1 – Lọc hoạt động theo dữ liệu & lịch học
# ---------------------------------------------------------------------------
def prepare_candidates(activities_df: pd.DataFrame,
                       schedule_df: pd.DataFrame,
                       include_labels: tuple[str, ...] = (config.LABEL_VERIFIED,
                                                          config.LABEL_POTENTIAL),
                       include_past: bool = False) -> tuple[list[dict], list[dict], list[dict]]:
    """Lọc dữ liệu ứng viên.

    Trả về (candidates, rejected_missing, conflicts) trong đó:
      - candidates: hoạt động đủ điều kiện về dữ liệu + thời gian
      - rejected_missing: bị loại do thiếu thông tin / nhãn không phù hợp
      - conflicts: bị loại do trùng giờ học chính khóa (kèm minh chứng)
    """
    now = datetime.now()
    candidates: list[dict] = []
    rejected_missing: list[dict] = []
    conflicts: list[dict] = []

    # Gom lịch học theo thứ
    schedule_by_day: dict[str, list[dict]] = {}
    for row in schedule_df.to_dict("records"):
        schedule_by_day.setdefault(str(row.get("day_of_week", "")), []).append(row)

    records = activities_df.to_dict("records")

    # Bản đồ tiêu đề → hoạt động có đủ start/end (để nhận diện bài nhắc hạn/cập nhật
    # trùng tên sự kiện gốc – không tính như một hoạt động độc lập trong đồ thị).
    from difflib import SequenceMatcher
    from .nlp_engine import normalize_event_title

    timed_by_title: dict[str, dict] = {}
    for rec in records:
        if rec.get("start_time") and rec.get("end_time"):
            key = normalize_event_title(rec.get("title") or "")
            if key:
                timed_by_title.setdefault(key, rec)

    def find_twin(title: str):
        key = normalize_event_title(title or "")
        if not key:
            return None
        if key in timed_by_title:
            return timed_by_title[key]
        best, best_ratio = None, 0.0
        for other_key, rec in timed_by_title.items():
            ratio = SequenceMatcher(None, key, other_key).ratio()
            if ratio > best_ratio:
                best, best_ratio = rec, ratio
        return best if best_ratio >= 0.72 else None

    for act in records:
        label = act.get("relevance_label")
        if label not in include_labels:
            rejected_missing.append({
                "id": act.get("id"), "title": act.get("title"),
                "reason": f"Nhãn {label} không thuộc lộ trình gợi ý "
                          f"(chỉ dùng {', '.join(include_labels)}).",
            })
            continue
        problems = []
        if int(float(act.get("is_missing_time") or 0)) == 1:
            problems.append("thiếu thời gian")
        if int(float(act.get("is_missing_location") or 0)) == 1:
            problems.append("thiếu địa điểm")
        if int(float(act.get("is_missing_content") or 0)) == 1:
            problems.append("thiếu nội dung")
        start = parse_dt(act.get("start_time"))
        end = parse_dt(act.get("end_time"))
        if start is None or end is None:
            # Cùng tiêu đề với một sự kiện khác đã có giờ → đây là bài CẬP NHẬT
            twin = find_twin(act.get("title") or "")
            if twin is not None and twin.get("id") != act.get("id"):
                rejected_missing.append({
                    "id": act.get("id"), "title": act.get("title"),
                    "reason": (f"Bài cập nhật/nhắc hạn của sự kiện gốc #{twin.get('id')} "
                               f"('{str(twin.get('title'))[:60]}…') – không phải hoạt động độc lập, "
                               "không tính trùng điểm."),
                })
                continue
            problems.append("không có đủ start/end thời gian")
        if problems:
            rejected_missing.append({
                "id": act.get("id"), "title": act.get("title"),
                "reason": "Thiếu dữ liệu: " + ", ".join(sorted(set(problems))),
            })
            continue
        if not include_past and end < now:
            rejected_missing.append({
                "id": act.get("id"), "title": act.get("title"),
                "reason": f"Hoạt động đã kết thúc ({act.get('end_time')}).",
            })
            continue

        # --- Kiểm tra trùng giờ học CTĐB theo từng ngày diễn ra của hoạt động ---
        day_key = _weekday_key(start)
        day_lessons = schedule_by_day.get(day_key, [])
        clash = None
        for lesson in day_lessons:
            lesson_start = _combine(day_key, lesson.get("start_time"), start)
            lesson_end = _combine(day_key, lesson.get("end_time"), start)
            if lesson_start is None or lesson_end is None:
                continue
            if start < lesson_end and end > lesson_start:
                clash = {
                    "id": act.get("id"), "title": act.get("title"),
                    "activity_time": f"{act.get('start_time')} → {act.get('end_time')}",
                    "lesson": f"{lesson.get('course_code')} – {lesson.get('course_name')} "
                              f"({lesson.get('day_of_week')} {lesson.get('start_time')}-{lesson.get('end_time')}, "
                              f"phòng {lesson.get('room')}, {lesson.get('campus')})",
                    "reason": "Trùng giờ học chính khóa CTĐB",
                }
                break
        if clash:
            conflicts.append(clash)
            continue

        item = dict(act)
        item["_start"] = start
        item["_end"] = end
        item["_campus"] = act.get("campus") or "NVC"
        # Điểm của hoạt động LUÔN là ước lượng (bài đăng không công bố điểm).
        # Không có điểm trong bài → vẫn lấy khoảng mặc định 3–5đ, KHÔNG loại.
        est = score_estimate.estimate_for_activity(act)
        item["_score"] = est["mid"]
        item["_score_min"] = est["min"]
        item["_score_max"] = est["max"]
        item["_score_source"] = est["source"]
        item["_verified"] = (
            act.get("relevance_label") == config.LABEL_VERIFIED
            or act.get("verification_status") in (config.VERIFY_ADMIN_APPROVED, config.VERIFY_RULE_CITED)
        )
        candidates.append(item)

    candidates.sort(key=lambda a: (a["_start"], a["_end"]))
    return candidates, rejected_missing, conflicts


# ---------------------------------------------------------------------------
# Bước 2 – Dựng đồ thị
# ---------------------------------------------------------------------------
def build_activity_graph(candidates: list[dict], buffer_minutes: int = 0,
                         travel_override: Optional[dict] = None) -> nx.DiGraph:
    """Dựng DAG có hướng: cạnh u→v nếu kịp di chuyển từ u sang v."""
    graph = nx.DiGraph()
    for act in candidates:
        graph.add_node(
            act["id"],
            title=act.get("title", ""),
            expected_score=act["_score"],
            criterion_code=act.get("criterion_code"),
            start_time=act.get("start_time"),
            end_time=act.get("end_time"),
            location=act.get("location"),
            campus=act["_campus"],
            verification_status=act.get("verification_status"),
            relevance_label=act.get("relevance_label"),
            _start=act["_start"],
            _end=act["_end"],
            _verified=act["_verified"],
        )

    for u in candidates:
        for v in candidates:
            if u["id"] == v["id"]:
                continue
            travel = (travel_override or {}).get((u["_campus"], v["_campus"]),
                        travel_minutes(u["_campus"], v["_campus"]))
            earliest_start = u["_end"] + timedelta(minutes=travel + buffer_minutes)
            if earliest_start <= v["_start"]:
                graph.add_edge(
                    u["id"], v["id"],
                    travel_minutes=travel,
                    slack_minutes=int((v["_start"] - u["_end"]).total_seconds() // 60) - travel,
                    weight=float(v["_score"]),   # trọng số theo điểm đỉnh đến
                )
    # Đảm bảo DAG (cạnh chỉ đi từ sớm → muộn; nếu dữ liệu trùng giờ tuyệt đối
    # thì bỏ cạnh 2 chiều để giữ tính không chu trình)
    for u, v in list(graph.edges()):
        if graph.has_edge(v, u) and (graph.nodes[u]["_start"], u) > (graph.nodes[v]["_start"], v):
            graph.remove_edge(v, u)
    return graph


# ---------------------------------------------------------------------------
# Bước 3a – đường đi dài nhất thuần NetworkX (không xét trần điểm)
# ---------------------------------------------------------------------------
def longest_path_by_networkx(graph: nx.DiGraph) -> list:
    if graph.number_of_nodes() == 0:
        return []
    try:
        path = nx.dag_longest_path(graph, weight="weight")
        return list(path)
    except nx.NetworkXError:
        # Đồ thị vi phạm DAG (dữ liệu bất thường) → dùng DP thủ công
        return []


# ---------------------------------------------------------------------------
# Bước 3b – QHĐ tôn trọng trần điểm từng tiêu chí
# ---------------------------------------------------------------------------
def _criteria_headroom(progress_df: pd.DataFrame,
                       criteria_df: pd.DataFrame) -> dict[str, float]:
    """Dư địa điểm còn lại của từng tiêu chí = max_score − điểm hiện có."""
    headroom: dict[str, float] = {}
    max_map = {row["code"]: float(row["max_score"] or 0) for row in criteria_df.to_dict("records")}
    if not progress_df.empty:
        for row in progress_df.to_dict("records"):
            code = row["criterion_code"]
            max_score = max_map.get(code, float(row.get("max_score") or 0))
            headroom[code] = max(0.0, max_score - float(row.get("current_score") or 0))
    for code, max_score in max_map.items():
        headroom.setdefault(code, max_score)
    return headroom


def dynamic_programming_path(candidates: list[dict], graph: nx.DiGraph,
                             headroom: dict[str, float],
                             target_remaining: float,
                             verified_bonus: float = 0.0,
                             prefer_verified: bool = True) -> dict:
    """QHĐ trên DAG: cực đại tổng điểm hợp lệ với trần điểm theo tiêu chí.

    Vì trần điểm phụ thuộc tổng điểm đã chọn theo từng tiêu chí, ta coi state
    là vector dư địa (rời rạc hoá theo bước 0.5). Với quy mô MVP (< 100 hoạt
    động, ≤ 12 tiêu chí) số state hữu hạn chấp nhận được; ngoài ra nếu vector
    quá lớn ta tự động chuyển sang beam-search rộng (giữ top-K state/đỉnh).
    """
    STEP = 0.5
    MAX_STATES_PER_NODE = 3000

    def quantize(value: float) -> int:
        return int(round(max(0.0, value) / STEP))

    nodes_topo = list(nx.topological_sort(graph))
    if not nodes_topo:
        return {"activities": [], "total_expected_score": 0.0, "mode": "dp"}

    # best[node][state_tuple] = (effective_score, path_tuple, gained_tuple)
    best: dict[int, dict[tuple, tuple[float, tuple, tuple]]] = {n: {} for n in nodes_topo}

    def value_of(node_id: int, score: float, verified: bool) -> float:
        val = score
        if prefer_verified and verified:
            val += verified_bonus
        return val

    for node in nodes_topo:
        data = graph.nodes[node]
        code = data.get("criterion_code") or "__NONE__"
        score = float(data.get("expected_score") or 0)
        if score <= 0:
            continue
        # Chỉ nhận hoạt động nếu TOÀN BỘ điểm của nó lọt vào dư địa tiêu chí.
        # (Hoạt động vượt trần sẽ bị loại thay vì chỉ tính phần dư – nhờ vậy
        #  "tổng điểm lộ trình = tổng điểm các hoạt động hiển thị" luôn khớp.)
        if score > headroom.get(code, score):
            continue
        state: dict[str, int] = {code: quantize(score)}
        gain = {code: score}
        val = value_of(node, score, bool(data.get("_verified")))

        # Kế thừa từ các cha
        for parent in graph.predecessors(node):
            for p_state, (p_val, p_path, p_gain) in best[parent].items():
                p_state_dict = dict(p_state)
                used = p_state_dict.get(code, 0) * STEP
                # KHÔNG có trần cho tiêu chí này (vd chưa nạp khung quy chế, hoặc
                # hoạt động chưa được gán mã tiêu chí) → coi như không giới hạn.
                # Trước đây hàm dùng headroom.get(code, 0) nên room = 0 và MỌI
                # hoạt động bị loại, khiến lộ trình rỗng dù có hoạt động hợp lệ.
                limit = headroom.get(code)
                if limit is not None and score > max(0.0, limit - used):
                    continue
                new_gain_dict = dict(p_gain)
                new_gain_dict[code] = new_gain_dict.get(code, 0.0) + score
                new_state = dict(p_state_dict)
                new_state[code] = quantize(used + score)
                key = tuple(sorted(new_state.items()))
                new_val = p_val + value_of(node, score, bool(data.get("_verified")))
                prev = best[node].get(key)
                if prev is None or new_val > prev[0]:
                    best[node][key] = (new_val, (*p_path, node), tuple(sorted(new_gain_dict.items())))
        existing = best[node].get(tuple(sorted(state.items())))
        if existing is None or val > existing[0]:
            best[node][tuple(sorted(state.items()))] = (val, (node,), tuple(sorted(gain.items())))

        # Giới hạn số state để tránh bùng nổ
        if len(best[node]) > MAX_STATES_PER_NODE:
            top = sorted(best[node].items(), key=lambda kv: kv[1][0], reverse=True)[:MAX_STATES_PER_NODE]
            best[node] = dict(top)

    # Chọn state tốt nhất toàn đồ thị
    best_overall = (float("-inf"), (), ())
    for node in nodes_topo:
        for _, payload in best[node].items():
            if payload[0] > best_overall[0]:
                best_overall = payload

    if not best_overall[1]:
        return {"activities": [], "total_expected_score": 0.0, "mode": "dp"}

    total = sum(v for _, v in best_overall[2])
    gains = dict(best_overall[2])
    return {
        "activities": list(best_overall[1]),
        "total_expected_score": round(total, 2),
        "effective_value": round(best_overall[0], 2),
        "gains_by_criterion": gains,
        "mode": "dp",
    }


# ---------------------------------------------------------------------------
# API chính
# ---------------------------------------------------------------------------
def _humanize_gap(minutes: int) -> str:
    """Đổi số phút thành chuỗi dễ đọc: '5 ngày 20 giờ', '2 giờ 30 phút', '45 phút'."""
    if minutes < 60:
        return f"{minutes} phút"
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if mins and not days:
        parts.append(f"{mins} phút")
    return " ".join(parts)


def compute_optimal_pathway(db_path=None,
                            student_id: Optional[str] = None,
                            semester: Optional[str] = None,
                            buffer_minutes: int = 0,
                            prefer_verified: bool = True,
                            include_past: bool = False) -> dict:
    """Chạy toàn bộ pipeline tối ưu lộ trình, trả về dict đầy đủ cho UI."""
    profile = (database.get_profile(student_id, semester, db_path) if student_id
               else database.latest_profile(db_path))
    if not profile:
        return {"error": "Chưa có hồ sơ sinh viên. Hãy đồng bộ hcmus_sync.json ở tab Tổng quan."}
    sid = profile["student_id"]
    sem = profile.get("semester") or semester or "HK1_2026_2027"

    activities_df = database.get_activities(db_path=db_path)
    schedule_df = database.get_schedule(sid, db_path)
    criteria_df = database.get_criteria(db_path)
    progress_df = database.get_criterion_progress(sid, sem, db_path)

    if activities_df.empty:
        return {"error": "Chưa có hoạt động nào trong database."}

    candidates, rejected_missing, conflicts = prepare_candidates(
        activities_df, schedule_df, include_past=include_past)

    graph = build_activity_graph(candidates, buffer_minutes=buffer_minutes)
    plain_path = longest_path_by_networkx(graph)

    headroom = _criteria_headroom(progress_df, criteria_df)
    target = float(profile.get("target_score") or 0)
    # None = chưa đồng bộ điểm → coi như 0 khi TÍNH lộ trình;
    # giao diện hiển thị "chưa đồng bộ" để không gây hiểu nhầm.
    current = float(profile.get("current_total_score") or 0)
    target_remaining = max(0.0, target - current)

    dp_result = dynamic_programming_path(
        candidates, graph, headroom, target_remaining, prefer_verified=prefer_verified)

    by_id = {c["id"]: c for c in candidates}
    chosen = [by_id[nid] for nid in dp_result["activities"] if nid in by_id]

    # Điểm tích luỹ theo tiêu chí trong lộ trình
    gains: dict[str, float] = {}
    for act in chosen:
        code = act.get("criterion_code") or "CHƯA_RÕ_TIÊU_CHÍ"
        gains[code] = gains.get(code, 0.0) + float(act["_score"])

    # Chú thích di chuyển & khoảng trống giữa các hoạt động liên tiếp trong lộ trình
    for idx, act in enumerate(chosen):
        if idx == 0:
            continue
        prev = chosen[idx - 1]
        travel = travel_minutes(prev["_campus"], act["_campus"])
        gap = int((act["_start"] - prev["_end"]).total_seconds() // 60)
        act["gap_minutes"] = gap
        act["travel_minutes"] = travel
        gap_label = _humanize_gap(gap)
        if gap >= 1440:
            act["travel_note"] = (
                f"cách hoạt động trước {gap_label} – hai hoạt động ở "
                f"{config.CAMPUS_LABELS.get(prev['_campus'], prev['_campus'])} và "
                f"{config.CAMPUS_LABELS.get(act['_campus'], act['_campus'])}"
            )
        elif travel > 0:
            act["travel_note"] = (
                f"di chuyển {travel} phút từ {config.CAMPUS_LABELS.get(prev['_campus'], prev['_campus'])} "
                f"sang {config.CAMPUS_LABELS.get(act['_campus'], act['_campus'])} "
                f"(khoảng trống {gap} phút, dư {gap - travel} phút)"
            )
        else:
            act["travel_note"] = f"cùng cơ sở/khu vực, khoảng trống {gap} phút"
        act["gap_note"] = f"trống {gap_label} sau hoạt động trước"

    plain_path_detail = []
    for nid in plain_path:
        act = by_id.get(nid)
        if act:
            plain_path_detail.append({
                "id": act["id"], "title": act.get("title"),
                "expected_score": float(act["_score"]),
                "criterion_code": act.get("criterion_code"),
                "start_time": act.get("start_time"), "end_time": act.get("end_time"),
                "verified": act["_verified"],
            })

    total_gain = round(sum(float(a["_score"]) for a in chosen), 2)
    verified_gain = round(sum(float(a["_score"]) for a in chosen if a["_verified"]), 2)
    potential_gain = round(total_gain - verified_gain, 2)
    # Tổng cũng phải là KHOẢNG: cộng cả cận dưới và cận trên của từng hoạt động.
    total_gain_min = round(sum(float(a.get("_score_min") or 0) for a in chosen), 2)
    total_gain_max = round(sum(float(a.get("_score_max") or 0) for a in chosen), 2)
    verified_gain_min = round(sum(float(a.get("_score_min") or 0)
                                  for a in chosen if a["_verified"]), 2)
    verified_gain_max = round(sum(float(a.get("_score_max") or 0)
                                  for a in chosen if a["_verified"]), 2)

    # Danh sách hoạt động "khám phá" (chưa đủ điều kiện vào lộ trình)
    discover = activities_df[activities_df["relevance_label"].isin(
        [config.LABEL_EVENT_CANDIDATE, config.LABEL_INSUFFICIENT]
    )].to_dict("records")

    route_activities = []
    for act in chosen:
        route_activities.append({
            "id": act["id"],
            "title": act.get("title"),
            "organizer": act.get("organizer"),
            "location": act.get("location"),
            "campus": act.get("campus"),
            "start_time": act.get("start_time"),
            "end_time": act.get("end_time"),
            "registration_deadline": act.get("registration_deadline"),
            "expected_score": float(act["_score"]),
            "expected_score_min": float(act.get("_score_min") or 0),
            "expected_score_max": float(act.get("_score_max") or 0),
            "score_estimate_source": act.get("_score_source"),
            "criterion_code": act.get("criterion_code"),
            "verification_status": act.get("verification_status"),
            "relevance_label": act.get("relevance_label"),
            "is_demo": int(float(act.get("is_demo") or 0)),
            "travel_note": act.get("travel_note"),
            "gap_note": act.get("gap_note"),
        })

    return {
        "student": profile,
        "semester": sem,
        "route": {
            "activities": route_activities,
            "total_expected_score": total_gain,
            "total_expected_score_min": total_gain_min,
            "total_expected_score_max": total_gain_max,
            "verified_gain": verified_gain,
            "verified_gain_min": verified_gain_min,
            "verified_gain_max": verified_gain_max,
            "potential_gain": potential_gain,
            "potential_gain_min": round(total_gain_min - verified_gain_min, 2),
            "potential_gain_max": round(total_gain_max - verified_gain_max, 2),
            "score_is_estimate": True,
            "gains_by_criterion": {k: round(v, 2) for k, v in gains.items()},
            "criterion_missing": {k: round(v, 2) for k, v in headroom.items()},
            "projected_total": round(min(100.0, current + total_gain), 2),
            "target": target,
            "current": current,
            "target_remaining": target_remaining,
            "excluded_conflicts": conflicts,
            "excluded_missing": rejected_missing,
        },
        "graph": graph,
        "candidates": candidates,
        "plain_longest_path": {
            "nodes": plain_path_detail,
            "total_expected_score": round(sum(n["expected_score"] for n in plain_path_detail), 2),
        },
        "dp": {
            "total_expected_score": dp_result.get("total_expected_score", 0.0),
            "mode": "Quy hoạch động trên DAG (tôn trọng trần điểm tiêu chí)",
        },
        "discover_activities": discover,
        "n_criteria_over_target": len(gains),
    }


# ---------------------------------------------------------------------------
# Vẽ đồ thị
# ---------------------------------------------------------------------------
def draw_graph(graph: nx.DiGraph, chosen_ids: Optional[list] = None,
               figsize: tuple = (10.5, 4.2)):
    """Vẽ DAG hoạt động, tô đậm đường đi tối ưu. Trả về matplotlib Figure.

    Bố cục: trục X = thứ tự thời gian, hoạt động cùng NGÀY xếp thành một cụm
    (lệch dọc để không chồng nhãn), có lề để không cắt chữ ở hai đầu.
    """
    import textwrap

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chosen_ids = set(chosen_ids or [])
    fig, ax = plt.subplots(figsize=figsize)
    if graph is None or graph.number_of_nodes() == 0:
        ax.text(0.5, 0.5, "Không có hoạt động hợp lệ để dựng đồ thị",
                ha="center", va="center", fontsize=12, color="#64748b")
        ax.axis("off")
        return fig

    # --- Bố cục theo ngày: mỗi ngày một cụm cột, hoạt động trong ngày lệch dọc ---
    ordered = sorted(graph.nodes, key=lambda n: (graph.nodes[n]["_start"], n))
    day_keys = []
    day_of: dict = {}
    for node in ordered:
        day = graph.nodes[node]["_start"].date()
        if day not in day_keys:
            day_keys.append(day)
        day_of[node] = day

    # Đếm trước số node mỗi ngày để canh giữa khi ngày chỉ có 1 hoạt động
    per_day: dict = {}
    for node in ordered:
        per_day.setdefault(day_of[node], []).append(node)

    counters: dict = {}
    pos: dict = {}
    for node in ordered:
        day = day_of[node]
        idx = counters.get(day, 0)
        counters[day] = idx + 1
        total = len(per_day[day])
        x = day_keys.index(day) * 2.0
        if total == 1:
            y = 0.0
        else:
            slot = (idx + 1) // 2
            y = (0.72 * slot) * (1 if idx % 2 == 0 else -1)
        pos[node] = (x, y)

    # --- Màu sắc ---
    edge_colors, edge_widths, edge_styles = [], [], []
    for u, v in graph.edges():
        if u in chosen_ids and v in chosen_ids:
            edge_colors.append("#dc2626")
            edge_widths.append(2.6)
            edge_styles.append("solid")
        else:
            edge_colors.append("#cbd5e1")
            edge_widths.append(0.9)
            edge_styles.append("dashed")

    node_colors = []
    for n in graph.nodes:
        if n in chosen_ids:
            node_colors.append("#16a34a" if graph.nodes[n].get("_verified") else "#f97316")
        elif graph.nodes[n].get("_verified"):
            node_colors.append("#bbf7d0")
        else:
            node_colors.append("#fde68a")

    labels = {}
    for n in graph.nodes:
        raw_title = str(graph.nodes[n].get("title") or "").replace("[DEMO]", "").strip()
        # Ưu tiên hiển thị TRỌN tiêu đề: thử 3 dòng rồi 4 dòng, chỉ cắt khi quá dài
        for width, max_lines in ((18, 3), (15, 4), (19, 4)):
            lines = textwrap.wrap(raw_title, width)
            if len(lines) <= max_lines:
                break
        wrapped = "\n".join(lines[:max_lines]) or "(không tên)"
        if len(lines) > max_lines:
            wrapped = wrapped.rstrip(" .,-") + "…"
        labels[n] = f"{wrapped}\n+{graph.nodes[n].get('expected_score'):g}đ"

    # --- Vẽ: node là HÌNH CHỮ NHẬT bo góc để không cắt chữ như hình tròn ---
    node_list = list(graph.nodes)
    half_w, half_h = 0.62, 0.30

    # 1) Cạnh vẽ trước (nằm dưới hộp node)
    for (u, v), color, width, style in zip(graph.edges(), edge_colors, edge_widths, edge_styles):
        nx.draw_networkx_edges(
            graph, pos, ax=ax, edgelist=[(u, v)],
            edge_color=[color], width=[width], style=[style],
            arrows=True, arrowsize=13, connectionstyle="arc3,rad=0.10",
            min_source_margin=16, min_target_margin=16, node_size=0,
        )

    # 2) Hộp node
    for idx, n in enumerate(node_list):
        x, y = pos[n]
        ax.add_patch(matplotlib.patches.FancyBboxPatch(
            (x - half_w, y - half_h), half_w * 2, half_h * 2,
            boxstyle="round,pad=0.03,rounding_size=0.16",
            facecolor=node_colors[idx], edgecolor="#1e293b", linewidth=1.1, zorder=2))

    # 3) Nhãn chữ
    for n in node_list:
        x, y = pos[n]
        ax.text(x, y, labels[n], ha="center", va="center", fontsize=6.2,
                family="DejaVu Sans", zorder=3, linespacing=1.25)

    # Ghi chú mốc ngày dưới mỗi cụm (luôn nằm dưới hộp thấp nhất của cụm)
    for day in day_keys:
        x = day_keys.index(day) * 2.0
        lowest = min(pos[n][1] for n in per_day[day]) - half_h
        ax.text(x, lowest - 0.18, day.strftime("%d/%m/%Y"), ha="center", va="top",
                fontsize=7.5, color="#475569")
    ax.set_xlim(-0.95, max(1.0, (len(day_keys) - 1) * 2.0 + 0.95))
    ax.set_ylim(min(pos[n][1] for n in pos) - 1.0, max(pos[n][1] for n in pos) + 0.8)
    ax.set_title("Đồ thị hoạt động (DAG) · cạnh đỏ = thuộc lộ trình tối ưu · "
                 "xanh lá = đã xác minh · cam = tiềm năng · vàng = ngoài lộ trình",
                 fontsize=9.5)
    ax.axis("off")
    fig.tight_layout()
    return fig
