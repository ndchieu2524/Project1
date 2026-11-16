# -*- coding: utf-8 -*-
"""
drl/seed_data.py — DỮ LIỆU MẪU BAN ĐẦU cho Smart DRL Assistant
==============================================================
Chủ trì: Thành viên 1

Nạp:
  1. Sources   — 5 nguồn từ config.CRAWL_SOURCES (CTSV, HCMUS Events, HCMUS Posts, FIT News, FB RSS)
  2. Activities— hoạt động ĐRL mẫu (bám sát Quyết định 1124/QĐ-KHTN-CTSV) cho demo & test
  3. Student profile mẫu + 3 tiết học mẫu (để pathway/UI chạy được ngay)

Chạy:  python -m drl.seed_data
        python -m drl.seed_data --reset   (xóa sạch dữ liệu cũ trong các bảng rồi seed lại)
Idempotent: chạy lại nhiều lần KHÔNG tạo bản ghi trùng (nhờ content_hash).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from drl.config import CRAWL_SOURCES
from drl import database as db

# ---------------------------------------------------------------------------
# 1. NGUỒN (lấy từ config — không khai báo lại ở đây)
# ---------------------------------------------------------------------------

def seed_sources(db_path: Path | str | None = None) -> list[int]:
    ids = []
    for src in CRAWL_SOURCES:
        ids.append(db.upsert_source(src, db_path))
    return ids


# ---------------------------------------------------------------------------
# 2. HOẠT ĐỘNG ĐRL MẪU (thời điểm: học kỳ 1, năm học 2026–2027)
#    criterion_code bám config.VALID_CRITERION_CODES; points theo quy chế.
# ---------------------------------------------------------------------------

SAMPLE_ACTIVITIES = [
    # --- Điều 4: Ý thức tham gia học tập ---
    {"title": "Hội thảo Khoa học Sinh viên Khoa CNTT 2026",
     "description": "Hội thảo báo cáo kết quả NCKH sinh viên, trải nghiệm poster và demo sản phẩm.",
     "organizer": "Khoa CNTT — FIT", "location": "Hội trường A, Trường ĐH KHTN",
     "start_time": "2026-11-20 08:30", "end_time": "2026-11-20 11:30",
     "registration_deadline": "2026-11-18 17:00",
     "criterion_code": "4.3.4", "drl_points": 5,
     "url": "https://fit.hcmus.edu.vn/"},
    {"title": "Cuộc thi Lập trình Olympic Sinh viên Khoa học Tự nhiên 2026",
     "description": "Cuộc thi học thuật lập trình thường niên cho sinh viên Trường ĐH KHTN.",
     "organizer": "Đoàn TN Khoa CNTT", "location": "Phòng Lab 4, Cơ sở Nguyễn Văn Cừ",
     "start_time": "2026-12-05 08:00", "end_time": "2026-12-05 12:00",
     "registration_deadline": "2026-11-30 23:59",
     "criterion_code": "4.3.2", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Chương trình NCKH Sinh viên S-Ideas 2026 (đăng ký ý tưởng)",
     "description": "Đăng ký thực hiện đề tài NCKH theo chương trình S-Ideas của ĐHQG-HCM.",
     "organizer": "Phòng CTSV & Phòng QLKH", "location": "Văn phòng Phòng CTSV",
     "start_time": "2026-11-30 09:00", "end_time": "2026-11-30 16:00",
     "registration_deadline": "2026-11-27 17:00",
     "criterion_code": "4.3.1", "drl_points": 5,
     "url": "https://ctsv.hcmus.edu.vn/"},
    {"title": "Sinh hoạt CLB Học thuật Tin học — buổi tháng 11",
     "description": "Sinh hoạt định kỳ: chia sẻ kinh nghiệm học phần Cấu trúc dữ liệu & Giải thuật.",
     "organizer": "CLB Học thuật Tin học", "location": "Phòng B.408",
     "start_time": "2026-11-18 18:00", "end_time": "2026-11-18 20:00",
     "registration_deadline": None,
     "criterion_code": "4.3.3", "drl_points": 5,
     "url": "https://fit.hcmus.edu.vn/"},

    # --- Điều 5: Nội quy, quy chế ---
    {"title": "Hoạt động lấy ý kiến người học về môn học — Học kỳ 1 năm 2026–2027",
     "description": "Sinh viên đánh giá chất lượng môn học qua hệ thống khảo sát trực tuyến.",
     "organizer": "Phòng CTSV", "location": "Trực tuyến (cổng CTĐB)",
     "start_time": "2026-12-08 08:00", "end_time": "2026-12-19 23:59",
     "registration_deadline": "2026-12-19 23:59",
     "criterion_code": "5.2.4", "drl_points": 10,
     "url": "https://ctsv.hcmus.edu.vn/"},
    {"title": "Sinh hoạt công dân – sinh viên đầu năm học 2026–2027",
     "description": "Buổi sinh hoạt công dân – sinh viên bắt buộc đầu năm. KHÔNG tham gia sẽ bị 0 điểm toàn bộ Điều 5.",
     "organizer": "Phòng CTSV & Đoàn Trường", "location": "Hội trường B, Trường ĐH KHTN",
     "start_time": "2026-11-17 07:30", "end_time": "2026-11-17 11:30",
     "registration_deadline": None,
     "criterion_code": "5.2.1", "drl_points": 0,
     "url": "https://ctsv.hcmus.edu.vn/"},

    # --- Điều 6: Chính trị, xã hội, VH-VN-TT ---
    {"title": "Ngày hội Văn hóa — Văn nghệ Chào mừng Ngày Nhà giáo Việt Nam 20/11",
     "description": "Chương trình giao lưu, văn nghệ chào mừng 20/11 với các tiết mục của sinh viên và cựu sinh viên.",
     "organizer": "Đoàn TN Trường & Hội SV Trường", "location": "Sân trường, Cơ sở Nguyễn Văn Cừ",
     "start_time": "2026-11-21 19:00", "end_time": "2026-11-21 22:00",
     "registration_deadline": "2026-11-19 17:00",
     "criterion_code": "6.3.3", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Giải Bóng đá Sinh viên HCMUS Cup 2026",
     "description": "Giải bóng đá phong trào toàn trường, thi đấu vòng bảng và chung kết.",
     "organizer": "Hội SV Trường — Ban Thể thao", "location": "Sân bóng Cơ sở Nguyễn Văn Cừ",
     "start_time": "2026-12-12 07:00", "end_time": "2026-12-12 17:00",
     "registration_deadline": "2026-12-01 17:00",
     "criterion_code": "6.3.1", "drl_points": 3,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Tập huấn An toàn giao thông & Phòng chống tệ nạn xã hội",
     "description": "Tuyên truyền pháp luật an toàn giao thông và phòng chống ma túy, cờ bạc.",
     "organizer": "Đoàn TN Khoa CNTT", "location": "Hội trường C, Trường ĐH KHTN",
     "start_time": "2026-11-28 08:00", "end_time": "2026-11-28 10:30",
     "registration_deadline": "2026-11-26 17:00",
     "criterion_code": "6.3.3", "drl_points": 5,
     "url": "https://fit.hcmus.edu.vn/"},
    {"title": "Hoạt động huy động lực lượng: Ngày Chủ nhật xanh — dọn dẹp khuôn viên Khoa",
     "description": "Ra quân dọn dẹp vệ sinh khuôn viên, trồng cây xanh gây quỹ học bổng.",
     "organizer": "Đoàn TN Khoa CNTT", "location": "Khuôn viên Khoa CNTT",
     "start_time": "2026-11-22 07:30", "end_time": "2026-11-22 11:00",
     "registration_deadline": "2026-11-20 17:00",
     "criterion_code": "6.3.5", "drl_points": 3,
     "url": "https://fit.hcmus.edu.vn/"},
    {"title": "CLB Tiếng Anh HCMUS — English Speaking Club buổi 12",
     "description": "Sinh hoạt CLB: chủ đề 'Study Abroad Opportunities', có khách mời từ cựu sinh viên.",
     "organizer": "CLB Tiếng Anh HCMUS", "location": "Phòng C.205",
     "start_time": "2026-11-19 18:30", "end_time": "2026-11-19 20:30",
     "registration_deadline": None,
     "criterion_code": "6.3.6", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Chiến dịch Tình nguyện Mùa hè xanh 2026 — tổng kết đợt 3",
     "description": "Tổng kết và trao khen thưởng các đội Mùa hè xanh đợt 3 (Tiếp sức mùa thi).",
     "organizer": "Đoàn TN Trường", "location": "Hội trường B, Trường ĐH KHTN",
     "start_time": "2026-12-15 19:00", "end_time": "2026-12-15 21:30",
     "registration_deadline": None,
     "criterion_code": "6.3.4", "drl_points": 7,
     "url": "https://www.hcmus.edu.vn/"},

    # --- Điều 7: Quan hệ cộng đồng ---
    {"title": "Hiến máu tình nguyện Đợt 6 năm 2026 — 'Giọt hồng KHTN'",
     "description": "Ngày hội hiến máu nhân đạo do Đoàn Trường phối hợp Hội Chữ thập đỏ TP.HCM tổ chức.",
     "organizer": "Đoàn TN Trường & Hội Chữ thập đỏ", "location": "Hội trường A, Trường ĐH KHTN",
     "start_time": "2026-11-25 07:30", "end_time": "2026-11-25 16:30",
     "registration_deadline": "2026-11-24 17:00",
     "criterion_code": "7.4.1", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Hoạt động tình nguyện: Hỗ trợ thí sinh nhập học Học kỳ 1",
     "description": "Tiếp sức mùa thi — hướng dẫn tân sinh viên làm thủ tục nhập học tại sảnh Khoa.",
     "organizer": "Hội SV Khoa CNTT", "location": "Sảnh Khoa CNTT, Cơ sở Nguyễn Văn Cừ",
     "start_time": "2026-12-01 07:30", "end_time": "2026-12-01 11:30",
     "registration_deadline": "2026-11-29 17:00",
     "criterion_code": "7.4.2", "drl_points": 5,
     "url": "https://fit.hcmus.edu.vn/"},
    {"title": "Hoạt động cộng đồng: Chủ nhật vì môi trường — Phường 4, Quận 5",
     "description": "Ra quân thu gom rác, vệ sinh tuyến đường thanh niên tự quản.",
     "organizer": "Đoàn TN Trường & UBND Phường 4, Quận 5", "location": "Phường 4, Quận 5",
     "start_time": "2026-12-06 06:30", "end_time": "2026-12-06 10:30",
     "registration_deadline": "2026-12-04 17:00",
     "criterion_code": "7.4.3", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
    {"title": "Hoạt động bảo vệ ANTT nơi cư trú — Tổ tuần tra khu phố",
     "description": "Tham gia tổ tuần tra an ninh khu phố nơi cư trú theo định kỳ.",
     "organizer": "UBND Phường & Ban điều hành khu phố", "location": "Khu dân cư nơi cư trú",
     "start_time": "2026-12-03 19:30", "end_time": "2026-12-03 22:00",
     "registration_deadline": None,
     "criterion_code": "7.4.5", "drl_points": 5,
     "url": "https://ctsv.hcmus.edu.vn/"},

    # --- Điều 8: Cán bộ lớp / đoàn thể ---
    {"title": "Sinh hoạt lớp & chi đoàn CNTT-K2023 định kỳ (tháng 11)",
     "description": "Họp lớp, sơ kết tháng 11, phổ biến kế hoạch Học kỳ 1 và bình bầu sinh viên tích cực.",
     "organizer": "Ban cán sự lớp CNTT-K2023", "location": "Phòng B.301",
     "start_time": "2026-11-26 17:30", "end_time": "2026-11-26 19:30",
     "registration_deadline": None,
     "criterion_code": "8.5.2a", "drl_points": 5,
     "url": "https://fit.hcmus.edu.vn/"},

    # --- Điều 9: Khuyến khích cộng thêm ---
    {"title": "Hội thao Sinh viên Khoa học Tự nhiên 2026 (khen thưởng cấp Trường)",
     "description": "Khen thưởng cho các tập thể/cá nhân đạt thành tích trong Hội thao KHTN 2026.",
     "organizer": "Hội SV Trường & Ban Thể thao", "location": "Sân bóng Cơ sở Nguyễn Văn Cừ",
     "start_time": "2026-12-19 08:00", "end_time": "2026-12-19 17:00",
     "registration_deadline": "2026-12-10 17:00",
     "criterion_code": "9.6.1a", "drl_points": 5,
     "url": "https://www.hcmus.edu.vn/"},
]


def seed_activities(db_path: Path | str | None = None) -> tuple[int, int]:
    """Trả về (số hoạt động mới tạo, số hoạt động đã tồn tại/bỏ qua)."""
    created = skipped = 0
    for item in SAMPLE_ACTIVITIES:
        _, was_created = db.insert_activity(item, db_path)
        if was_created:
            created += 1
        else:
            skipped += 1
    return created, skipped


# ---------------------------------------------------------------------------
# 3. HỒ SƠ SINH VIÊN & THỜI KHÓA BIỂU MẪU (phục vụ demo)
# ---------------------------------------------------------------------------

SAMPLE_PROFILE = {
    "student_id": "22520300",
    "full_name": "Nguyễn Văn An",
    "class_name": "CNTT-K2022",
    "cohort": "K2022",
    "faculty": "Khoa Công nghệ Thông tin",
    "current_semester": "2026-HK1",
    "target_drl": 90,
}

SAMPLE_SCHEDULE = [
    {"course_code": "CSC10105", "course_name": "Cấu trúc dữ liệu & Giải thuật",
     "day_of_week": 2, "period_start": 1, "period_end": 4, "room": "B.403", "semester": "2026-HK1"},
    {"course_code": "CSC10001", "course_name": "Cơ sở dữ liệu",
     "day_of_week": 4, "period_start": 3, "period_end": 6, "room": "B.405", "semester": "2026-HK1"},
    {"course_code": "CSC10009", "course_name": "Mạng máy tính",
     "day_of_week": 6, "period_start": 7, "period_end": 10, "room": "C.102", "semester": "2026-HK1"},
]


def seed_student_profile(db_path: Path | str | None = None) -> None:
    db.save_student_profile(SAMPLE_PROFILE, db_path)


def seed_schedule_sample(db_path: Path | str | None = None) -> int:
    """Chỉ thêm TKB mẫu nếu bảng đang trống (không ghi đè dữ liệu thật của TV3)."""
    if db.list_schedule_events(db_path=db_path):
        return 0
    for event in SAMPLE_SCHEDULE:
        db.add_schedule_event(event, db_path)
    return len(SAMPLE_SCHEDULE)


# ---------------------------------------------------------------------------
# TỔNG HỢP
# ---------------------------------------------------------------------------

def seed_all(db_path: Path | str | None = None) -> None:
    db.init_db(db_path)
    source_ids = seed_sources(db_path)
    print(f"[seed] Sources: {len(source_ids)} nguồn đã sẵn sàng (upsert theo code)")

    created, skipped = seed_activities(db_path)
    print(f"[seed] Activities: tạo mới {created}, bỏ qua (trùng content_hash) {skipped}")

    seed_student_profile(db_path)
    print(f"[seed] Student profile: {SAMPLE_PROFILE['full_name']} ({SAMPLE_PROFILE['student_id']}) — mục tiêu ĐRL {SAMPLE_PROFILE['target_drl']}")

    n_events = seed_schedule_sample(db_path)
    print(f"[seed] Schedule events mẫu: +{n_events} tiết (bảng trống mới thêm)")

    stats = db.get_db_stats(db_path)
    print("[seed] Thống kê DB:", {k: v for k, v in stats.items() if k != "activities_by_component"})
    print("[seed] Phân bố hoạt động theo nhóm:", stats["activities_by_component"])


def reset_db(db_path: Path | str | None = None) -> None:
    """Xóa toàn bộ dữ liệu trong các bảng (giữ cấu trúc) rồi seed lại."""
    with db.get_connection(db_path) as conn:
        for table in ("student_activities", "schedule_events", "activities",
                      "source_posts", "sources", "student_profile"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    print("[seed] Đã xóa sạch dữ liệu cũ.")
    seed_all(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dữ liệu mẫu Smart DRL Assistant")
    parser.add_argument("--reset", action="store_true", help="Xóa toàn bộ dữ liệu cũ rồi seed lại")
    args = parser.parse_args()
    if args.reset:
        reset_db()
    else:
        seed_all()


if __name__ == "__main__":
    main()
