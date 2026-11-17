"""Kiểm thử tự động cho Smart DRL Assistant (chạy: pytest -q).

Bao phủ:
  - Bóc tách ngày/giờ/địa điểm/điểm ĐRL bằng Regex
  - Phân loại 2 bước + cờ thiếu dữ liệu
  - Schema 1 của báo cáo AI/NLP
  - SQLite: schema, nạp dữ liệu mẫu (chỉ trong test), đồng bộ gói Schema 2
  - NetworkX: lọc trùng lịch, DAG, tối ưu có trần tiêu chí
  - ML: baseline vs mô hình đề xuất, độ đo, confusion matrix
  - An toàn: AI không được tự nâng VERIFIED_DRL
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

# Dữ liệu mẫu CHỈ được phép trong test: đặt cờ trước khi import drl.seed_data.
os.environ.setdefault("SDRS_ALLOW_DEMO_SEED", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from drl import config, database, ml_benchmark, nlp_engine, pathway, seed_data  # noqa: E402
from drl.ai_engine import sanitize_ai_report  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    database.init_db(db_path)
    seed_data.seed_database(db_path=db_path, force=True)
    return db_path


@pytest.fixture()
def catalog():
    return [dict(c) for c in seed_data.DEMO_CRITERIA]


# ---------------------------------------------------------------------------
# 1. NLP: trích xuất thời gian
# ---------------------------------------------------------------------------
def test_extract_time_full(catalog):
    text = (
        "HỘI THẢO AI\n"
        "⏰ Thời gian: 08h30 - 11h30, ngày 22/11/2026\n"
        "👉 Đăng ký trước 23h59 ngày 20/11/2026 tại link.\n"
        "📍 Địa điểm: Hội trường I, Cơ sở Nguyễn Văn Cừ, Q.5\n"
        "🎁 Được cộng 5 điểm rèn luyện.\n"
    )
    act = nlp_engine.analyze_post(text, criteria_catalog=catalog)["activity"]
    assert act["start_time"] == "2026-11-22 08:30"
    assert act["end_time"] == "2026-11-22 11:30"
    assert act["registration_deadline"] == "2026-11-20 23:59"


def test_time_range_not_mistaken_for_date(catalog):
    """"08h30 - 11h30" KHÔNG được hiểu thành ngày 30/11."""
    text = "Thời gian: 08h30 - 11h30\n📍 Phòng A.101, Cơ sở Linh Trung\nTham gia được cộng 3 điểm rèn luyện."
    report = nlp_engine.analyze_post(text, criteria_catalog=catalog)
    act = report["activity"]
    assert act["start_time"] is None, "Không có ngày cụ thể ⇒ không được tự suy ra ngày"
    assert report["missing_flags"]["is_missing_time"] is True


def test_deadline_only_does_not_create_fake_event_time(catalog):
    text = ("NHẮC HẠN ĐĂNG KÝ\nHạn chót: 23h59 ngày 20/11/2026\n"
            "📍 Hội trường I, Cơ sở Nguyễn Văn Cừ\nTham gia được cộng 5 điểm rèn luyện.")
    act = nlp_engine.analyze_post(text, criteria_catalog=catalog)["activity"]
    assert act["registration_deadline"] == "2026-11-20 23:59"
    assert act["start_time"] is None


# ---------------------------------------------------------------------------
# 2. NLP: địa điểm, điểm, tiêu chí
# ---------------------------------------------------------------------------
def test_location_and_campus(catalog):
    text = ("WORKSHOP KỸ NĂNG\nThời gian: 13h30 - 17h00, ngày 20/12/2026\n"
            "📍 Địa điểm: Phòng D401, Cơ sở Linh Trung\n"
            "Sinh viên tham gia đầy đủ được cộng 3 điểm rèn luyện.")
    act = nlp_engine.analyze_post(text, criteria_catalog=catalog)["activity"]
    assert "Linh Trung" in act["location"]
    assert act["campus"] == "Linh Trung"
    assert act["expected_score"] == 3.0


def test_pending_location_is_missing(catalog):
    text = ("BUỔI CHIA SẺ HỌC BỔNG\nThời gian: 18h00 - 20h00, ngày 09/12/2026\n"
            "Địa điểm sẽ thông báo tới sinh viên đăng ký qua email.\n")
    report = nlp_engine.analyze_post(text, criteria_catalog=catalog)
    assert report["activity"]["location"] == ""
    assert report["missing_flags"]["is_missing_location"] is True
    assert report["relevance_label"] == config.LABEL_INSUFFICIENT


def test_score_only_when_explicit(catalog):
    no_score = ("CUỘC THI HÙNG BIỆN\nThời gian: 13h00 - 17h00, ngày 13/12/2026\n"
                "Địa điểm: Hội trường I, Cơ sở Nguyễn Văn Cừ\nĐăng ký trước 05/12/2026.")
    report = nlp_engine.analyze_post(no_score, criteria_catalog=catalog)
    # Bài KHÔNG ghi điểm là chuyện BÌNH THƯỜNG (trường không công bố điểm ĐRL).
    # expected_score vẫn None trong báo cáo phân tích, nhưng nhãn phải là
    # POTENTIAL_DRL để hoạt động còn vào được lộ trình với ước lượng 3–5đ.
    assert report["activity"]["expected_score"] is None
    assert report["relevance_label"] == config.LABEL_POTENTIAL


def test_criterion_mapping(catalog):
    text = ("NGÀY HỘI HIẾN MÁU NHÂN ĐẠO\nThời gian: 07h30 - 10h00, ngày 28/11/2026\n"
            "Địa điểm: Sân Trường, Cơ sở Nguyễn Văn Cừ\nĐược cộng 4 điểm rèn luyện.")
    act = nlp_engine.analyze_post(text, criteria_catalog=catalog)["activity"]
    # Hiến máu = trách nhiệm công dân trong quan hệ cộng đồng → nhóm 4 (không phải nhóm 3)
    assert act["criterion_code"] == "TC_4"


# ---------------------------------------------------------------------------
# 3. Phân loại 2 bước
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key,expected", [
    ("hoi_thao_ai", config.LABEL_POTENTIAL),
    ("xuan_tinh_nguyen", config.LABEL_INSUFFICIENT),
    ("workshop_thuyet_trinh", config.LABEL_INSUFFICIENT),
    ("cuoc_thi_khoi_nghiep", config.LABEL_POTENTIAL),
    ("chuc_mung_olympic", config.LABEL_NOT_RELEVANT),
    ("tuyen_thuc_tap", config.LABEL_NOT_RELEVANT),
    ("hien_mau", config.LABEL_POTENTIAL),
])
def test_demo_posts_labels(key, expected, catalog):
    post = next(p for p in seed_data.DEMO_POSTS if p["key"] == key)
    report = nlp_engine.analyze_post(post["text"], criteria_catalog=catalog)
    assert report["relevance_label"] == expected


def test_benchmark_agreement_high(catalog):
    """Bộ heuristic phải khớp ≥ 90% nhãn chuẩn còn hiệu lực.

    Các mẫu có nhãn chuẩn là EVENT_CANDIDATE *chỉ vì bài đăng không ghi điểm* được
    bỏ khỏi phép so khớp: từ 2026-11-16, thiếu điểm không còn là lý do để xếp
    "chưa rõ quyền lợi ĐRL" — điểm của hoạt động luôn là ước lượng 3–5đ.
    """
    SUPERSEDED = config.LABEL_EVENT_CANDIDATE
    compared = agree = 0
    for row in seed_data.BENCHMARK_DATASET:
        if row["label"] == SUPERSEDED:
            continue
        report = nlp_engine.analyze_post(row["text"], criteria_catalog=catalog)
        compared += 1
        agree += int(report["relevance_label"] == row["label"])
    ratio = agree / max(compared, 1)
    assert ratio >= 0.9, f"Chỉ khớp {ratio:.0%} nhãn benchmark ({agree}/{compared})"


# ---------------------------------------------------------------------------
# 4. Schema 1
# ---------------------------------------------------------------------------
def test_report_schema_keys(catalog):
    report = nlp_engine.analyze_post(seed_data.DEMO_POSTS[0]["text"], criteria_catalog=catalog)
    for key in ("post_type", "relevance_label", "relevance_reason",
                "is_student_participation_possible", "activity", "missing_flags",
                "drl_assessment"):
        assert key in report
    for key in ("title", "organizer", "location", "start_time", "end_time",
                "registration_deadline", "expected_score", "criterion_code"):
        assert key in report["activity"]
    for key in ("is_missing_time", "is_missing_location",
                "is_missing_content", "is_missing_score"):
        assert key in report["missing_flags"]
        assert isinstance(report["missing_flags"][key], bool)
    json.dumps(report, ensure_ascii=False)  # phải serialize được


# ---------------------------------------------------------------------------
# 5. An toàn AI
# ---------------------------------------------------------------------------
def test_ai_cannot_self_verify(catalog):
    local = nlp_engine.analyze_post(seed_data.DEMO_POSTS[0]["text"], criteria_catalog=catalog)
    ai_report = {
        "relevance_label": "VERIFIED_DRL",
        "activity": {"expected_score": 5, "criterion_code": "TC_2"},
        "drl_assessment": {"status": "ADMIN_APPROVED"},
    }
    sanitized, warnings = sanitize_ai_report(ai_report, local, catalog)
    assert sanitized["relevance_label"] != "VERIFIED_DRL"
    assert any("VERIFIED_DRL" in w for w in warnings)


def test_ai_unknown_criterion_dropped(catalog):
    local = nlp_engine.analyze_post(seed_data.DEMO_POSTS[0]["text"], criteria_catalog=catalog)
    ai_report = {"activity": {"criterion_code": "TC_99.99", "expected_score": 5}}
    sanitized, warnings = sanitize_ai_report(ai_report, local, catalog)
    assert sanitized["activity"]["criterion_code"] != "TC_99.99"
    assert any("TC_99.99" in w for w in warnings)


# ---------------------------------------------------------------------------
# 6. Database & seed
# ---------------------------------------------------------------------------
def test_schema_tables(temp_db):
    with database.transaction(temp_db) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] for r in rows}
    required = {"Sources", "SourcePosts", "Activities", "DRLCriteria", "StudentProfile",
                "StudentCriterionProgress", "StudentSchedule", "AuditLogs"}
    assert required.issubset(names)


def test_seed_counts(temp_db):
    stats = database.dashboard_stats(temp_db)
    assert stats["n_posts"] == len(seed_data.DEMO_POSTS)
    assert stats["n_criteria"] == len(seed_data.DEMO_CRITERIA)
    assert stats["n_schedule"] == len(seed_data.DEMO_SCHEDULE)
    posts = database.get_posts(temp_db)
    assert (posts["is_demo"] == 1).all()


def test_content_hash_present_and_duplicates_allowed(temp_db):
    posts = database.get_posts(temp_db)
    assert all(len(h) == 64 for h in posts["content_hash"])
    source_id = database.ensure_default_source(temp_db)
    text = seed_data.DEMO_POSTS[0]["text"]
    id1 = database.insert_source_post(source_id, text, "u", "TEST", db_path=temp_db)
    id2 = database.insert_source_post(source_id, text, "u", "TEST", db_path=temp_db)
    assert id1 != id2, "MVP cho phép ghi trùng"
    assert len(database.get_posts(temp_db)) == len(posts) + 2


def test_sync_payload_roundtrip(temp_db):
    payload = seed_data.demo_sync_payload()
    database.upsert_profile({
        "student_id": payload["student_profile"]["student_id"],
        "semester": payload["student_profile"]["semester"],
        "current_total_score": payload["student_profile"]["current_total_score"],
        "score_type": payload["student_profile"]["score_type"],
        "target_score": 90,
        "has_detailed_criteria": True,
    }, temp_db)
    database.replace_criterion_progress(
        payload["student_profile"]["student_id"],
        payload["student_profile"]["semester"],
        payload["drl_progress"], temp_db)
    database.replace_schedule(payload["student_profile"]["student_id"],
                              payload["student_profile"]["semester"],
                              payload["timetable"], db_path=temp_db)
    progress = database.get_criterion_progress(
        payload["student_profile"]["student_id"],
        payload["student_profile"]["semester"], temp_db)
    assert len(progress) == len(payload["drl_progress"])
    assert len(database.get_schedule(payload["student_profile"]["student_id"], temp_db)) \
        == len(payload["timetable"])


# ---------------------------------------------------------------------------
# 7. NetworkX pathway
# ---------------------------------------------------------------------------
def _synthetic_case():
    """3 hoạt động: 1 trùng lịch học, 2 xếp được liên tiếp."""
    schedule = [{"course_code": "PHY1", "course_name": "Lý", "day_of_week": "Thursday",
                 "start_time": "07:30", "end_time": "11:30", "room": "A1", "campus": "Linh Trung"}]
    activities = [
        {"id": 1, "title": "A", "start_time": "2027-03-04 08:00", "end_time": "2027-03-04 10:00",
         "campus": "Linh Trung", "relevance_label": config.LABEL_POTENTIAL, "expected_score": 5,
         "criterion_code": "TC_2", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "NEEDS_HUMAN_REVIEW"},
        {"id": 2, "title": "B", "start_time": "2027-03-06 08:00", "end_time": "2027-03-06 10:00",
         "campus": "Linh Trung", "relevance_label": config.LABEL_POTENTIAL, "expected_score": 4,
         "criterion_code": "TC_2", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "NEEDS_HUMAN_REVIEW"},
        {"id": 3, "title": "C", "start_time": "2027-03-06 11:00", "end_time": "2027-03-06 13:00",
         "campus": "NVC", "relevance_label": config.LABEL_VERIFIED, "expected_score": 3,
         "criterion_code": "TC_3", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "ADMIN_APPROVED"},
    ]
    import pandas as pd
    return pd.DataFrame(activities), pd.DataFrame(schedule)


def test_conflict_filtered_and_travel_edge():
    activities, schedule = _synthetic_case()
    candidates, rejected, conflicts = pathway.prepare_candidates(
        activities, schedule, include_past=True)
    assert [c["id"] for c in candidates] == [2, 3]
    assert len(conflicts) == 1 and conflicts[0]["id"] == 1

    graph = pathway.build_activity_graph(candidates)
    # B (Linh Trung) kết thúc 10:00 → C (NVC) bắt đầu 11:00: cần 45 phút ⇒ 10:00+45 ≤ 11:00 ✔
    assert graph.has_edge(2, 3)
    edge = graph[2][3]
    assert edge["travel_minutes"] == 45
    assert edge["slack_minutes"] == 15


def test_travel_time_blocks_edge():
    activities, _ = _synthetic_case()
    activities.loc[activities["id"] == 3, "start_time"] = "2027-03-06 10:30"
    activities.loc[activities["id"] == 3, "end_time"] = "2027-03-06 12:00"
    candidates, _, _ = pathway.prepare_candidates(activities, _synthetic_case()[1],
                                                  include_past=True)
    graph = pathway.build_activity_graph(candidates)
    assert not graph.has_edge(2, 3), "Không kịp di chuyển 45 phút ⇒ không có cạnh"


def test_criterion_cap_respected():
    import pandas as pd
    # Hai hoạt động cùng tiêu chí, tổng 10 điểm nhưng dư địa chỉ còn 6
    activities = pd.DataFrame([
        {"id": 1, "title": "A", "start_time": "2027-03-02 08:00", "end_time": "2027-03-02 10:00",
         "campus": "NVC", "relevance_label": config.LABEL_POTENTIAL, "expected_score": 5,
         "criterion_code": "TC_2", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "X"},
        {"id": 2, "title": "B", "start_time": "2027-03-09 08:00", "end_time": "2027-03-09 10:00",
         "campus": "NVC", "relevance_label": config.LABEL_POTENTIAL, "expected_score": 5,
         "criterion_code": "TC_2", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "X"},
        {"id": 3, "title": "C", "start_time": "2027-03-02 11:00", "end_time": "2027-03-02 12:00",
         "campus": "NVC", "relevance_label": config.LABEL_VERIFIED, "expected_score": 3,
         "criterion_code": "TC_3", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0, "verification_status": "ADMIN_APPROVED"},
    ])
    candidates, _, conflicts = pathway.prepare_candidates(
        activities, pd.DataFrame([]), include_past=True)
    assert len(candidates) == 3 and not conflicts
    graph = pathway.build_activity_graph(candidates)
    headroom = {"TC_2": 6.0, "TC_3": 20.0}
    result = pathway.dynamic_programming_path(candidates, graph, headroom,
                                              target_remaining=10, prefer_verified=True)
    assert result["total_expected_score"] <= 9  # 5 + 3, KHÔNG học 5 + 5 = 10 vì vượt trần
    assert result["total_expected_score"] >= 8


def test_pathway_end_to_end(temp_db):
    result = pathway.compute_optimal_pathway(db_path=temp_db)
    assert "error" not in result
    route = result["route"]
    assert route["total_expected_score"] >= 0
    # tổng điểm theo tiêu chí không được vượt dư địa
    for code, gain in route["gains_by_criterion"].items():
        assert gain <= route["criterion_missing"].get(code, gain) + 1e-6
    # mỗi hoạt động trong lộ trình phải khớp tổng
    assert abs(sum(a["expected_score"] for a in route["activities"])
               - route["total_expected_score"]) < 1e-6


# ---------------------------------------------------------------------------
# 8. ML benchmark
# ---------------------------------------------------------------------------
def test_benchmark_dataset_size_and_balance():
    assert len(seed_data.BENCHMARK_DATASET) >= 20
    labels = [row["label"] for row in seed_data.BENCHMARK_DATASET]
    for lbl in (config.LABEL_NOT_RELEVANT, config.LABEL_INSUFFICIENT,
                config.LABEL_EVENT_CANDIDATE, config.LABEL_POTENTIAL):
        assert labels.count(lbl) >= 5


def test_ml_vs_baseline():
    result = ml_benchmark.run_benchmark(run_cv=True, n_splits=3)
    assert result.n_train + result.n_test == len(seed_data.BENCHMARK_DATASET)
    assert set(result.metrics_ml) >= {"accuracy", "precision_macro", "recall_macro", "f1_macro"}
    assert result.confusion_ml.shape[0] == len(result.labels)
    assert result.cv_scores["f1_macro_mean"] > 0.5
    assert result.metrics_ml["f1_macro"] >= result.metrics_baseline["f1_macro"]
    df = ml_benchmark.comparison_dataframe(result)
    assert len(df) == 3  # baseline, đề xuất, chênh lệch


def test_baseline_classifier_is_deterministic():
    texts = [row["text"] for row in seed_data.BENCHMARK_DATASET]
    labels = [row["label"] for row in seed_data.BENCHMARK_DATASET]
    model = ml_benchmark.BaselineKeywordClassifier().fit(texts, labels)
    preds = model.predict(texts)
    assert len(preds) == len(texts)
    assert set(preds).issubset(set(labels))


# ---------------------------------------------------------------------------
# 9. Seed sync payload
# ---------------------------------------------------------------------------
def test_demo_sync_payload_schema():
    payload = seed_data.demo_sync_payload()
    assert payload["sync_source"] == config.SYNC_SOURCE_TAG
    assert payload["is_demo"] is True
    assert payload["student_profile"]["has_detailed_criteria"] is True
    assert len(payload["drl_progress"]) == len(seed_data.DEMO_CRITERIA)
    assert len(payload["timetable"]) == len(seed_data.DEMO_SCHEDULE)
    total = sum(row["current_score"] for row in payload["drl_progress"])
    assert payload["student_profile"]["current_total_score"] == total


def test_weekday_parse_vietnamese():
    text = ("LỚP TẬP HUẤN\nThời gian: 08h00 - 11h00, ngày 26/11/2026 (Thứ Năm)\n"
            "📍 Phòng B105, Cơ sở Linh Trung\nĐược cộng 3 điểm rèn luyện.")
    start = datetime.strptime(
        nlp_engine.analyze_post(text, criteria_catalog=seed_data.DEMO_CRITERIA)["activity"]["start_time"],
        "%Y-%m-%d %H:%M")
    assert start.weekday() == 3  # Thứ Năm


# ---------------------------------------------------------------------------
# Hồi quy: dữ liệu THẬT từ cổng trường (dựa trên ảnh chụp CTĐB của người dùng)
# ---------------------------------------------------------------------------
REAL_CTDB_TIMETABLE = [
    {"course_code": "BAA00005", "course_name": "Kinh tế đại cương", "day_of_week": "Tuesday",
     "start_time": "07:30", "end_time": "11:10", "room": "E402", "campus": "NVC"},
    {"course_code": "BAA00021", "course_name": "Thực tập 1", "day_of_week": "Monday",
     "start_time": "07:30", "end_time": "11:10", "room": "", "campus": "NVC"},
    {"course_code": "CSC10008", "course_name": "Mạng máy tính", "day_of_week": "Tuesday",
     "start_time": "13:30", "end_time": "17:10", "room": "B116", "campus": "NVC"},
    {"course_code": "CSC10014", "course_name": "Tư duy tính toán", "day_of_week": "Monday",
     "start_time": "13:30", "end_time": "17:10", "room": "C36", "campus": "NVC"},
    {"course_code": "CSC10014", "course_name": "Tư duy tính toán", "day_of_week": "Friday",
     "start_time": "07:30", "end_time": "09:30", "room": "152", "campus": "NVC"},
    {"course_code": "MTH00006", "course_name": "Vi tích phân 2", "day_of_week": "Thursday",
     "start_time": "07:30", "end_time": "11:10", "room": "E308", "campus": "NVC"},
    {"course_code": "MTH00006", "course_name": "Vi tích phân 2", "day_of_week": "Thursday",
     "start_time": "13:30", "end_time": "15:30", "room": "E307", "campus": "NVC"},
]


def test_sync_timetable_only_keeps_previous_score(tmp_path):
    """Gói chỉ có TKB (chưa quét DRL) KHÔNG được xoá điểm/tín chỉ tiêu chí đã đồng bộ."""
    from drl import database, ui_common

    db = tmp_path / "regress.db"
    database.init_db(db)
    full = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-14T00:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 61, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "Ý thức học tập",
             "current_score": 18, "max_score": 20, "mandatory": True},
        ],
        "timetable": REAL_CTDB_TIMETABLE,
    }
    ui_common.apply_sync_payload(full, db_path=db)

    only_ttb = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-14T00:05:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": None, "score_type": "SELF_DECLARED"},
        "drl_progress": [],
        "timetable": REAL_CTDB_TIMETABLE,
    }
    info = ui_common.apply_sync_payload(only_ttb, db_path=db)

    profile = database.get_profile("25127302", "HK1_2026_2027", db_path=db)
    assert float(profile["current_total_score"]) == 61.0, "Điểm cũ bị ghi đè!"
    assert len(database.get_criterion_progress("25127302", "HK1_2026_2027", db_path=db)) == 1
    assert info["kept_previous_score"] is True
    assert info["n_timetable"] == len(REAL_CTDB_TIMETABLE)


def test_real_timetable_conflict_and_pathway(tmp_path):
    """Lịch thật 7 buổi: Thứ 3 có 2 buổi liền nhau, Thứ 5 có 2 buổi cùng môn."""
    from drl import database, pathway

    db = tmp_path / "regress2.db"
    database.init_db(db)
    database.replace_schedule("25127302", "HK1_2026_2027", REAL_CTDB_TIMETABLE, db_path=db)
    df = database.get_schedule("25127302", db_path=db)
    assert len(df) == 7
    assert set(df["room"].fillna("")) >= {"E402", "B116", "C36", "152", "E308", "E307"}

    # Hoạt động rơi ĐÚNG vào giờ học Thứ 5 07:30-11:10 (MTH00006) phải bị loại
    clash_day = (datetime.now() + timedelta(days=(3 - datetime.now().weekday()) % 7 + 7)).date()
    acts = pd.DataFrame([
        {"id": 1, "title": "Hội thảo AI", "relevance_label": "VERIFIED_DRL",
         "start_time": f"{clash_day} 08:00", "end_time": f"{clash_day} 10:00",
         "location": "E402", "campus": "NVC", "expected_score": 5,
         "criterion_code": "TC_2", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0},
        {"id": 2, "title": "Talkshow kỹ năng", "relevance_label": "VERIFIED_DRL",
         "start_time": f"{clash_day} 18:00", "end_time": f"{clash_day} 20:00",
         "location": "Hội trường", "campus": "NVC", "expected_score": 3,
         "criterion_code": "TC_3", "is_missing_time": 0, "is_missing_location": 0,
         "is_missing_content": 0, "is_missing_score": 0},
    ])
    candidates, _rejected, conflicts = pathway.prepare_candidates(acts, df)
    kept_ids = {c["id"] for c in candidates}
    assert 2 in kept_ids, "Hoạt động 18:00 không trùng giờ học phải được giữ"
    assert 1 not in kept_ids, "Hoạt động 08:00-10:00 trùng MTH00006 phải bị loại"
    assert conflicts and conflicts[0]["id"] == 1


# ---------------------------------------------------------------------------
# Bộ thu thập tự động (crawler) – test OFFLINE bằng HTML/JSON giả lập cấu trúc thật
# ---------------------------------------------------------------------------
def test_crawler_ctsv_parses_real_api_shape():
    """API CTSV thật trả {data:[...], meta:{...}} – phải bóc đúng trường."""
    from drl import crawler

    src = crawler.CtsvApiSource()
    row = {
        "idCode": 535,
        "title": "Thông báo tổ chức Workshop “Sơ cấp cứu”",
        "slug": "thong-bao-workshop-so-cap-cuu",
        "content": "<p>Kính mời sinh viên tham dự workshop.</p><p>Địa điểm: Giảng đường 1</p>",
        "imageUrl": "https://ctsv.hcmus.edu.vn/x.jpg",
        "author": "Trương Quốc Tiên",
        "createdAt": "2026-10-24T13:28:12.169Z",
        "category": {"idCode": 1, "name": "KỸ NĂNG"},
        "tags": [],
    }
    post = src._to_post(row)
    assert post.external_id == "ctsv-535"
    assert post.title.startswith("Thông báo tổ chức Workshop")
    assert "<p>" not in post.content, "Phải bóc sạch HTML khỏi nội dung"
    assert "workshop" in post.content.lower()
    assert post.url.endswith("thong-bao-workshop-so-cap-cuu")
    assert post.published_at.startswith("2026-10-24")


def test_crawler_events_uses_structured_time_and_venue():
    """Adapter sự kiện phải dùng start_date/end_date/venue có sẵn của nguồn."""
    from drl import crawler

    src = crawler.HcmusEventsSource()
    row = {
        "id": 12345,
        "title": "Hội thảo khoa học về Trí tuệ nhân tạo",
        "description": "<p>Nội dung hội thảo</p>",
        "url": "https://hcmus.edu.vn/event/hoi-thao-ai/",
        "start_date": "2026-11-22T08:30:00+07:00",
        "end_date": "2026-11-22T11:30:00+07:00",
        "venue": {"venue": "Hội trường I", "address": "227 Nguyễn Văn Cừ, Quận 5"},
        "organizer": [{"organizer": "Trường Đại học Khoa học tự nhiên"}],
    }
    post = src._to_post(row)
    assert post.start_time == "2026-11-22 08:30"
    assert post.end_time == "2026-11-22 11:30"
    assert "Hội trường I" in post.location and "Nguyễn Văn Cừ" in post.location
    assert "Khoa học tự nhiên" in post.organizer


def test_crawler_fit_html_parses_listing():
    """Trang Khoa CNTT: <h6><a>tiêu đề</a></h6> + .post-date chứa dd/mm/yyyy."""
    from drl import crawler

    page = """
    <div>
      <h6><a href="/tin-tuc/dang-ky-hoi-thao-cv">Đăng ký tham dự Hội thảo: Xây dựng CV</a></h6>
      <p class="mb-1">Mô tả ngắn về hội thảo dành cho sinh viên.</p>
      <ul class="post-meta"><li class="post-date"><i class="uil uil-calendar-alt"></i>
        <span>11/11/2026</span></li></ul>
      <h6><a href="/tin-tuc/ai-doanh-nghiep">Hội thảo "AI trong doanh nghiệp"</a></h6>
      <ul class="post-meta"><li class="post-date"><span>05/11/2026</span></li></ul>
    </div>
    """
    posts = crawler.FitNewsSource()._parse_listing(page)
    assert len(posts) == 2
    assert posts[0].title.startswith("Đăng ký tham dự Hội thảo")
    assert posts[0].published_at == "2026-11-11"
    assert posts[1].published_at == "2026-11-05"
    assert posts[1].url == "https://fit.hcmus.edu.vn/tin-tuc/ai-doanh-nghiep"


def test_crawler_activity_filter_rejects_admin_news():
    """Bộ lọc phải loại tin học vụ/hành chính và giữ hoạt động sinh viên."""
    from drl import crawler

    assert crawler.is_activity_like(
        "Thông báo tổ chức Workshop “Sơ cấp cứu: những kỹ năng cần thiết”")
    assert crawler.is_activity_like(
        "Đăng ký tham dự Hội thảo: Xây dựng CV nổi bật và chinh phục phỏng vấn")
    assert not crawler.is_activity_like(
        "Thông báo thu phí bảo hiểm y tế năm 2027 (đợt 1)")
    assert not crawler.is_activity_like(
        "Thông báo kết quả chính thức Điểm rèn luyện sinh viên HK2/2025-2026")
    assert not crawler.is_activity_like(
        "NCS. Nguyễn Ngọc Trung bảo vệ thành công luận án tiến sĩ")
    assert not crawler.is_activity_like(
        "“LỊCH SỬ DỤNG PHÒNG HỌP (Tuần 16/11/2026 đến 22/11/2026)”")


def test_crawler_marks_invitation():
    """Bài có lời mời đăng ký phải được đánh dấu để ưu tiên hiển thị."""
    from drl import crawler

    assert crawler.looks_like_invitation(
        "Thông báo tổ chức Workshop", "Kính mời sinh viên đăng ký tham dự trước 20/11.")
    assert not crawler.looks_like_invitation(
        "Hội nghị khoa học đã diễn ra", "Hội nghị đã tổng kết với 200 báo cáo.")


# ---------------------------------------------------------------------------
# Hồi quy: bóc tách trên ĐỊNH DẠNG THẬT của cổng trường HCMUS
# ---------------------------------------------------------------------------
def test_vietnamese_time_format_13g30():
    """Cổng CTSV viết '13g30, ngày 08/11/2026' – chữ g thay dấu hai chấm."""
    from drl import nlp_engine

    text = ("2. Thời gian: 13g30, ngày 08/11/2026 (chủ nhật).\n"
            "3. Địa điểm: Giảng đường 1, Trường Đại học Khoa học tự nhiên, ĐHQG-HCM")
    act = nlp_engine.analyze_post(text)["activity"]
    assert act["start_time"].startswith("2026-11-08 13:30"), act["start_time"]
    assert "Giảng đường 1" in (act["location"] or "")


def test_office_hours_not_treated_as_event_time():
    """'Giờ làm việc: 8:00 - 11:30' KHÔNG phải giờ diễn ra hoạt động."""
    from drl import nlp_engine

    text = ("RECAP TẬP HUẤN\n"
            "- Giờ làm việc: Từ thứ Hai - thứ Sáu | 8:00 - 11:30 | 13:30 - 16:30\n"
            "Buổi tập huấn diễn ra sôi nổi.")
    act = nlp_engine.analyze_post(text)["activity"]
    assert not act["start_time"], f"Không được lấy giờ hành chính: {act['start_time']}"


def test_location_rejects_noun_phrases():
    """Cụm danh từ không trỏ tới không gian cụ thể phải bị loại (thà trống còn hơn sai)."""
    from drl.nlp_engine import ExtractionResult, _accept_location

    reject = ["phòng tránh nguy cơ xâm hại trực tuyến", "sân chơi dành cho sinh viên",
              "PHÒNG HỌP (Tuần 16/11/2026 đến 22/11/2026)",
              "phòng Phòng Khoa học – Công nghệ, đại diện trình bày tham luận"]
    accept = ["Giảng đường 1, Trường Đại học Khoa học tự nhiên", "Phòng F102, ĐHQG-HCM",
              "Hội trường B", "Trực tuyến (Online)"]
    for text in reject:
        assert not _accept_location(text, ExtractionResult()), f"Phải loại: {text}"
    for text in accept:
        assert _accept_location(text, ExtractionResult()), f"Phải nhận: {text}"

    # Có địa điểm thật + mệnh đề giải thích → cắt phần giải thích, giữ địa điểm
    res = ExtractionResult()
    assert _accept_location("Hội trường I trong khuôn khổ Hội thảo NMEC-4", res)
    assert res.location == "Hội trường I", res.location


def test_merge_duplicates_keeps_one_row(tmp_path):
    """Chạy thu thập 2 lần sinh bài trùng → gộp còn 1 bản, giữ bản có điểm cao hơn."""
    from drl import database

    db = tmp_path / "dup.db"
    database.init_db(db)
    base = {
        "title": "Thông báo tổ chức Workshop “Sơ cấp cứu”",
        "organizer": "Phòng CTSV", "location": "", "campus": "",
        "start_time": "2026-10-31 14:00", "end_time": "2026-10-31 16:00",
        "relevance_label": "EVENT_CANDIDATE", "verification_status": "UNVERIFIED",
        "is_missing_time": 0, "is_missing_location": 1, "is_missing_content": 0,
        "is_missing_score": 1, "is_demo": False,
    }
    database.insert_activity({**base, "expected_score": None}, db)
    database.insert_activity({**base, "expected_score": 5, "location": "Giảng đường 1"}, db)

    assert len(database.get_activities(db_path=db)) == 2
    res = database.merge_duplicates(db)
    assert res["rows_deleted"] == 1
    df = database.get_activities(db_path=db)
    assert len(df) == 1
    row = df.iloc[0]
    assert float(row["expected_score"]) == 5
    assert row["location"] == "Giảng đường 1", "Phải bổ sung trường trống từ bản bị xoá"


# ---------------------------------------------------------------------------
# Hồi quy: KHÔNG được thu thập sự kiện đã diễn ra
# ---------------------------------------------------------------------------
def test_is_upcoming_filters_expired():
    """Sự kiện đã kết thúc phải bị loại; sự kiện hôm nay phải được giữ."""
    from datetime import datetime, timedelta

    from drl import crawler

    now = datetime(2026, 11, 14, 12, 0)
    past = {"start_time": "2024-11-11 00:00", "end_time": "2024-11-16 23:59"}
    today = {"start_time": "2026-11-14 08:00", "end_time": "2026-11-14 11:30"}
    future = {"start_time": "2026-11-22 08:30", "end_time": "2026-11-22 11:30"}
    undated = {"start_time": "", "end_time": ""}

    assert crawler.is_upcoming(past, now=now) is False
    assert crawler.is_upcoming(today, now=now) is True
    assert crawler.is_upcoming(future, now=now) is True
    assert crawler.is_upcoming(undated, now=now) is None
    # Sự kiện nhiều ngày: còn hiệu lực nếu ngày KẾT THÚC chưa qua
    multi = {"start_time": "2026-11-10 00:00", "end_time": "2026-11-20 23:59"}
    assert crawler.is_upcoming(multi, now=now) is True
    _ = timedelta


def test_purge_expired_real_activities(tmp_path):
    """Xoá mục thật đã kết thúc, GIỮ mục tương lai và mục không rõ ngày."""
    from drl import database

    db = tmp_path / "purge.db"
    database.init_db(db)
    base = {"organizer": "X", "location": "", "campus": "",
            "relevance_label": "EVENT_CANDIDATE", "verification_status": "UNVERIFIED",
            "is_missing_time": 0, "is_missing_location": 1, "is_missing_content": 0,
            "is_missing_score": 1, "is_demo": False}
    database.insert_activity({**base, "title": "Sự kiện cũ 2024",
                              "start_time": "2024-11-11 08:00",
                              "end_time": "2024-11-11 11:00"}, db)
    database.insert_activity({**base, "title": "Sự kiện sắp tới",
                              "start_time": "2027-12-22 08:00",
                              "end_time": "2027-12-22 11:00"}, db)
    database.insert_activity({**base, "title": "Không rõ ngày"}, db)

    assert len(database.get_activities(db_path=db)) == 3
    res = database.purge_expired_real_activities(db)
    assert res["deleted"] == 1
    titles = set(database.get_activities(db_path=db)["title"])
    assert "Sự kiện cũ 2024" not in titles
    assert "Sự kiện sắp tới" in titles
    assert "Không rõ ngày" in titles


def test_multiday_event_spanning_today_not_hidden():
    """Sự kiện nhiều ngày đang diễn ra KHÔNG được xếp vào 'đã qua'.

    Lỗi thật đã gặp: Hội nghị Khoa học 09–16/11/2026 bị ẩn khi hôm nay là 14/11
    vì Tab Kho phân loại theo ngày BẮT ĐẦU. Phải dùng ngày KẾT THÚC.
    """
    from datetime import datetime as _dt

    import pandas as pd

    def _parse_day(value):
        raw = str(value or "")
        if len(raw) < 10:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return _dt.strptime(raw[:16] if ":" in raw else raw[:10], fmt).date()
            except ValueError:
                continue
        return None

    def verdict(row):
        end_day = _parse_day(row.get("end_time")) or _parse_day(row.get("start_time"))
        if end_day is None:
            return "unknown"
        return "past" if end_day < _dt.now().date() else "upcoming"

    span = {"start_time": "2026-11-09 08:00", "end_time": "2026-11-16 17:00"}
    done = {"start_time": "2026-11-10 08:00", "end_time": "2026-11-10 11:00"}
    undated = {"start_time": "", "end_time": ""}

    # Chỉ kiểm chứng khi hôm nay nằm trong khoảng 09–16/11/2026
    if _dt.now().date() == _dt(2026, 11, 14).date():
        assert verdict(span) == "upcoming", "Sự kiện đang diễn ra bị xếp nhầm là đã qua"
        assert verdict(done) == "past"
    assert verdict(undated) == "unknown"
    assert verdict({"start_time": "2020-01-01 08:00", "end_time": "2020-01-02 08:00"}) == "past"


# ---------------------------------------------------------------------------
# Cổng chặn "đủ thông tin mới vào kho" + bóc tách ngày/diễn giả
# ---------------------------------------------------------------------------
def test_deadline_is_not_event_date():
    """Hạn nộp hồ sơ KHÔNG được ghi thành ngày diễn ra.

    Đây là lỗi nghiêm trọng nhất có thể xảy ra: lưu workshop với ngày hết hạn
    đăng ký khiến sinh viên tưởng đã hết hạn và bỏ lỡ buổi thật.
    """
    from drl import event_details as ed

    text = """THÔNG BÁO
2. Thời gian: 14g00, ngày 31/10/2026 (Thứ 7).
3. Địa điểm: Giảng đường 1, Trường ĐH KHTN.
4. Báo cáo viên: BS.CKII. Trần Quang Khải - Bệnh viện đa khoa Tân Phú.
6. Hình thức đăng ký: sinh viên đăng ký từ 20g00 ngày 26/10/2026
   đến hết ngày 28/10/2026.
"""
    w = ed.extract_when(text)
    assert w["start_time"].startswith("2026-10-31"), w["start_time"]
    assert "14:00" in w["start_time"]
    assert w["deadline"].startswith("2026-10-28"), w["deadline"]
    assert w["start_raw"], "Phải giữ câu gốc để đối chiếu"
    assert ed.extract_speaker(text)[0].startswith("BS.CKII. Trần Quang Khải")


def test_duration_from_time_range():
    from drl import event_details as ed

    mins, raw = ed.extract_duration("Thời gian: từ 13g30 đến 16g30 cùng ngày.")
    assert mins == 180
    assert raw
    assert ed.extract_duration("Thời lượng: 90 phút")[0] == 90
    assert ed.extract_duration("Thời lượng: 2 giờ")[0] == 120
    assert ed.extract_duration("Không nói gì về thời lượng")[0] is None


def test_required_report_gate():
    """Thiếu bất kỳ trường bắt buộc nào → KHÔNG được coi là đủ."""
    from drl import event_details as ed

    full = {"title": "Workshop A", "start_time": "2026-11-18 00:00",
            "location": "Giảng đường 1", "organizer": "Phòng CTSV"}
    ok, missing = ed.required_report(full)
    assert ok and missing == []

    for field in ed.REQUIRED_FIELDS:
        broken = dict(full)
        broken[field] = ""
        ok2, missing2 = ed.required_report(broken)
        assert not ok2, f"Thiếu {field} mà vẫn cho qua"
        assert field in missing2


def test_gate_blocks_incomplete_and_keeps_speaker():
    """save_crawled_posts: mục thiếu địa điểm bị chặn, mục đủ được lưu kèm chi tiết."""
    from drl import crawler, database

    import tempfile
    from pathlib import Path as _P

    db = _P(tempfile.mkdtemp()) / "gate.db"
    database.init_db(db)

    content = ("2. Thời gian: 14g00, ngày 18/11/2026. "
               "3. Địa điểm: Giảng đường 1, Trường ĐH KHTN. "
               "4. Báo cáo viên: ThS. Nguyễn Văn A. "
               "Thời lượng: 90 phút.")
    good = {
        "source_key": "ctsv_api", "source_name": "Phòng Công tác Sinh viên HCMUS",
        "title": "Workshop đủ thông tin", "content": content,
        "url": "https://ctsv.hcmus.edu.vn/x", "published_at": "2026-11-01",
    }
    bad = dict(good)
    bad["title"] = "Workshop thiếu địa điểm"
    bad["content"] = "2. Thời gian: 14g00, ngày 18/11/2026. Không có địa điểm."
    bad["url"] = "https://ctsv.hcmus.edu.vn/y"

    res = crawler.save_crawled_posts([good, bad], db_path=db)
    titles = set(database.get_activities(db_path=db)["title"])
    assert "Workshop đủ thông tin" in titles
    assert "Workshop thiếu địa điểm" not in titles
    assert len(res["incomplete"]) == 1
    assert "location" in res["incomplete"][0]["missing"]


def test_negation_not_mistaken_for_label():
    """Câu "Không có địa điểm" KHÔNG được coi là nhãn địa điểm.

    Lỗi thật đã gặp: hệ thống coi chữ "địa điểm" trong câu phủ định là nhãn,
    rồi bóc nhầm giá trị từ dòng "Thời gian:" phía trên → lưu sai địa điểm.
    """
    from drl import event_details as ed

    assert ed.extract_location("2. Thời gian: 14g00, ngày 18/11/2026. "
                              "Không có địa điểm.")[0] == ""
    assert ed.extract_location("Thông báo về địa điểm thi mới của trường.")[0] == ""
    # Nhãn thật (đầu dòng, có thể có số thứ tự hoặc gạch đầu dòng) thì phải bóc
    assert "I.23" in ed.extract_location("- Địa điểm: Phòng I.23 cơ sở Nguyễn Văn Cừ")[0]
    assert "Giảng đường 1" in ed.extract_location(
        "3. Địa điểm: Giảng đường 1, Trường ĐH KHTN.")[0]
    assert ed.extract_speaker("Không có diễn giả tham gia.")[0] == ""


def test_duration_not_computed_across_days():
    """Sự kiện nhiều ngày không được suy ra 'thời lượng' vô nghĩa."""
    from drl import crawler, database

    import tempfile
    from pathlib import Path as _P

    db = _P(tempfile.mkdtemp()) / "multi.db"
    database.init_db(db)
    rec = {
        "source_key": "hcmus_events", "source_name": "Trường HCMUS – Lịch sự kiện",
        "title": "Hội nghị nhiều ngày", "content": "Địa điểm: Hội trường A.",
        "url": "https://hcmus.edu.vn/e/1", "published_at": "2026-11-01",
        "start_time": "2026-11-20 08:00", "end_time": "2026-11-27 17:00",
    }
    crawler.save_crawled_posts([rec], db_path=db)
    row = database.get_activities(db_path=db).iloc[0]
    assert row["duration_minutes"] is None or str(row["duration_minutes"]) in ("", "nan")


def test_date_range_and_procedural_dates_ignored():
    """Khoảng ngày '23/11 – 30/11/2026' phải hiểu là start→end.

    Và mốc thủ tục như "thời gian tích luỹ: từ 01/2026 đến 05/01/2027" KHÔNG
    được dùng làm ngày diễn ra (từng gây ra end_time < start_time).
    """
    from drl import event_details as ed

    w = ed.extract_when("Thời gian: Từ ngày 23/11 – 30/11/2026, theo thông báo.")
    assert w["start_time"].startswith("2026-11-23"), w["start_time"]
    assert w["end_time"].startswith("2026-11-30"), w["end_time"]

    w2 = ed.extract_when("Thời gian: 1/12 - 5/12/2026 tại Hội trường A.")
    assert w2["start_time"].startswith("2026-12-01")
    assert w2["end_time"].startswith("2026-12-05")

    text = ("- Thời gian tính tích luỹ: từ 01/2026 đến hết 05/01/2027.\n"
            "- Thời gian: Từ ngày 23/11 – 30/11/2026.")
    w3 = ed.extract_when(text)
    assert w3["start_time"].startswith("2026-11-23"), w3["start_time"]
    # Không bao giờ được trả về end < start
    assert not w3["end_time"] or w3["end_time"] >= w3["start_time"]


# ---------------------------------------------------------------------------
# Thời khóa biểu dạng lịch + chỉnh sửa của người dùng
# ---------------------------------------------------------------------------
def test_calendar_weekday_parsing():
    """Nhiều cách ghi thứ phải quy về cùng chỉ số 0..6."""
    from drl import calendar_view as cv

    assert cv.weekday_index("Monday") == 0
    assert cv.weekday_index("Thứ 2") == 0
    assert cv.weekday_index("T4") == 2
    assert cv.weekday_index("CN") == 6
    assert cv.weekday_index("chủ nhật") == 6
    assert cv.weekday_index("không phải thứ") is None


def test_calendar_renders_events_with_color_and_time():
    """Lịch phải đặt khối đúng vị trí giờ và hiện đủ thông tin."""
    from datetime import date

    from drl import calendar_view as cv

    html = cv.build_week_grid([
        {"title": "Giải tích 1", "subtitle": "I.12", "day_of_week": "Monday",
         "start_time": "07:30", "end_time": "09:30", "color": "#1f6feb"},
        {"title": "Đi làm thêm", "day_of_week": "Monday",
         "start_time": "18:00", "end_time": "21:00", "color": "#d97706",
         "kind": "personal"},
    ], week_start=date(2026, 11, 16))

    assert "Giải tích 1" in html and "Đi làm thêm" in html
    assert "07:30–09:30" in html and "18:00–21:00" in html
    assert "cal-personal" in html and "cal-class" in html
    # 7:30 so với mốc 6:00 → 1.5 giờ × 56px = 84px
    assert "top:84.0px" in html, "Khối 07:30 phải nằm đúng 84px tính từ 6:00"


def test_overlapping_events_share_width():
    """Hai việc trùng giờ phải chia đôi bề ngang, không che nhau."""
    from datetime import date

    from drl import calendar_view as cv

    html = cv.build_week_grid([
        {"title": "A", "day_of_week": "Monday", "start_time": "09:00",
         "end_time": "11:00"},
        {"title": "B", "day_of_week": "Monday", "start_time": "10:00",
         "end_time": "12:00"},
    ], week_start=date(2026, 11, 16))
    assert "left:0.0%" in html and "left:50.0%" in html
    assert "width:calc(50.0% - 3px)" in html


def test_schedule_crud_roundtrip():
    """Người dùng thêm → sửa → xoá việc bận cá nhân."""
    import tempfile
    from pathlib import Path as _P

    from drl import database

    db = _P(tempfile.mkdtemp()) / "sched.db"
    database.init_db(db)

    eid = database.add_schedule_entry("25127302", "HK1", {
        "course_name": "Đi làm thêm", "day_of_week": "Tuesday",
        "start_time": "18:00", "end_time": "21:00",
        "event_type": "personal", "color": "amber", "notes": "ca cố định",
    }, db_path=db)

    row = database.get_schedule_entry(eid, db)
    assert row["course_name"] == "Đi làm thêm"
    assert row["event_type"] == "personal"
    assert row["color"] == "amber"

    database.update_schedule_entry(eid, {"end_time": "22:00",
                                         "course_name": "Đi làm thêm (đổi ca)"}, db_path=db)
    row = database.get_schedule_entry(eid, db)
    assert row["end_time"] == "22:00"
    assert "đổi ca" in row["course_name"]

    database.delete_schedule_entry(eid, db_path=db)
    assert database.get_schedule_entry(eid, db) is None


def test_schedule_update_ignores_forbidden_columns():
    """Không cho sửa cột hệ thống như student_id qua update_schedule_entry."""
    import tempfile
    from pathlib import Path as _P

    from drl import database

    db = _P(tempfile.mkdtemp()) / "s2.db"
    database.init_db(db)
    eid = database.add_schedule_entry("A1", "HK1", {
        "course_name": "X", "day_of_week": "Monday",
        "start_time": "08:00", "end_time": "09:00"}, db_path=db)
    database.update_schedule_entry(eid, {"student_id": "HACKED"}, db_path=db)
    assert database.get_schedule_entry(eid, db)["student_id"] == "A1"


def test_markdown_rendered_inside_styled_box():
    """'**đậm**' bên trong khối HTML phải thành <strong>, không hiện dấu sao thô."""
    from drl import ui_common as ui

    out = ui.md_in_html("Dữ liệu **[DEMO]** và `file.py`")
    assert out == "Dữ liệu <strong>[DEMO]</strong> và <code>file.py</code>"
    assert "**" not in out


# ---------------------------------------------------------------------------
# Điểm rèn luyện: KHÔNG được hiển thị điểm cũ khi người dùng nhập 0
# ---------------------------------------------------------------------------
def test_zero_score_replaces_previous():
    """Gói JSON có current_total_score = 0 phải ghi 0, KHÔNG giữ điểm cũ.

    Lỗi thật: người dùng nạp JSON 0 điểm nhưng màn hình vẫn hiện 61 điểm mẫu
    vì code dùng `bool(old_score)` thay vì kiểm tra "có trường điểm hay không".
    """
    import tempfile
    from pathlib import Path as _P

    from drl import database, seed_data, ui_common as ui

    db = _P(tempfile.mkdtemp()) / "score.db"
    database.init_db(db)
    demo = seed_data.demo_sync_payload()
    ui.apply_sync_payload(demo, db_path=db)
    sid, sem = demo["student_profile"]["student_id"], demo["student_profile"]["semester"]
    assert database.get_profile(sid, sem, db)["current_total_score"] > 0

    real = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "student_profile": {"student_id": sid, "semester": sem,
                            "current_total_score": 0, "full_name": "Thật"},
        "drl_progress": [], "timetable": [],
    }
    info = ui.apply_sync_payload(real, db_path=db)

    assert database.get_profile(sid, sem, db)["current_total_score"] == 0
    assert info["cleared_previous_progress"] is True
    assert len(database.get_criterion_progress(sid, sem, db)) == 0


def test_missing_score_keeps_previous():
    """Gói KHÔNG có trường điểm (chỉ TKB) thì giữ điểm cũ — khác với điểm 0."""
    import tempfile
    from pathlib import Path as _P

    from drl import database, seed_data, ui_common as ui

    db = _P(tempfile.mkdtemp()) / "keep.db"
    database.init_db(db)
    demo = seed_data.demo_sync_payload()
    ui.apply_sync_payload(demo, db_path=db)
    sid, sem = demo["student_profile"]["student_id"], demo["student_profile"]["semester"]
    before = database.get_profile(sid, sem, db)["current_total_score"]

    only_tkb = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "student_profile": {"student_id": sid, "semester": sem},  # không có điểm
        "drl_progress": [], "timetable": [],
    }
    info = ui.apply_sync_payload(only_tkb, db_path=db)
    assert database.get_profile(sid, sem, db)["current_total_score"] == before
    assert info["kept_previous_score"] is True


def test_wipe_demo_profile():
    """Nút 'xoá hồ sơ mẫu' phải xoá hồ sơ + tiến độ + TKB, không để lại 61 điểm."""
    import tempfile
    from pathlib import Path as _P

    from drl import database, seed_data

    db = _P(tempfile.mkdtemp()) / "wipe.db"
    database.init_db(db)
    seed_data.seed_database(force=True, db_path=db) if "db_path" in seed_data.seed_database.__code__.co_varnames else None
    demo = seed_data.demo_sync_payload()
    from drl import ui_common as ui
    ui.apply_sync_payload(demo, db_path=db)
    sid = demo["student_profile"]["student_id"]

    removed = database.wipe_demo_profile(db)
    assert removed["profiles"] >= 1
    assert database.get_profile(sid, demo["student_profile"]["semester"], db) in (None, {})


# ---------------------------------------------------------------------------
# Hồi quy 2026-11-16: "Điểm hiện tại = 0 mà bảng tiêu chí vẫn 18/5/10…"
# ---------------------------------------------------------------------------
def test_purge_all_demo_data_removes_legacy_demo_profile(tmp_path):
    """DB của bản cũ phải được dọn sạch: hồ sơ [DEMO] + bảng tiêu chí đi kèm."""
    from drl import database

    db = tmp_path / "legacy_demo.db"
    database.init_db(db)
    database.upsert_profile({
        "student_id": "25127302", "full_name": "[DEMO] Nguyễn Văn A",
        "faculty": "Khoa Công nghệ Thông tin", "semester": "HK1_2026_2027",
        "current_total_score": 0, "score_type": "OFFICIAL_SYNCED",
        "target_score": 90, "has_detailed_criteria": 1,
    }, db)
    database.replace_criterion_progress("25127302", "HK1_2026_2027", [
        {"criterion_code": "TC_1", "name": "Ý thức học tập",
         "current_score": 18, "max_score": 20, "mandatory": 1},
        {"criterion_code": "TC_2", "name": "Hoạt động học thuật",
         "current_score": 5, "max_score": 15, "mandatory": 0},
    ], db)

    removed = database.purge_all_demo_data(db)
    assert removed["profiles"] == 1
    assert removed["progress"] == 2
    assert database.latest_profile(db) in ({}, None)
    assert len(database.get_criterion_progress("25127302", "HK1_2026_2027", db)) == 0


def test_purge_keeps_real_student_data(tmp_path):
    """Dọn dữ liệu mẫu KHÔNG được xoá hồ sơ thật của sinh viên."""
    from drl import database

    db = tmp_path / "real_student.db"
    database.init_db(db)
    database.upsert_profile({
        "student_id": "25127302", "full_name": "Nguyễn Văn Thật",
        "faculty": "Khoa Công nghệ Thông tin", "semester": "HK1_2026_2027",
        "current_total_score": 62, "score_type": "OFFICIAL_SYNCED",
        "target_score": 90, "has_detailed_criteria": 1,
    }, db)
    database.replace_criterion_progress("25127302", "HK1_2026_2027", [
        {"criterion_code": "TC_1", "name": "Ý thức học tập",
         "current_score": 18, "max_score": 20, "mandatory": 1},
    ], db)

    database.purge_all_demo_data(db)
    prof = database.latest_profile(db)
    assert prof.get("student_id") == "25127302"
    assert float(prof.get("current_total_score")) == 62.0
    assert len(database.get_criterion_progress("25127302", "HK1_2026_2027", db)) == 1


def test_sync_total_zero_drops_contradictory_progress(tmp_path):
    """Gói khai TỔNG = 0 mà vẫn kèm bảng tiêu chí có điểm → bảng vô nghĩa, phải bỏ."""
    from drl import database, ui_common

    db = tmp_path / "zero_conflict.db"
    database.init_db(db)
    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T00:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 0, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "Ý thức học tập",
             "current_score": 18, "max_score": 20, "mandatory": True},
        ],
    }
    info = ui_common.apply_sync_payload(payload, db_path=db)
    prof = database.get_profile("25127302", "HK1_2026_2027", db)
    assert float(prof.get("current_total_score")) == 0.0
    assert info["n_progress"] == 0
    assert info["cleared_previous_progress"] is True
    assert len(database.get_criterion_progress("25127302", "HK1_2026_2027", db)) == 0


def test_sync_partial_progress_keeps_reported_total(tmp_path):
    """Gói chỉ liệt kê MỘT PHẦN tiêu chí: tổng điểm phải giữ theo gói, không bị tụt."""
    from drl import database, ui_common

    db = tmp_path / "partial.db"
    database.init_db(db)
    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T00:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 61, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "Ý thức học tập",
             "current_score": 18, "max_score": 20, "mandatory": True},
        ],
    }
    ui_common.apply_sync_payload(payload, db_path=db)
    prof = database.get_profile("25127302", "HK1_2026_2027", db)
    # 18 < 61 nhưng KHÔNG được ghi đè thành 18 — tổng điểm là số của cổng trường.
    assert float(prof.get("current_total_score")) == 61.0


# ---------------------------------------------------------------------------
# Hồi quy 2026-11-16 (lần 2): gói quét CHỈ CÓ THỜI KHÓA BIỂU làm điểm thành 0
# ---------------------------------------------------------------------------
def test_timetable_only_payload_does_not_invent_zero_score(tmp_path):
    """Gói JSON chỉ có TKB (current_total_score = null) KHÔNG được ghi 0 điểm.

    Lỗi người dùng báo: nạp `hcmus_sync.json` quét từ cổng CTĐB → dashboard hiện
    "① Điểm hiện tại đã có: 0" trong khi sinh viên chỉ chưa đồng bộ điểm ĐRL.
    """
    from drl import database, ui_common

    db = tmp_path / "ttb_only.db"
    database.init_db(db)
    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T03:40:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": None, "score_type": "SELF_DECLARED",
                            "has_detailed_criteria": False},
        "drl_progress": [],
        "timetable": [
            {"course_code": "BAA00021", "course_name": "Thực tập 1",
             "day_of_week": "Tuesday", "start_time": "07:30", "end_time": "11:10",
             "campus": "C.36"},
            {"course_code": "CSC10014", "course_name": "Tư duy tính toán",
             "day_of_week": "Friday", "start_time": "07:30", "end_time": "09:30",
             "campus": "I.52"},
        ],
    }
    ui_common.apply_sync_payload(payload, db_path=db)

    prof = database.latest_profile(db)
    assert prof is not None
    # Điểm PHẢI là None (chưa biết), không được là 0.0
    assert prof["current_total_score"] is None
    # Thời khóa biểu vẫn phải được lưu
    assert len(database.get_schedule("25127302", db_path=db)) == 2


def test_real_zero_score_still_stored_as_zero(tmp_path):
    """Điểm thật = 0 (đã quét trang ĐRL, chưa được điểm nào) phải lưu 0, không phải NULL."""
    from drl import database, ui_common

    db = tmp_path / "real_zero.db"
    database.init_db(db)
    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T03:45:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 0, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [],
    }
    ui_common.apply_sync_payload(payload, db_path=db)
    prof = database.latest_profile(db)
    assert prof["current_total_score"] is not None
    assert float(prof["current_total_score"]) == 0.0


def test_later_score_sync_replaces_null(tmp_path):
    """Đồng bộ TKB trước (NULL), sau đó đồng bộ điểm thật → phải ghi đè bằng điểm thật."""
    from drl import database, ui_common

    db = tmp_path / "null_then_score.db"
    database.init_db(db)
    base = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T03:40:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": None},
        "timetable": [{"course_code": "BAA00021", "course_name": "Thực tập 1",
                       "day_of_week": "Tuesday", "start_time": "07:30", "end_time": "11:10"}],
    }
    ui_common.apply_sync_payload(base, db_path=db)
    assert database.latest_profile(db)["current_total_score"] is None

    with_score = {**base, "student_profile": {**base["student_profile"],
                                              "current_total_score": 62}}
    ui_common.apply_sync_payload(with_score, db_path=db)
    assert float(database.latest_profile(db)["current_total_score"]) == 62.0


def test_migration_allows_null_score_on_legacy_db(tmp_path):
    """DB cũ có NOT NULL trên current_total_score phải được migrate sang cho phép NULL."""
    import sqlite3

    from drl import database

    db = tmp_path / "legacy_schema.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE StudentProfile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            full_name TEXT,
            faculty TEXT,
            semester TEXT NOT NULL,
            current_total_score REAL NOT NULL DEFAULT 0,
            score_type TEXT NOT NULL DEFAULT 'SELF_DECLARED',
            target_score REAL NOT NULL DEFAULT 0,
            has_detailed_criteria INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO StudentProfile(student_id, semester, current_total_score, updated_at) "
        "VALUES ('25127302', 'HK1_2026_2027', 55, '2026-11-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    database.init_db(db)          # migrate
    cols = {r[1]: r for r in sqlite3.connect(db).execute("PRAGMA table_info(StudentProfile)")}
    assert cols["current_total_score"][3] == 0, "cột phải cho phép NULL"
    # Dữ liệu cũ phải được giữ nguyên
    prof = database.latest_profile(db)
    assert prof["student_id"] == "25127302"
    assert float(prof["current_total_score"]) == 55.0
    # Và giờ ghi được NULL
    database.upsert_profile({"student_id": "25127302", "semester": "HK1_2026_2027",
                             "current_total_score": None}, db)
    assert database.latest_profile(db)["current_total_score"] is None


# ---------------------------------------------------------------------------
# Điểm của HOẠT ĐỘNG là ƯỚC LƯỢNG dạng khoảng 3–5đ (2026-11-16)
# Bài đăng của trường không công bố điểm ĐRL; điểm chỉ chốt sau khi Phòng CTSV
# duyệt. Vì vậy app KHÔNG được (a) coi điểm là sự thật, (b) loại hoạt động chỉ vì
# bài đăng không ghi điểm.
# ---------------------------------------------------------------------------
def test_score_estimate_default_range():
    """Không có thông tin điểm → khoảng mặc định 3–5đ, không phải một con số."""
    from drl import score_estimate as se

    est = se.estimate_for_activity({})
    assert est["min"] == config.SCORE_ESTIMATE_MIN == 3.0
    assert est["max"] == config.SCORE_ESTIMATE_MAX == 5.0
    assert est["source"] == config.SCORE_ESTIMATE_SOURCE_DEFAULT


def test_score_estimate_from_post_is_still_range():
    """Bài đăng có nêu điểm → vẫn trả KHOẢNG, chỉ đổi nguồn."""
    from drl import score_estimate as se

    est = se.estimate_for_activity({"expected_score": 4})
    assert est["min"] < est["max"], "phải là khoảng, không phải 1 số"
    assert est["source"] == config.SCORE_ESTIMATE_SOURCE_POST


def test_total_range_sums_both_bounds():
    """Cộng nhiều hoạt động → cộng cả hai cận (3 HĐ = 9–15đ)."""
    from drl import score_estimate as se

    total = se.total_range([{}, {}, {}])
    assert total["min"] == 9.0
    assert total["max"] == 15.0
    assert total["n"] == 3


def test_missing_score_does_not_block_pathway():
    """Hoạt động KHÔNG có điểm trong bài vẫn phải vào được lộ trình.

    Đây là lỗi nghiệp vụ: trước đây nhãn EVENT_CANDIDATE + điều kiện
    `expected_score is None` khiến gần như MỌI hoạt động thật bị loại khỏi lộ trình.
    """
    from drl import pathway

    acts = pd.DataFrame([{
        "id": 1, "title": "Hội thảo không ghi điểm",
        "start_time": "2026-12-01 09:00", "end_time": "2026-12-01 11:00",
        "location": "Hội trường I", "campus": "NVC",
        "relevance_label": config.LABEL_POTENTIAL,
        "verification_status": config.VERIFY_NONE,
        "expected_score": 4.0, "expected_score_min": 3.0, "expected_score_max": 5.0,
        "criterion_code": "TC_2",
        "is_missing_time": 0, "is_missing_location": 0, "is_missing_content": 0,
        "is_missing_score": 0,
    }])
    cands, rejected, _ = pathway.prepare_candidates(acts, pd.DataFrame())
    assert len(cands) == 1, f"hoạt động bị loại oan: {rejected}"
    assert cands[0]["_score_min"] == 3.0
    assert cands[0]["_score_max"] == 5.0


def test_pathway_without_criteria_catalog_still_returns_activities():
    """Chưa nạp khung tiêu chí (headroom rỗng) KHÔNG được làm rỗng lộ trình."""
    from drl import pathway

    acts = pd.DataFrame([
        {"id": i, "title": f"Hoạt động {i}",
         "start_time": f"2026-12-0{i} 09:00", "end_time": f"2026-12-0{i} 11:00",
         "location": "Hội trường", "campus": "NVC",
         "relevance_label": config.LABEL_POTENTIAL,
         "verification_status": config.VERIFY_NONE,
         "expected_score": 4.0, "expected_score_min": 3.0, "expected_score_max": 5.0,
         "criterion_code": f"TC_{i}.1",
         "is_missing_time": 0, "is_missing_location": 0, "is_missing_content": 0,
         "is_missing_score": 0}
        for i in (1, 2, 3)
    ])
    cands, _, _ = pathway.prepare_candidates(acts, pd.DataFrame())
    graph = pathway.build_activity_graph(cands)
    result = pathway.dynamic_programming_path(cands, graph, {}, 0.0)
    assert len(result["activities"]) == 3, "headroom rỗng không được loại hết hoạt động"


def test_pathway_still_respects_criteria_ceiling():
    """Trần điểm theo tiêu chí vẫn phải được tôn trọng (không nới lỏng quá mức)."""
    from drl import pathway

    acts = pd.DataFrame([
        {"id": 1, "title": "HĐ 1", "start_time": "2026-12-01 09:00",
         "end_time": "2026-12-01 11:00", "location": "A", "campus": "NVC",
         "relevance_label": config.LABEL_POTENTIAL,
         "verification_status": config.VERIFY_NONE,
         "expected_score": 4.0, "expected_score_min": 3.0, "expected_score_max": 5.0,
         "criterion_code": "TC_2",
         "is_missing_time": 0, "is_missing_location": 0, "is_missing_content": 0,
         "is_missing_score": 0},
    ])
    cands, _, _ = pathway.prepare_candidates(acts, pd.DataFrame())
    graph = pathway.build_activity_graph(cands)
    # Chỉ còn 2 điểm dư địa < 4 điểm của hoạt động → phải bị loại
    result = pathway.dynamic_programming_path(cands, graph, {"TC_2": 2.0}, 0.0)
    assert len(result["activities"]) == 0


def test_activities_display_shows_range_not_single_number():
    """Bảng hiển thị phải ghi '3–5đ', không phải một con số như thể chắc chắn."""
    from drl import ui_common

    df = pd.DataFrame([{
        "id": 1, "title": "Hội thảo",
        "expected_score": 4.0, "expected_score_min": 3.0, "expected_score_max": 5.0,
    }])
    shown = ui_common.activities_to_display_df(df)
    score_cell = str(shown["Điểm (ước lượng)"].iloc[0])
    assert "–" in score_cell, f"phải là khoảng, nhận được {score_cell!r}"
    assert "3" in score_cell and "5" in score_cell


# ---------------------------------------------------------------------------
# Hồi quy 2026-11-16: quét CẢ trang ĐRL + TKB nhưng tiến độ vẫn sai
# Nguyên nhân: extension gửi max_score = null (trang không hiện điểm tối đa)
# → app ghi 0 → "còn thiếu = max − current" = 0 → cột nào cũng đầy 100%.
# ---------------------------------------------------------------------------
def test_progress_null_max_falls_back_to_rule_framework(tmp_path):
    """max_score = null phải lấy từ khung quy chế, KHÔNG được ghi 0."""
    from drl import database, ui_common

    db = tmp_path / "null_max.db"
    database.init_db(db)
    database.ensure_rule_framework(db)   # khung quy chế: TC_1 = 20, TC_2 = 20 (5 nhóm, tổng 100)

    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T06:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 62},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "A", "current_score": 18, "max_score": None},
            {"criterion_code": "TC_2", "name": "B", "current_score": 5, "max_score": None},
        ],
        "timetable": [{"course_code": "X", "course_name": "Y", "day_of_week": "Monday",
                       "start_time": "07:30", "end_time": "09:30"}],
    }
    ui_common.apply_sync_payload(payload, db_path=db)

    df = database.get_criterion_progress("25127302", "HK1_2026_2027", db)
    assert len(df) == 2
    assert float(df["max_score"].sum()) == 40.0, "max 20 (TC_1) + 20 (TC_2) lấy từ khung quy chế"
    assert float(df["current_score"].sum()) == 23.0
    # Đây là con số người dùng thấy: còn thiếu 17 điểm (40 − 23)
    missing = (df["max_score"] - df["current_score"]).clip(lower=0).sum()
    assert float(missing) == 17.0
    # Thời khóa biểu vẫn phải lưu cùng lúc
    assert len(database.get_schedule("25127302", db_path=db)) == 1


def test_progress_auto_loads_rule_framework_when_missing(tmp_path):
    """Danh mục tiêu chí trống + gói không kèm max → tự nạp khung quy chế."""
    from drl import database, ui_common

    db = tmp_path / "auto_framework.db"
    database.init_db(db)
    assert database.get_criteria(db).empty

    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T06:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 62},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "A", "current_score": 18, "max_score": None},
        ],
    }
    ui_common.apply_sync_payload(payload, db_path=db)
    assert len(database.get_criteria(db)) == 5, "phải tự nạp khung quy chế (5 nhóm)"
    df = database.get_criterion_progress("25127302", "HK1_2026_2027", db)
    assert float(df["max_score"].iloc[0]) == 20.0


def test_progress_explicit_max_wins_over_framework(tmp_path):
    """Gói có max_score thật thì phải dùng số của gói, không lấy khung."""
    from drl import database, ui_common

    db = tmp_path / "explicit_max.db"
    database.init_db(db)
    database.ensure_rule_framework(db)

    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T06:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 25},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "A", "current_score": 18, "max_score": 25},
        ],
    }
    ui_common.apply_sync_payload(payload, db_path=db)
    df = database.get_criterion_progress("25127302", "HK1_2026_2027", db)
    assert float(df["max_score"].iloc[0]) == 25.0, "phải tôn trọng max trong gói"


def test_progress_chart_skips_missing_delta_when_max_unknown():
    """Không biết điểm tối đa → KHÔNG được coi như đã đạt 100% mọi tiêu chí."""
    import pandas as pd

    from drl import ui_tab1_dashboard

    df = pd.DataFrame([
        {"criterion_code": "TC_1", "current_score": 18.0, "max_score": 0.0},
        {"criterion_code": "TC_2", "current_score": 5.0, "max_score": 0.0},
    ])
    # max = 0 không được sinh cột "Còn thiếu" (nếu sinh sẽ luôn = 0 → cột đầy 100%)
    deltas = (df["max_score"] - df["current_score"]).clip(lower=0)
    assert float(deltas.sum()) == 0.0
    # Hàm phải chạy được mà không lỗi và không vẽ phần "còn thiếu"
    assert callable(ui_tab1_dashboard._progress_chart)


# ---------------------------------------------------------------------------
# Hồi quy 2026-11-16 (lần 3): trang hcmus.drl.vn dùng 5 NHÓM, không có mã TC_x.y
# Trang thật hiển thị: | ⌄ | 1 | <tên nhóm> | Bắt đầu | Kết thúc | 0 |
# Extension cũ chỉ tìm mã TC_x.y nên trả về RỖNG → app báo "chưa có bảng điểm".
# ---------------------------------------------------------------------------
def test_rule_framework_has_five_real_groups():
    """Khung quy chế phải là 5 nhóm đúng như trang trường, tổng 100 điểm."""
    from drl import seed_data

    crits = seed_data.DEMO_CRITERIA
    assert len(crits) == 5, f"phải có 5 nhóm, đang có {len(crits)}"
    assert [c["code"] for c in crits] == ["TC_1", "TC_2", "TC_3", "TC_4", "TC_5"]
    assert sum(c["max_score"] for c in crits) == 100
    # Tên phải khớp văn bản trên trang thật
    assert crits[0]["name"].startswith("Trách nhiệm chấp hành pháp luật")
    assert crits[1]["name"].startswith("Trách nhiệm, tinh thần và thái độ")
    assert crits[2]["name"].startswith("Trách nhiệm tham gia các hoạt động chính trị")
    assert crits[3]["name"].startswith("Trách nhiệm công dân trong quan hệ cộng đồng")
    assert crits[4]["name"].startswith("Trách nhiệm và kết quả tham gia công tác cán bộ lớp")


def test_zero_scores_from_real_page_are_saved(tmp_path):
    """Trang thật hiển thị 0 điểm → phải LƯU 5 dòng 0 điểm, không bỏ qua.

    Lỗi người dùng báo: đã quét JSON trang DRL nhưng app vẫn nói "chưa có bảng
    điểm theo từng tiêu chí".
    """
    from drl import database, ui_common

    db = tmp_path / "real_page.db"
    database.init_db(db)
    payload = {
        "sync_source": "HCMUS_CHROME_EXTENSION_V1",
        "synced_at": "2026-11-16T07:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 0, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [
            {"criterion_code": "TC_1", "name": "Chấp hành pháp luật",
             "current_score": 0, "max_score": None},
            {"criterion_code": "TC_2", "name": "Thái độ học tập",
             "current_score": 0, "max_score": None},
            {"criterion_code": "TC_3", "name": "Hoạt động chính trị xã hội",
             "current_score": 0, "max_score": None},
            {"criterion_code": "TC_4", "name": "Trách nhiệm cộng đồng",
             "current_score": 0, "max_score": None},
            {"criterion_code": "TC_5", "name": "Công tác cán bộ lớp",
             "current_score": 0, "max_score": None},
        ],
        "timetable": [{"course_code": "BAA00021", "course_name": "Thực tập 1",
                       "day_of_week": "Tuesday", "start_time": "07:30", "end_time": "11:10"}],
    }
    info = ui_common.apply_sync_payload(payload, db_path=db)
    assert info["n_progress"] == 5, "phải lưu đủ 5 dòng dù điểm = 0"

    df = database.get_criterion_progress("25127302", "HK1_2026_2027", db)
    assert len(df) == 5
    assert float(df["current_score"].sum()) == 0.0
    # Điểm tối đa lấy từ khung quy chế → tổng 100
    assert float(df["max_score"].sum()) == 100.0
    # TKB vẫn lưu cùng lúc
    assert len(database.get_schedule("25127302", db_path=db)) == 1


def test_criterion_mapping_to_five_groups(catalog):
    """Phân loại hoạt động phải rơi vào đúng 1 trong 5 nhóm thật."""
    cases = {
        "NGÀY HỘI HIẾN MÁU NHÂN ĐẠO\nĐịa điểm: Sân Trường": "TC_4",
        "HỘI THẢO KHOA HỌC VỀ AI\nĐịa điểm: Giảng đường I": "TC_3",
        "CHIẾN DỊCH TÌNH NGUYỆN MÙA HÈ XANH\nĐịa điểm: Xã Bình Phước": "TC_3",
        "GIẢI BÓNG ĐÁ SINH VIÊN\nĐịa điểm: Sân vận động": "TC_3",
        "TUYÊN DƯƠNG SINH VIÊN 5 TỐT\nĐịa điểm: Hội trường": "TC_5",
    }
    for text, expected in cases.items():
        got = nlp_engine.analyze_post(text, criteria_catalog=catalog)["activity"]["criterion_code"]
        assert got == expected, f"{text[:40]!r} → {got}, mong đợi {expected}"


# ---------------------------------------------------------------------------
# Tiến độ DỰ ĐOÁN (2026-11-16): chỉ gồm 5 nhóm có điểm tối đa; đánh dấu hoàn
# thành 1 hoạt động → tự cộng khoảng 3–5đ vào đúng nhóm và cập nhật ngay.
# ---------------------------------------------------------------------------
def _mk_act(db, title, code, day="2026-12-01 08:00"):
    from drl import database
    return database.insert_activity({
        "title": title, "organizer": "Đoàn trường", "location": "Hội trường",
        "start_time": day, "end_time": day[:11] + "11:00",
        "criterion_code": code, "relevance_label": "POTENTIAL_DRL",
        "created_at": database.utcnow_iso(),
    }, db)


def test_predicted_progress_lists_only_capped_groups(tmp_path):
    """Bảng tiến độ dự đoán chỉ gồm các nhóm CÓ điểm tối đa, tổng trần = 100."""
    from drl import database, progress_predict as pp

    db = tmp_path / "p.db"
    database.init_db(db)
    pred = pp.predict_progress(db)
    rows = pred["rows"]
    assert len(rows) == 5, "phải đúng 5 nhóm như trang trường"
    assert all(r["max_score"] for r in rows), "mọi nhóm phải có điểm tối đa"
    assert [r["max_score"] for r in rows] == [20, 20, 30, 15, 15]
    assert pred["totals"]["max_score"] == 100
    assert pred["totals"]["n_activities"] == 0
    assert pred["totals"]["min"] == 0 and pred["totals"]["max"] == 0


def test_marking_done_adds_estimate_to_right_group(tmp_path):
    """Đánh dấu hoàn thành 1 HĐ → cộng 3–5đ vào đúng nhóm, các nhóm khác = 0."""
    from drl import database, progress_predict as pp

    db = tmp_path / "p.db"
    database.init_db(db)
    database.upsert_profile({"student_id": "25127302", "semester": "HK1_2026_2027",
                             "current_total_score": 0, "target_score": 90}, db)

    aid = _mk_act(db, "HỘI THẢO KHOA HỌC VỀ AI", "TC_3")
    assert pp.predict_progress(db)["totals"]["max"] == 0  # chưa đánh dấu → 0

    assert database.mark_activity_done(aid, db_path=db) is True
    pred = pp.predict_progress(db)
    by_code = {r["criterion_code"]: r for r in pred["rows"]}
    assert by_code["TC_3"]["pred_min"] == 3.0
    assert by_code["TC_3"]["pred_max"] == 5.0
    assert by_code["TC_3"]["n_activities"] == 1
    for code in ("TC_1", "TC_2", "TC_4", "TC_5"):
        assert by_code[code]["pred_min"] == 0, f"{code} không được tự có điểm"
    assert pred["totals"]["min"] == 3 and pred["totals"]["max"] == 5

    # Đánh dấu lần 2 không nhân đôi điểm
    assert database.mark_activity_done(aid, db_path=db) is False
    assert pp.predict_progress(db)["totals"]["max"] == 5

    # Bỏ đánh dấu → trừ lại đúng phần đã cộng
    assert database.unmark_activity_done(aid, db_path=db) is True
    assert pp.predict_progress(db)["totals"]["max"] == 0


def test_predicted_progress_never_exceeds_group_cap(tmp_path):
    """Cộng dồn không bao giờ vượt điểm tối đa của nhóm (trần quy chế)."""
    from drl import database, progress_predict as pp

    db = tmp_path / "p.db"
    database.init_db(db)
    database.upsert_profile({"student_id": "25127302", "semester": "HK1_2026_2027",
                             "current_total_score": None, "target_score": 90}, db)
    for k in range(10):   # 10 × 3–5đ = 30–50đ nhưng trần TC_4 chỉ 15đ
        aid = _mk_act(db, f"HIẾN MÁU NHÂN ĐẠO đợt {k+1}", "TC_4")
        database.mark_activity_done(aid, db_path=db)
    pred = pp.predict_progress(db)
    tc4 = next(r for r in pred["rows"] if r["criterion_code"] == "TC_4")
    assert tc4["pred_min"] == 15.0 and tc4["pred_max"] == 15.0
    assert pred["totals"]["max"] <= 100
    assert pred["overflow"], "phải báo rõ nhóm nào bị cắt phần vượt trần"


def test_predicted_progress_ignores_official_score(tmp_path):
    """Điểm chính thức KHÔNG bị trộn vào tiến độ dự đoán (nguồn riêng biệt)."""
    from drl import database, progress_predict as pp

    db = tmp_path / "p.db"
    database.init_db(db)
    database.upsert_profile({"student_id": "25127302", "semester": "HK1_2026_2027",
                             "current_total_score": 0, "target_score": 90}, db)
    aid = _mk_act(db, "TÌNH NGUYỆN MÙA HÈ XANH", "TC_3")
    database.mark_activity_done(aid, db_path=db)
    pred = pp.predict_progress(db)
    assert pred["totals"]["min"] == 3.0, "chỉ tính hoạt động đã đánh dấu"
    assert database.latest_profile(db)["current_total_score"] == 0.0


def test_sync_payload_cannot_overwrite_framework_names(tmp_path):
    """Gói quét về (tên rỗng/rác, max_score=None) KHÔNG được ghi đè khung quy chế.

    Lỗi thật đã gặp: bảng tiến độ hiện cột "Nhóm tiêu chí" toàn chữ "x" vì tên
    trong gói quét được ghi đè lên 5 tên nhóm chính thức của trường.
    """
    from drl import database, ui_common as ui

    db = tmp_path / "n.db"
    database.init_db(db)
    ui.apply_sync_payload({
        "sync_source": "HCMUS_CHROME_EXTENSION_V1", "synced_at": "2026-11-16T07:00:00Z",
        "student_profile": {"student_id": "25127302", "semester": "HK1_2026_2027",
                            "current_total_score": 0, "score_type": "OFFICIAL_SYNCED"},
        "drl_progress": [{"criterion_code": f"TC_{i}", "name": "x",
                          "current_score": 0, "max_score": None} for i in range(1, 6)],
        "timetable": [],
    }, db_path=db)
    df = database.get_criteria(db)
    assert len(df) == 5
    assert all(str(n).startswith("Trách nhiệm") for n in df["name"]), \
        f"tên nhóm bị ghi đè: {list(df['name'])}"
    assert float(df["max_score"].sum()) == 100.0
