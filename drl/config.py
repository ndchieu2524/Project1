# -*- coding: utf-8 -*-
"""
drl/config.py — CẤU HÌNH TRUNG TÂM của Smart DRL Assistant
===========================================================
Chủ trì: Thành viên 1 (Kiến trúc hệ thống, Database & Tích hợp)

Nội dung:
  1. Metadata ứng dụng & đường dẫn dùng chung
  2. Cấu hình Database (SQLite)
  3. Nguồn dữ liệu (Sources) & từ khóa nhận diện/loại trừ hoạt động — dùng chung cho Crawler (TV2)
  4. Bộ quy chế 5 Điều (+ nội dung khuyến khích) ĐRL HCMUS — CHUẨN HÓA
     Nguồn: Quyết định số 1124/QĐ-KHTN-CTSV ngày 22/8/2016 của Hiệu trưởng
     Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM (Quy chế đánh giá kết quả rèn luyện
     sinh viên hệ chính quy). Điểm tối đa cả học kỳ: 100 điểm.
  5. Thang phân loại kết quả rèn luyện
  6. Cấu hình lộ trình tối ưu (TV5 dùng)

Mọi module khác (crawler, nlp_engine, pathway, ui_tab*) import từ file này,
KHÔNG hard-code lại hằng số ở nơi khác.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. METADATA & ĐƯỜNG DẪN
# ---------------------------------------------------------------------------
APP_NAME = "Smart DRL Assistant"
APP_SHORT_NAME = "SmartDRL"
APP_VERSION = "0.1.0"
APP_AUTHOR = "Nhóm 5 — HCMUS"
APP_DESCRIPTION = (
    "Hệ thống hỗ trợ quản lý & tối ưu lộ trình Điểm rèn luyện (ĐRL) "
    "sinh viên Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM"
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DRL_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.environ.get("DRL_DB_PATH", DATA_DIR / "smart_drl.db"))

# ---------------------------------------------------------------------------
# 2. DATABASE
# ---------------------------------------------------------------------------
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_CONNECT_ARGS = {"timeout": SQLITE_TIMEOUT_SECONDS, "check_same_thread": False}

# ---------------------------------------------------------------------------
# 3. NGUỒN DỮ LIỆU & TỪ KHÓA (dùng chung cho TV2 — Crawler)
# ---------------------------------------------------------------------------
# Adapter tương ứng drl/crawler.py. `url` là trang gốc; TV2 xác nhận lại endpoint thật.
CRAWL_SOURCES = [
    {
        "code": "ctsv_api",
        "name": "Phòng CTSV HCMUS — Thông báo",
        "type": "API/HTML",
        "adapter": "ctsv_api",
        "url": "https://ctsv.hcmus.edu.vn/",   # TODO(TV2): xác nhận endpoint thật
        "is_active": True,
    },
    {
        "code": "hcmus_events",
        "name": "HCMUS — Lịch sự kiện Trường",
        "type": "HTML",
        "adapter": "hcmus_events",
        "url": "https://www.hcmus.edu.vn/",     # TODO(TV2): xác nhận đường dẫn /su-kien
        "is_active": True,
    },
    {
        "code": "hcmus_posts",
        "name": "HCMUS — Tin tức Trường",
        "type": "HTML",
        "adapter": "hcmus_posts",
        "url": "https://www.hcmus.edu.vn/",     # TODO(TV2): xác nhận đường dẫn /tin-tuc
        "is_active": True,
    },
    {
        "code": "fit_news",
        "name": "Khoa CNTT (FIT) — Tin tức & Sự kiện",
        "type": "HTML",
        "adapter": "fit_news",
        "url": "https://fit.hcmus.edu.vn/",     # TODO(TV2): xác nhận endpoint thật
        "is_active": True,
    },
    {
        "code": "fb_rss",
        "name": "Fanpage Facebook HCMUS (qua RSS)",
        "type": "RSS",
        "adapter": "fb_rss",
        "url": "https://rsshub.app/facebook/page/HCMUSOfficial",  # TODO(TV2): chọn instance RSSHub
        "is_active": True,
    },
]

# Từ khóa NHẬN DIỆN bài viết có nội dung hoạt động ĐRL (câu lạc bộ, hiến máu, tình nguyện...)
ACTIVITY_KEYWORDS = [
    "hoạt động", "sự kiện", "tham gia", "đăng ký", "tình nguyện", "hiến máu",
    "hội thảo", "tọa đàm", "chuyên đề", "tập huấn", "sinh hoạt", "cuộc thi",
    "văn nghệ", "thể thao", "mùa hè xanh", "tiếp sức mùa thi", "chiến dịch",
    "câu lạc bộ", "CLB", "ngày hội", "chiến sĩ", "thanh niên", "cộng đồng",
    "workshop", "seminar", "hackathon", "hội thao", "giải",
]

# Từ khóa LOẠI TRỪ — tin hành chính/lịch học thuần túy, KHÔNG phải hoạt động ĐRL
EXCLUDE_KEYWORDS = [
    "lịch thi", "thời khóa biểu", "đăng ký học phần", "đăng ký môn học",
    "điểm học phần", "điểm thi", "cảnh báo học vụ", "học phí", "lệ phí",
    "thông báo nghỉ lễ", "lịch nghỉ", "khai giảng", "tốt nghiệp (thủ tục)",
    "luận văn (thủ tục)", "bảo vệ luận văn (lịch)", "sao y", "xác nhận sinh viên",
    "cấp bảng điểm", "hoàn thiện hồ sơ", "lịch bảo vệ",
]

# ---------------------------------------------------------------------------
# 4. BỘ QUY CHẾ 5 ĐIỀU ĐRL HCMUS (CHUẨN HÓA)
#    Quyết định 1124/QĐ-KHTN-CTSV ngày 22/8/2016 — Thang điểm 100
#
#    Cấu trúc: DRL_COMPONENTS = danh sách 6 nhóm (Điều 4 → Điều 9).
#    Mỗi item con: code, name, points (điểm chuẩn), per_semester_cap (giới hạn
#    số lần/điểm mỗi học kỳ, None = không giới hạn), note.
# ---------------------------------------------------------------------------
DRL_REGULATION_SOURCE = (
    "Quyết định 1124/QĐ-KHTN-CTSV ngày 22/8/2016 của Hiệu trưởng "
    "Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM"
)
DRL_MAX_TOTAL = 100

DRL_COMPONENTS = [
    {
        "code": "DIEU_4",
        "article": 4,
        "name": "Ý thức tham gia học tập",
        "max_points": 20,
        "items": [
            {"code": "4.1.1", "name": "Chấp hành quy chế học vụ (học, kiểm tra, thi) — không vi phạm",
             "points": 5, "per_semester_cap": None, "note": "Vi phạm: -10đ/lần"},
            {"code": "4.1.2", "name": "Kết quả học tập ĐTB tích lũy học kỳ ≥ 8.0",
             "points": 10, "per_semester_cap": None, "note": "5.0–<6.5: +5đ; 6.5–<8.0: +7đ; 8.0–10: +10đ"},
            {"code": "4.1.3", "name": "Tăng ĐTB so với học kỳ trước ≥ 0.8",
             "points": 10, "per_semester_cap": None,
             "note": ">0–<0.2:+2đ; 0.2–<0.4:+4đ; 0.4–<0.6:+6đ; 0.6–<0.8:+8đ; ≥0.8:+10đ"},
            {"code": "4.3.1", "name": "NCKH / S-Ideas / chương trình tương tự (+5đ/chương trình)",
             "points": 5, "per_semester_cap": None,
             "note": "Giải trường: I +10/II +9/III +8/KK +7; giải cấp thành/ĐHQG trở lên +15"},
            {"code": "4.3.2", "name": "Cuộc thi học thuật cấp Đoàn/đơn vị — tham gia vòng loại",
             "points": 5, "per_semester_cap": None,
             "note": "Giải I +10/II +9/III +8/KK +7; cấp thành trở lên +15; BTVC +10; CTV +5"},
            {"code": "4.3.3", "name": "Sinh hoạt thường xuyên tại CLB học thuật / phòng thí nghiệm",
             "points": 5, "per_semester_cap": 5, "note": "+5đ/học kỳ"},
            {"code": "4.3.4", "name": "Sinh hoạt, hội thảo, chuyên đề NCKH do đơn vị trong Trường tổ chức",
             "points": 5, "per_semester_cap": 10, "note": "+5đ/hoạt động, tối đa 2 hoạt động/học kỳ"},
            {"code": "4.3.5", "name": "Tác giả bài báo khoa học đăng kỷ yếu/tạp chí (có phản biện)",
             "points": 10, "per_semester_cap": None, "note": "+10đ/bài báo"},
        ],
    },
    {
        "code": "DIEU_5",
        "article": 5,
        "name": "Ý thức chấp hành nội quy, quy chế, quy định trong Nhà trường",
        "max_points": 25,
        "items": [
            {"code": "5.2.1", "name": "Chấp hành nội quy, quy chế — không vi phạm",
             "points": 15, "per_semester_cap": None,
             "note": "Kỷ luật khiển trách: -5đ/lần; cảnh cáo trở lên: -15đ/lần"},
            {"code": "5.2.2", "name": "Tuyên truyền/hoạt động nâng cao ý thức chấp hành nội quy, bảo vệ của công, tiết kiệm",
             "points": 5, "per_semester_cap": None, "note": "+5đ/lần; khen thưởng cộng thêm +5đ"},
            {"code": "5.2.3", "name": "Bảo vệ an ninh trật tự, an toàn xã hội trong trường / Đội VMHĐ",
             "points": 5, "per_semester_cap": None,
             "note": "+5đ; khen thưởng +10đ; đội trưởng VMHĐ có giấy khen +10đ; thành viên VMHĐ +5đ"},
            {"code": "5.2.4", "name": "Tham gia hoạt động lấy ý kiến người học về môn học, khóa học",
             "points": 10, "per_semester_cap": 10, "note": "Tối đa +10đ/học kỳ"},
        ],
    },
    {
        "code": "DIEU_6",
        "article": 6,
        "name": "Ý thức tham gia các hoạt động chính trị, xã hội, văn hóa, văn nghệ, thể thao, phòng chống tội phạm và tệ nạn xã hội",
        "max_points": 20,
        "items": [
            {"code": "6.3.1", "name": "Cuộc thi CT-XH-VH-VN-TT cấp Trường trở lên — tham gia vòng loại",
             "points": 3, "per_semester_cap": None,
             "note": "Bán kết +5; giải I +10/II +9/III +8/KK +7; BTVC +5; CTV +3"},
            {"code": "6.3.2", "name": "Được chứng nhận danh hiệu Thanh niên khỏe",
             "points": 3, "per_semester_cap": None, "note": "+3đ/lần"},
            {"code": "6.3.3", "name": "Hoạt động giáo dục CT-XH-VH-VN-TT do Trường/Khoa/KTX/Đoàn-Hội (cấp Khoa trở lên) tổ chức",
             "points": 5, "per_semester_cap": 10, "note": "+5đ/lần, tối đa 2 lần/học kỳ"},
            {"code": "6.3.4", "name": "Tình nguyện quy mô lớn (Mùa hè xanh, Tiếp sức mùa thi...) hiệu quả",
             "points": 7, "per_semester_cap": None,
             "note": "Đội trưởng xuất sắc/khen thưởng +10; chiến sĩ giỏi +9"},
            {"code": "6.3.5", "name": "Hoạt động / huy động lực lượng từ cấp Khoa trở lên",
             "points": 3, "per_semester_cap": 12, "note": "+3đ/lần, tối đa 4 lần/học kỳ"},
            {"code": "6.3.6", "name": "Thành viên các câu lạc bộ sở thích",
             "points": 5, "per_semester_cap": 5, "note": "+5đ/học kỳ"},
        ],
    },
    {
        "code": "DIEU_7",
        "article": 7,
        "name": "Ý thức công dân trong quan hệ cộng đồng",
        "max_points": 25,
        "items": [
            {"code": "7.4.1", "name": "Hiến máu nhân đạo",
             "points": 5, "per_semester_cap": None, "note": "+5đ/lần"},
            {"code": "7.4.2", "name": "Tham gia hoạt động tình nguyện",
             "points": 5, "per_semester_cap": None,
             "note": "+5đ/lần; thành viên tích cực BTVC +2đ/lần"},
            {"code": "7.4.3", "name": "Hoạt động cộng đồng tại địa phương / tổ chức xã hội (có giấy chứng nhận)",
             "points": 5, "per_semester_cap": None,
             "note": "+5đ/lần; tuyên dương (giấy khen) +5đ"},
            {"code": "7.4.4", "name": "Hoạt động xã hội/cộng đồng do Đoàn-Hội-Khoa (cấp khoa trở lên) tổ chức",
             "points": 5, "per_semester_cap": 10, "note": "+5đ/lần, tối đa 2 lần/học kỳ"},
            {"code": "7.4.5", "name": "Bảo vệ an ninh trật tự, an toàn xã hội nơi cư trú",
             "points": 5, "per_semester_cap": None, "note": "+5đ; khen thưởng cộng thêm +10đ"},
            {"code": "7.4.6", "name": "Chấp hành chủ trương Đảng, chính sách pháp luật Nhà nước — không vi phạm",
             "points": 10, "per_semester_cap": None, "note": "Vi phạm: -15đ"},
        ],
    },
    {
        "code": "DIEU_8",
        "article": 8,
        "name": "Ý thức và kết quả tham gia công tác cán bộ lớp, các đoàn thể, tổ chức khác trong Nhà trường",
        "max_points": 10,
        "items": [
            {"code": "8.5.1a", "name": "Ban cán sự lớp / cán bộ Đoàn-Hội — hoàn thành xuất sắc nhiệm vụ (có giấy khen)",
             "points": 5, "per_semester_cap": None, "note": "HT tốt +4đ; HT +2đ; không HT: -2đ"},
            {"code": "8.5.1b", "name": "Ban cán sự lớp / cán bộ Đoàn-Hội — hoàn thành tốt nhiệm vụ",
             "points": 4, "per_semester_cap": None, "note": ""},
            {"code": "8.5.2a", "name": "Sinh viên — tham gia đầy đủ sinh hoạt lớp, chi đoàn, chi hội",
             "points": 5, "per_semester_cap": None, "note": "Bình chọn tại lớp, phiếu kín"},
            {"code": "8.5.2b", "name": "Sinh viên là nhân tố tích cực trong lớp",
             "points": 5, "per_semester_cap": None, "note": "Trừ đối tượng 5.1; bình chọn tại lớp"},
            {"code": "8.5.2c", "name": "Tham gia mô hình bạn giúp bạn",
             "points": 1, "per_semester_cap": None, "note": "+1đ"},
        ],
    },
    {
        # Điều 9 — nội dung khuyến khích cộng thêm (không tính vào 5 Điều gốc nhưng cộng dồn vào tổng, tối đa 100)
        "code": "DIEU_9",
        "article": 9,
        "name": "Các nội dung khuyến khích cộng thêm",
        "max_points": 20,
        "items": [
            {"code": "9.6.1a", "name": "Khen thưởng thành tích đặc biệt cấp Trường",
             "points": 5, "per_semester_cap": None, "note": "+5đ"},
            {"code": "9.6.1b", "name": "Khen thưởng thành tích đặc biệt cấp thành phố / ĐHQG-HCM trở lên",
             "points": 10, "per_semester_cap": None, "note": "+10đ"},
            {"code": "9.6.2", "name": "Sinh viên mồ côi cả cha lẫn mẹ (có giấy chứng nhận)",
             "points": 20, "per_semester_cap": 20, "note": "+20đ/học kỳ"},
            {"code": "9.6.3", "name": "Sinh viên có hoàn cảnh gia đình đặc biệt khó khăn (hộ nghèo/cận nghèo)",
             "points": 20, "per_semester_cap": 20, "note": "+20đ/học kỳ"},
        ],
    },
]

# Mã tiêu chí hợp lệ — TV4 (NLP) dùng để kiểm tra đầu ra trích xuất
VALID_CRITERION_CODES = {item["code"] for comp in DRL_COMPONENTS for item in comp["items"]}
COMPONENT_CODES = [comp["code"] for comp in DRL_COMPONENTS]
COMPONENT_BY_CODE = {comp["code"]: comp for comp in DRL_COMPONENTS}
ITEM_BY_CODE = {item["code"]: item for comp in DRL_COMPONENTS for item in comp["items"]}


def component_max_points() -> dict[str, int]:
    """Trả về {mã nhóm: điểm tối đa}, ví dụ {'DIEU_4': 20, ...}."""
    return {comp["code"]: comp["max_points"] for comp in DRL_COMPONENTS}


def five_discipline_max() -> int:
    """Tổng điểm tối đa của 5 Điều gốc (không tính nội dung khuyến khích)."""
    return sum(comp["max_points"] for comp in DRL_COMPONENTS if comp["code"] != "DIEU_9")


def regulation_as_json() -> str:
    """Xuất toàn bộ quy chế ra JSON (phục vụ seed/debug/UI)."""
    return json.dumps(DRL_COMPONENTS, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 5. THANG PHÂN LOẠI KẾT QUẢ RÈN LUYỆN (Điều 11 — Quyết định 1124/QĐ-KHTN-CTSV)
# ---------------------------------------------------------------------------
# (điểm_tối_thiểu, loại)
RATING_SCALE = [
    (90, "Xuất sắc"),
    (80, "Tốt"),
    (65, "Khá"),
    (50, "Trung bình"),
    (35, "Yếu"),
    (0, "Kém"),
]


def classify_rating(score: float) -> str:
    """Xếp loại ĐRL theo thang điểm 100. Điểm âm vẫn xếp 'Kém'."""
    for threshold, label in RATING_SCALE:
        if score >= threshold:
            return label
    return "Kém"


def cap_score(score: float) -> float:
    """Điểm ĐRL học kỳ tối đa 100 điểm."""
    return max(0.0, min(float(score), float(DRL_MAX_TOTAL)))


# ---------------------------------------------------------------------------
# 6. CẤU HÌNH LỘ TRÌNH TỐI ƯU (TV5 dùng)
# ---------------------------------------------------------------------------
PATHWAY_DEFAULT_TARGET = 90          # Mặc định gợi ý lộ trình hướng đến Xuất sắc
PATHWAY_TARGET_OPTIONS = [100, 90, 80, 65, 50]  # Các mức gợi ý trên UI
PATHWAY_MAX_SUGGESTIONS = 8          # Số hoạt động tối đa gợi ý mỗi lần
