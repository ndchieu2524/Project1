"""Bộ bóc tách thông tin bài đăng OSA HCMUS bằng Regex/Heuristic nội bộ.

Module này CHẠY OFFLINE 100% (không cần API Key) và là "chân lý nền" của hệ thống:

1. Bóc tách 4 nhóm thông tin trọng tâm:
   (1) Thời gian diễn ra & hạn đăng ký          → start_time / end_time / registration_deadline
   (2) Địa điểm / cơ sở / hình thức Online      → location / campus
   (3) Nội dung & đơn vị tổ chức                → title / description / organizer
   (4) Điểm ĐRL kỳ vọng & mã tiêu chí dự kiến   → expected_score / criterion_code
2. Bật cờ ``is_missing_*`` tương ứng khi nhóm thông tin nào KHÔNG trích xuất được.
3. Phân loại 2 bước (xem ``classify_two_step``).
4. Sinh báo cáo JSON đúng Schema 1 (``analyze_post``).

Nguyên tắc chống "bịa":
- Không suy diễn điểm nếu văn bản không nêu; mọi giả định (năm, giờ kết thúc,
  hạn chót 23:59) đều được ghi vào ``assumptions`` để hiển thị minh bạch.
- Mã tiêu chí chỉ được gán khi khớp ngữ cảnh với danh mục DRLCriteria, và luôn
  đi kèm trạng thái NEEDS_HUMAN_REVIEW (nhãn POTENTIAL_DRL) – không tự xác minh.
- Thời gian được ghép theo TỪNG DÒNG văn bản để tránh nhầm "08h30 - 11h30" thành
  ngày tháng hoặc ghép giờ của dòng này sang ngày của dòng khác.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

from . import config

# ---------------------------------------------------------------------------
# Tiện ích chuẩn hoá văn bản
# ---------------------------------------------------------------------------
_DIACRITIC_MAP = str.maketrans("đĐ", "dD")


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp từ khoá bền vững (giữ nguyên ĐỘ DÀI bằng
    cách thay thế ký tự dấu bằng rỗng – chỉ dùng để so khớp nội dung, KHÔNG
    dùng để cắt chuỗi theo vị trí)."""
    if not text:
        return ""
    text = text.translate(_DIACRITIC_MAP)
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn").lower()


def normalize_ws(text: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", (text or "")).strip()


_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002190-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u2640-\u265F\u2B00-\u2BFF"
    "\u200d\u200b\u2060\u00ad]"
)


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text or "").strip()


TITLE_PREFIX_RE = re.compile(
    r"^(?:\[[^\]]{1,20}\]\s*|(?:thông\s*báo|nhắc\s*hạn|nhắc\s*nhở|chú\s*ý|cập\s*nhật|"
    r"quan\s*trọng|mời|hot|mới)\s*[:\-–]\s*|[-–—:•*|]+\s*)",
    re.IGNORECASE,
)


def normalize_event_title(title: str) -> str:
    """Chuẩn hoá tiêu đề sự kiện để so khớp bài gốc ↔ bài cập nhật.

    Bỏ nhãn [DEMO], các tiền tố "THÔNG BÁO:", "NHẮC HẠN:"…, dấu câu và khoảng
    trắng thừa; giữ nguyên nội dung tên sự kiện.
    """
    text = strip_emoji(normalize_ws(title or ""))
    for _ in range(4):
        new_text = TITLE_PREFIX_RE.sub("", text).strip()
        if new_text == text:
            break
        text = new_text
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text.lower())
    return normalize_ws(text)


def clean_title(text: str) -> str:
    """Lấy dòng đầu tiên có nghĩa làm tiêu đề, bỏ emoji/nhãn [DEMO]/ký tự trang trí."""
    for line in (text or "").splitlines():
        cand = strip_emoji(line)
        cand = normalize_ws(cand)
        if not cand:
            continue
        # Bỏ tiền tố dạng "[DEMO] " / "[TAG] " và các ký tự trang trí đầu dòng
        for _ in range(3):
            new = re.sub(r"^(?:\[[^\]]{1,20}\]\s*|[\-\–\—:•*|]+\s*)", "", cand)
            if new == cand:
                break
            cand = new
        cand = normalize_ws(cand)
        if len(cand) >= 8:
            return cand[:220]
    raw = normalize_ws((text or "").splitlines()[0] if (text or "").strip() else "")
    return strip_emoji(raw)[:220]


def _kw_hit(norm: str, keyword: str) -> bool:
    """So khớp từ khoá với ranh giới từ ở hai đầu (tránh 'tam doi' khớp 'trung tam doi')."""
    return re.search(
        rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", norm
    ) is not None


def _any_hit(norm: str, keywords: Iterable[str]) -> list[str]:
    return [kw for kw in keywords if _kw_hit(norm, kw)]


# ---------------------------------------------------------------------------
# Danh sách từ khoá nghiệp vụ
# ---------------------------------------------------------------------------
ACTIVITY_SIGNALS = [
    "dang ky", "dang ki", "tham gia", "tham du", "moi tham du", "moi cac ban",
    "hoat dong", "chuong trinh", "cuoc thi", "hoi thao", "seminar", "workshop",
    "toa dam", "talkshow", "tinh nguyen", "hien mau", "mua he xanh", "chien dich",
    "cau lac bo", "clb", "ngay hoi", "trai nghiem", "tap huan", "giao luu",
    "sinh hoat chuyen de", "buoi chia se", "ra quan", "giai bong", "giai chay",
    "dem nhac", "cuoc dua", "bootcamp", "cuoc hop", "hoi nghi",
]

CORE_EVENT_SIGNALS = [
    "tham gia", "tham du", "moi cac ban", "moi tham du", "chuong trinh gap go",
    "buoi chia se", "buoi toa dam", "buoi sinh hoat", "buoi tap huan", "buoi giao luu",
    "cuoc thi", "hoi thao", "seminar", "workshop", "toa dam", "talkshow",
    "tinh nguyen", "hien mau", "chien dich", "ngay hoi", "ra quan", "giao luu",
    "tap huan", "giai bong", "giai chay", "dem nhac", "tham quan",
    "sinh hoat chuyen de", "buoi chia se", "hoi nghi", "cuoc hop", "bootcamp",
]

NON_EVENT_NEGATIONS = [
    "khong co hoat dong", "khong kem theo hoat dong", "khong to chuc hoat dong",
    "khong to chuc", "khong co chuong trinh", "khong co su kien", "khong co dang ky",
]

CONGRATULATION_SIGNALS = [
    "chuc mung", "bieu duong", "dat giai", "thanh tich", "vinh danh",
]

STRONG_IRRELEVANT_SIGNALS = [
    "chuc mung", "tuyen dung", "viec lam", "giam gia", "khuyen mai", "uu dai",
    "hoc phi", "cong no", "lich nghi", "ket qua trung tuyen", "chuc mung nam moi",
    "ban hang", "quang cao", "nha tai tro", "thuc tap sinh",
]

ACTIVITY_STRONG_SIGNALS = [
    "tham gia", "tham du", "dang ky", "dang ki", "moi cac ban", "moi tham du",
    "ra quan", "tham quan", "tuyen thanh vien",
]

NOT_RELEVANT_SIGNALS = [
    "chuc mung", "tuyen dung", "viec lam", "thuc tap sinh", "uu dai", "giam gia",
    "khuyen mai", "ban hang", "quang cao", "nha tai tro", "lich nghi", "nghi le",
    "nghi tet", "hoc phi", "cong no", "ket qua trung tuyen", "chuc mung nam moi",
    "sinh nhat", "chia sẻ cảm hứng", "chia se cam hung", "lan toa tinh than",
]

REMINDER_SIGNALS = [
    "nhac han", "nhac nho", "han chot", "han cuoi", "sap het han", "dung quen",
    "chot danh sach", "chot dang ky", "moi nguoi nhanh tay", "han dang ky",
    "han dang ki", "han nop", "con lai", "gap gap", "nhanh tay dang ky",
]

CHANGE_SIGNALS = [
    "doi lich", "doi phong", "doi dia diem", "thay doi lich", "thay doi phong",
    "doi gio", "doi ngay", "hoan lich", "chuyen sang ngay",
    "doi sang ngay", "thay doi thoi gian", "thay doi dia diem",
    "doi hinh thuc", "chuyen sang phong", "doi ca", "doi buoi",
]

RESULT_SIGNALS = [
    "ket qua", "cong bo danh sach", "cong bo ket qua", "danh sach tham gia",
    "danh sach dat", "trao thuong", "tong ket", "chuc mung cac ban",
]

REGISTRATION_SIGNALS = [
    "dang ky", "dang ki", "link dang ky", "form dang ky", "quet ma qr",
    "dien form", "nop don", "dieu kien tham gia", "only dang ky",
]

LOCATION_LINE_PATTERNS = [
    re.compile(r"(?:địa\s*điểm|địa\s*điêm|diễn\s*ra\s*tại|tổ\s*chức\s*tại|tọa\s*lạc\s*tại)"
               r"\s*(?:tập\s*trung)?\s*[:\-–]?\s*(?P<loc>.+)$", re.IGNORECASE),
    re.compile(r"(?:hình\s*thức)\s*[:\-–]\s*(?P<loc>.+)$", re.IGNORECASE),
    re.compile(r"\b(?P<loc>(?:hội\s*trường|giảng\s*đường|phòng\s+[A-Z0-9]|sân\s+[A-Z0-9]|"
               r"nhà\s*thi\s*đấu|ký\s*túc\s*xá)[^\n;]{2,140})", re.IGNORECASE),
]

LOCATION_PREFIX_RE = re.compile(r"^(?:tập\s*trung|tổ\s*chức|diễn\s*ra)\s*[:\-–]?\s*", re.IGNORECASE)

ORGANIZER_PATTERNS = [
    re.compile(r"(?:đơn\s*vị\s*tổ\s*chức|tổ\s*chức\s*bởi|ban\s*tổ\s*chức)\s*[:\-–]\s*(?P<org>.+)$",
               re.IGNORECASE),
    re.compile(r"^(?P<org>[^\n]{4,140}?)\s+(?:phối\s*hợp\s+[^\n]{2,100}?\s+)?"
               r"(?:tổ\s*chức|triển\s*khai)\b", re.IGNORECASE),
    re.compile(r"\b(?P<org>(?:đoàn\s*khoa|đoàn\s*trường|hội\s*sinh\s*viên|trung\s*tâm|"
               r"phòng\s*công\s*tác|câu\s*lạc\s*bộ|clb|ban\s*chấp\s*hành|nhà\s*trường)"
               r"[^\n,.;]{0,100})", re.IGNORECASE),
]

ORGANIZER_CUT_RE = re.compile(
    r"\s+(?:mời|kính\s*mời|trân\s*trọng|thông\s*báo|chúc\s*mừng|mong|hân\s*hạnh)\b",
    re.IGNORECASE,
)

SCORE_PATTERNS = [
    re.compile(
        r"(?:cộng|được\s*cộng|được\s*tính|được\s*nhận|nhận\s*được|hưởng|cộng\s*thêm)\s*\+?\s*"
        r"(?P<score>\d{1,2}(?:[.,]\d)?)\s*(?:điểm|đ)\s*(?:rèn\s*luyện|rl|drl|ren\s*luyen)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<score>\d{1,2}(?:[.,]\d)?)\s*điểm\s*(?:rèn\s*luyện|rl|drl)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:điểm\s*rèn\s*luyện|điểm\s*drl|drl)\s*[:\-–]?\s*\+?\s*(?P<score>\d{1,2}(?:[.,]\d)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\+\s*(?P<score>\d{1,2}(?:[.,]\d)?)\s*(?:điểm|đ)\b",
        re.IGNORECASE,
    ),
]

DRL_MENTION_RE = re.compile(
    r"điểm\s*rèn\s*luyện|điểm\s*rl\b|điểm\s*đrl|\bdrl\b|rèn\s*luyện|ren\s*luyen",
    re.IGNORECASE,
)

# Từ khoá ngữ nghĩa bổ trợ cho từng tiêu chí (dùng khi tên tiêu chí trong DB
# không đủ đặc trưng). Khoá là một phần (không dấu) của tên tiêu chí.
#: Từ khoá nhận diện 5 NHÓM tiêu chí ĐRL đúng như hcmus.drl.vn hiển thị.
#: Cấu trúc: (các từ khoá để NHẬN RA nhóm khi tên nhóm chứa chúng, các từ khoá
#: dùng để SO KHỚP nội dung bài đăng).
CRITERION_KEYWORD_RULES: list[tuple[list[str], list[str]]] = [
    # Nhóm 1 – Trách nhiệm chấp hành pháp luật, nội quy, quy chế nhà trường
    (["phap luat", "noi quy", "quy che", "ky luat"], [
        "noi quy", "quy che", "phap luat", "ky luat", "an toan giao thong",
        "phong chay chua chay", "chuyen can", "di hoc dung gio", "khong vi pham",
        "ky luat thi", "quy dinh cua truong",
    ]),
    # Nhóm 2 – Trách nhiệm, tinh thần và thái độ trong học tập
    (["hoc tap", "thai do", "tinh than", "ket qua hoc tap"], [
        "ket qua hoc tap", "hoc tap", "gpa", "hoc bong", "thi dua hoc tap",
        "tinh than hoc tap", "thai do hoc tap", "y thuc hoc tap", "diem trung binh",
        "khong dat mon", "hoc lai", "thi lai",
    ]),
    # Nhóm 3 – Hoạt động chính trị, xã hội, văn hoá, văn nghệ, thể thao
    (["chinh tri", "xa hoi", "van hoa", "van nghe", "the thao", "tinh nguyen"], [
        # Chính trị – xã hội – tình nguyện
        "tinh nguyen", "mua he xanh", "chien dich", "xuan tinh nguyen", "ra quan",
        "chinh tri", "cong tac xa hoi", "ngay hoi tinh nguyen", "mua xuan cho em",
        # Học thuật / hội thảo
        "hoi thao", "seminar", "workshop", "toa dam", "nghien cuu khoa hoc", "nckh",
        "olympic", "cuoc thi hoc thuat", "bao cao khoa hoc",
        # Văn hoá – văn nghệ
        "van nghe", "van hoa", "ca nhac", "bieu dien", "dem nhac", "trien lam",
        "giao luu van hoa", "cuoc thi van nghe", "am nhac",
        # Thể thao
        "the thao", "the duc", "bong da", "bong ro", "bong chuyen", "cau long",
        "chay bo", "giai chay", "marathon", "viet da",
        # Phòng chống tội phạm, tệ nạn
        "phong chong toi pham", "te nan xa hoi", "ma tuy", "an toan xa hoi",
        # Kỹ năng / hội nhập (thuộc nhóm hoạt động)
        "ky nang", "ky nang mem", "hoi nhap", "ngoai ngu", "tieng anh", "ielts",
        "thuyet trinh", "giao tiep", "phat trien ban than", "cau lac bo", "clb",
        "tap huan", "khoi nghiep", "startup", "doi moi sang tao",
    ]),
    # Nhóm 4 – Trách nhiệm công dân trong quan hệ cộng đồng
    (["cong dong", "cong dan", "quan he cong dong"], [
        "hien mau", "hien mau nhan dao", "giot hong", "gio t hon giong",
        "ngay hoi hien mau", "benh vien truyen mau",
        "cong dong", "vi cong dong", "du an cong dong", "ho tro cong dong",
        "ky tuc xa", "khu pho", "dia phuong", "ngay chu nhat xanh", "don ve sinh",
        "xay dung nong thon", "hieu hoc", "tre em", "nguoi gia",
    ]),
    # Nhóm 5 – Công tác cán bộ lớp, đoàn thể, khen thưởng
    (["can bo lop", "doan the", "khen thuong", "cong tac can bo"], [
        "can bo lop", "lop truong", "lop pho", "bi thu chi doan", "bi thu doan",
        "cong tac doan", "cong tac hoi", "doan thanh nien", "hoi sinh vien",
        "khen thuong", "giay khen", "bang khen", "thanh tich xuat sac",
        "sinh vien 5 tot", "sinh vien gioi",
    ]),
]

# Từ dừng khi so khớp tiêu chí (tránh "công nghệ" khớp "cộng đồng"…)
CRITERION_STOPWORDS = {
    "hoat", "dong", "cong", "hoc", "khoa", "vien", "sinh", "thuat", "nghien", "cuu",
    "nhan", "dao", "mau", "hien", "giao", "duc", "tao", "boi", "duoc", "theo", "cac",
    "trong", "nang", "cao", "moi", "sang", "tao", "cua", "va", "cho", "voi", "cung",
    "tich", "cuc", "tham", "gia", "tieu", "chi", "diem", "ren", "luyen", "noi", "dung",
}

POST_TYPE_LABELS = {
    "event_announcement": "Thông báo hoạt động",
    "deadline_reminder": "Nhắc hạn đăng ký",
    "schedule_change": "Đổi lịch / đổi phòng",
    "result_announcement": "Công bố kết quả",
    "recruitment": "Tuyển thành viên / tuyển dụng",
    "promotion": "Quảng bá / chúc mừng",
    "administrative": "Hành chính chung",
    "other": "Khác",
}

# ---------------------------------------------------------------------------
# Regex ngày tháng & giờ
# ---------------------------------------------------------------------------
# Ngày: 22/11/2026 · 22/11 · 22.11.2026 · "ngày 22 tháng 11 năm 2026" · "ngày 22-11-2026"
# Lookbehind (?<![\d/:hH_.]) chặn bắt nhầm "30 - 11" trong "08h30 - 11h30" hoặc "TC_5.2".
_DATE_RE = re.compile(
    r"(?<![\d/:hH_.])"
    r"(?:"
    r"(?P<d1>\d{1,2})\s*[/.]\s*(?P<m1>\d{1,2})\s*(?:[/.]\s*(?P<y1>\d{4}))?(?!\d)"
    r"|ngày\s+(?P<d2>\d{1,2})\s*(?:[/.\-]|tháng)\s*(?P<m2>\d{1,2})\s*(?:[/.\-]|năm)?\s*(?P<y2>\d{4})?"
    r")",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    # Chấp nhận: 08h30, 8h, 13g30 (cách viết miền Nam), 8 giờ 30, 08:30
    # "g" chỉ nhận khi CÓ phút (13g30) để tránh nhầm với "5g" (gam) trong văn bản.
    r"(?<![\d:])(?:(?P<h1>\d{1,2})[hH](?P<mn1>\d{2})?"
    r"|(?P<h4>\d{1,2})[gG](?P<mn4>\d{2})(?![\d])"
    r"|(?P<h2>\d{1,2})\s*giờ(?:\s*(?P<mn2>\d{1,2}))?"
    r"|(?P<h3>\d{1,2}):(?P<mn3>\d{2}))(?![\d:])",
    re.IGNORECASE,
)

DEADLINE_KEYWORDS = [
    "hạn chót", "hạn cuối", "hạn đăng ký", "hạn đăng kí", "hạn ghi danh",
    "hạn nộp", "chậm nhất", "chốt danh sách", "chốt đăng ký", "chốt đăng kí",
    "hết hạn", "deadline", "trước ngày", "trước",
]


@dataclass
class _Moment:
    """Một mốc thời gian đã ghép ngày + giờ."""
    moment: datetime
    pos: int
    end_pos: int
    has_year: bool = False
    has_time: bool = False
    line_no: int = 0


@dataclass
class _TimeRange:
    start_moment: Optional[datetime] = None
    end_moment: Optional[datetime] = None
    start_pos: int = -1
    deadline_moment: Optional[datetime] = None
    deadline_pos: int = -1
    has_year: bool = True
    has_start_time: bool = False
    has_end_time: bool = False
    has_deadline_time: bool = False


@dataclass
class ExtractionResult:
    """Kết quả bóc tách thô (dùng nội bộ, sau đó dựng báo cáo JSON)."""
    title: str = ""
    description: str = ""
    organizer: str = ""
    location: str = ""
    campus: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    registration_deadline: Optional[str] = None
    expected_score: Optional[float] = None
    score_context: str = "NONE"            # NONE | EVENT_SPECIFIC | RULE_GENERIC
    score_evidence: str = ""
    criterion_code: Optional[str] = None
    criterion_confidence: float = 0.0
    criterion_keywords: list[str] = field(default_factory=list)
    post_type: str = "other"
    is_student_participation_possible: bool = False
    relevance_label: str = config.LABEL_EVENT_CANDIDATE
    relevance_reason: str = ""
    rejection_reason: Optional[str] = None
    missing_flags: dict = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    rule_citation: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    registration_present: bool = False
    has_score_mention_in_text: bool = False
    drl_mentioned: bool = False


# ---------------------------------------------------------------------------
# Bóc tách thời gian (theo từng dòng)
# ---------------------------------------------------------------------------
def _current_year() -> int:
    return datetime.now().year


def _iter_lines_with_offset(text: str):
    offset = 0
    for line_no, raw_line in enumerate(text.splitlines(keepends=True)):
        yield line_no, raw_line.rstrip("\r\n"), offset
        offset += len(raw_line)


def _find_dates_in_line(line: str) -> list[tuple[datetime, int, int, bool]]:
    """Trả về danh sách (ngày, pos_start, pos_end, has_year) trong 1 dòng."""
    out = []
    for m in _DATE_RE.finditer(line):
        day_raw = m.group("d1") or m.group("d2")
        month_raw = m.group("m1") or m.group("m2")
        year_raw = m.group("y1") or m.group("y2")
        if not day_raw or not month_raw:
            continue
        day, month = int(day_raw), int(month_raw)
        has_year = year_raw is not None
        year = int(year_raw) if has_year else _current_year()
        try:
            dt = datetime(year, month, day)
        except ValueError:
            continue
        out.append((dt, m.start(), m.end(), has_year))
    return out


def _find_times_in_line(line: str) -> list[tuple[int, int, int, int]]:
    """Trả về (giờ, phút, pos_start, pos_end) cho mọi mốc giờ trong 1 dòng."""
    out = []
    for m in _TIME_RE.finditer(line):
        hour_raw = m.group("h1") or m.group("h4") or m.group("h2") or m.group("h3")
        minute_raw = (m.group("mn1") or m.group("mn4") or m.group("mn2")
                      or m.group("mn3") or 0)
        try:
            hour, minute = int(hour_raw), int(minute_raw)
        except (TypeError, ValueError):
            continue
        if hour > 23 or minute > 59:
            continue
        out.append((hour, minute, m.start(), m.end()))
    return out


def _find_moments(text: str) -> list[_Moment]:
    """Ghép ngày + giờ theo TỪNG DÒNG.

    Ví dụ dòng "⏰ Thời gian: 08h30 - 11h30, ngày 22/11/2026":
        → start 22/11 08:30 và end 22/11 11:30 (2 mốc).
    Dòng "👉 Đăng ký trước 23h59 ngày 20/11/2026":
        → 1 mốc 20/11 23:59.
    """
    # Giờ hành chính / giờ mở cửa không phải giờ diễn ra hoạt động → bỏ qua dòng này
    OFFICE_HOURS_RE = re.compile(
        r"giờ\s*(?:làm\s*việc|hành\s*chính|mở\s*cửa|tiếp\s*dân|giao\s*dịch)",
        re.IGNORECASE,
    )

    moments: list[_Moment] = []
    for line_no, line, offset in _iter_lines_with_offset(text):
        if not line.strip():
            continue
        if OFFICE_HOURS_RE.search(line):
            continue
        dates = _find_dates_in_line(line)
        if not dates:
            continue
        times = _find_times_in_line(line)
        used_time_idx: set[int] = set()

        for date_idx, (dt, d_start, d_end, has_year) in enumerate(dates):
            # Giờ nằm TRƯỚC ngày trong cùng dòng (vd "08h30 - 11h30, ngày 22/11")
            before = [
                (i, t) for i, t in enumerate(times)
                if i not in used_time_idx and t[3] <= d_start and d_start - t[3] <= 60
            ]
            # Giới hạn: chỉ lấy các giờ thuộc cùng "cụm" với ngày (cách nhau <= 18 ký tự)
            cluster: list[tuple[int, tuple]] = []
            for i, t in reversed(before):
                if not cluster:
                    cluster.append((i, t))
                elif cluster[-1][1][2] - t[3] <= 18:   # khoảng trống giữa 2 mốc giờ
                    cluster.append((i, t))
                else:
                    break
            cluster = list(reversed(cluster))

            after = [
                (i, t) for i, t in enumerate(times)
                if i not in used_time_idx and t[2] >= d_end and t[2] - d_end <= 25
            ]

            if cluster:
                i0, t0 = cluster[0]
                used_time_idx.add(i0)
                start_dt = dt.replace(hour=t0[0], minute=t0[1])
                moments.append(_Moment(start_dt, offset + d_start, offset + t0[3],
                                       has_year, True, line_no))
                if len(cluster) >= 2:
                    i1, t1 = cluster[-1]
                    if (t1[0], t1[1]) > (t0[0], t0[1]):
                        used_time_idx.add(i1)
                        end_dt = dt.replace(hour=t1[0], minute=t1[1])
                        moments.append(_Moment(end_dt, offset + t1[2], offset + d_end,
                                               has_year, True, line_no))
            elif after:
                i0, t0 = after[0]
                used_time_idx.add(i0)
                start_dt = dt.replace(hour=t0[0], minute=t0[1])
                moments.append(_Moment(start_dt, offset + d_start, offset + t0[3],
                                       has_year, True, line_no))
                if len(after) >= 2:
                    i1, t1 = after[1]
                    if (t1[0], t1[1]) > (t0[0], t0[1]):
                        used_time_idx.add(i1)
                        end_dt = dt.replace(hour=t1[0], minute=t1[1])
                        moments.append(_Moment(end_dt, offset + t1[2], offset + d_end,
                                               has_year, True, line_no))
            else:
                moments.append(_Moment(dt, offset + d_start, offset + d_end,
                                       has_year, False, line_no))
    return moments


def _pick_deadline(moments: list[_Moment], text: str) -> Optional[_Moment]:
    """Chọn mốc gần từ khoá hạn chót nhất ('trước …', 'hạn chót …')."""
    best: Optional[_Moment] = None
    best_dist = 10**9
    for keyword in DEADLINE_KEYWORDS:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        for m in pattern.finditer(text):
            for moment in moments:
                # Mốc nằm SAU từ khoá (vd "trước 23h59 ngày 20/11"): cho phép tới 180 ký tự
                after_dist = moment.pos - m.end()
                if 0 <= after_dist <= 180 and after_dist < best_dist:
                    best, best_dist = moment, after_dist
                # Mốc nằm TRƯỚC từ khoá (vd "20/11 là hạn chót")
                before_dist = m.start() - moment.end_pos
                if 0 <= before_dist <= 25 and before_dist + 8 < best_dist:
                    best, best_dist = moment, before_dist + 8
    return best


def _fmt(dt: Optional[datetime]) -> Optional[str]:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else None


def extract_time_info(text: str, result: ExtractionResult) -> None:
    """Điền start_time / end_time / registration_deadline + ghi giả định."""
    moments = _find_moments(text)
    if not moments:
        if _TIME_RE.search(text):
            result.warnings.append(
                "Bài đăng có nhắc giờ nhưng không có ngày cụ thể – hệ thống không tự suy diễn ngày."
            )
        return

    deadline = _pick_deadline(moments, text)
    if deadline:
        if deadline.has_time:
            result.registration_deadline = _fmt(deadline.moment)
        else:
            result.registration_deadline = _fmt(deadline.moment.replace(hour=23, minute=59))
            result.assumptions.append("Hạn đăng ký không ghi giờ → giả định 23:59 cùng ngày.")
        moments = [m for m in moments if not (m.pos == deadline.pos and m.moment == deadline.moment)]

    remaining = sorted(moments, key=lambda m: (m.moment, m.pos))
    if remaining:
        start = remaining[0]
        result.start_time = _fmt(start.moment)
        if not start.has_year:
            result.assumptions.append(
                f"Năm không ghi rõ trong bài → giả định năm {start.moment.year}."
            )
        if not start.has_time:
            result.assumptions.append(
                "Bài đăng không ghi giờ bắt đầu cụ thể (chỉ có ngày) – cần xác minh lại."
            )

        end_candidate = None
        for cand in remaining[1:]:
            if cand.moment > start.moment:
                end_candidate = cand
                break
        if end_candidate:
            result.end_time = _fmt(end_candidate.moment)
        else:
            result.end_time = _fmt(start.moment + timedelta(hours=2))
            result.assumptions.append(
                "Không ghi giờ kết thúc → giả định kéo dài 2 giờ (chỉ để xếp lộ trình, cần xác minh)."
            )

    if result.start_time and result.registration_deadline \
            and result.start_time == result.registration_deadline:
        result.start_time = None
        result.end_time = None
        result.assumptions = [
            a for a in result.assumptions
            if "giờ kết thúc" not in a and "giờ bắt đầu" not in a
        ]
        result.warnings.append(
            "Chỉ tìm thấy một mốc thời gian duy nhất và mốc này mang dấu hiệu HẠN ĐĂNG KÝ – "
            "chưa rõ giờ diễn ra sự kiện."
        )


# ---------------------------------------------------------------------------
# Bóc tách địa điểm / cơ sở
# ---------------------------------------------------------------------------
def guess_campus(location_text: str) -> str:
    """Ánh xạ văn bản địa điểm về mã cơ sở HCMUS (NVC / Linh Trung / Online)."""
    low = strip_accents(location_text or "")
    if not low:
        return ""
    if "linh trung" in low:
        return "Linh Trung"
    if "nguyen van cu" in low or re.search(r"\bnvc\b", low):
        return "NVC"
    if "online" in low or "truc tuyen" in low or "zoom" in low or "google meet" in low \
            or "ms teams" in low or re.search(r"\bteams\b", low):
        return "Online"
    return ""


PENDING_LOCATION_MARKERS = [
    "se thong bao", "thong bao sau", "se cap nhat", "cap nhat sau", "se gui",
    "qua email", "chua xac dinh", "dang cap nhat", "se cong bo", "chua co dia diem",
]


def _accept_location(loc_text: str, result: ExtractionResult) -> bool:
    """Nhận địa điểm nếu hợp lệ; loại bỏ lời hứa 'sẽ thông báo sau'."""
    loc = normalize_ws(loc_text).strip(" .,:;-–—")
    if len(loc) < 4:
        return False
    loc_norm = strip_accents(loc)
    BAD_LOCATION_PATTERNS = [
        r"^phong\s*hop", r"^lich\s*su\s*dung", r"^danh\s*sach",
        r"^tuan\s*\d", r"^bang\s", r"^noi\s*dung", r"^thoi\s*gian\s*:",
        # Cụm danh từ bị regex bắt nhầm thành "địa điểm" (phát hiện trên dữ liệu thật)
        r"^phong\s*(?:tranh|ngua|chong|trao|cho|hoc\s*bong|thi|du\s*thi|hop\s*tac)",
        r"^san\s*(?:choi|khau|van\s*dong\s*truong\s*hop)", r"^noi\s*(?:gap|dung|chon)",
        r"^khu\s*(?:vuc|dong\s*nguoi)", r"^diem\s*(?:den|gap|thi)",
        r"^hoi\s*truong\s*(?:trong|theo|voi|de)", r"^phong\s*(?:theo|voi|de|trong)",
        r"^phong\s+(?:khoa\s*hoc|dao\s*tao|to\s*chuc|cong\s*tac|quan\s*ly|ke\s*toan)",
        r"^hoi\s*truong\s+(?:da|se|dang)\s",
    ]
    # Địa điểm phải trỏ tới một KHÔNG GIAN CỤ THỂ: có số nhà, tên cơ sở, hoặc mã phòng
    # (E402, F102, C36, B116, I23…) – nếu không thì gần như chắc chắn là đoán sai.
    SPACE_HINT_RE = re.compile(
        r"(?:\b[0-9]{1,4}\b|nguy\S*n\s*v\S*n\s*c\S*|linh\s*trung|\b[A-Z]{1,2}\d{2,3}[A-Z]?\b"
        r"|h\S*i\s*tr\S*\S*ng|gi\S*ng\s*\S*\S*\S*ng|t\S*\S*\s*nh\S*|c\S*\S*\s*s\S*\b"
        r"|online|tr\S*c\s*tuy\S*n|zoom|teams|meet)",
        re.IGNORECASE,
    )
    if any(re.search(pat, loc_norm) for pat in BAD_LOCATION_PATTERNS):
        return False
    if any(marker in loc_norm for marker in PENDING_LOCATION_MARKERS):
        result.warnings.append(
            f'Thông tin địa điểm chỉ là lời hứa thông báo sau ("{loc[:70]}") '
            "→ được ghi nhận là THIẾU địa điểm."
        )
        return False
    # Địa điểm trích từ văn xuôi hay bị kéo dài thành cả câu. Cắt ở ranh giới
    # cụm hợp lý để không ra "…, Ph" cụt nghĩa.
    loc = loc.splitlines()[0].strip()                    # bỏ phần xuống dòng
    # Bỏ mệnh đề giải thích dính sau địa điểm (phát hiện trên dữ liệu thật)
    loc = re.split(
        r"\s+(?:trong\s*khu\S*n\s*kh\S*|nh\S*m\s|v\S*i\s*m\S*c\s*\S*\S*ch|"
        r"\S*\S*i\s*di\S*n|\S*\S*i\s*bi\S*u|d\S*\S*\s*tr\S*nh\s*b\S*y|theo\s*th\S*ng\s*b\S*o)",
        loc, flags=re.IGNORECASE,
    )[0].strip(" ,;.-–—")
    # "phòng Phòng …" → "Phòng …"
    loc = re.sub(r"(?i)^(phòng|sân|hội\s*trường|giảng\s*đường)\s+\1\s+", lambda m: m.group(1) + " ", loc)
    loc = re.split(r"(?:Thời\s*gian|Ngày|Lúc|Vào\s*lúc)\s*[:：]", loc)[0].strip(" ,;.-–—")
    loc = re.split(r"\.\s", loc)[0].strip(" ,;.-–—")
    if len(loc) > 90:
        parts = re.split(r"(?<=[).])\s*[,;–-]\s*|\s*[-–]\s+|(?<=\S)\s{2,}", loc)
        kept = ""
        for part in parts:
            part = part.strip(" ,;.-–—")
            if not part:
                continue
            if kept and len(kept) + len(part) + 2 > 130:
                break
            kept = f"{kept}, {part}" if kept else part
        loc = kept or loc[:130]
    # Không phải không gian cụ thể → coi như THIẾU địa điểm (thà để trống còn hơn sai)
    if not SPACE_HINT_RE.search(strip_accents(loc) if False else loc):
        result.warnings.append(
            f'Cụm "{loc[:60]}" không trỏ tới địa điểm cụ thể → ghi nhận là THIẾU địa điểm.'
        )
        return False
    result.location = loc[:160]
    result.campus = guess_campus(loc)
    # Phòng/giảng đường không kèm tên cơ sở → cơ sở mặc định của trường (NVC).
    # Ghi rõ đây là SUY LUẬN để người dùng kiểm chứng, không phải dữ liệu nguồn.
    if not result.campus and re.match(
        r"^(?:phòng|giảng\s*đường|hội\s*trường|sân|nhà\s*thi\s*đấu|tòa)",
        loc_norm,
    ):
        result.campus = "NVC"
        result.warnings.append(
            f'Địa điểm "{loc[:60]}" không ghi cơ sở → tạm gán cơ sở Nguyễn Văn Cừ (mặc định của trường).'
        )
    return True


def extract_location(text: str, result: ExtractionResult) -> None:
    """Bóc địa điểm theo 2 lượt: (1) dòng có nhãn 'Địa điểm:'…, (2) mẫu chung."""
    lines = [normalize_ws(strip_emoji(l)) for l in text.splitlines()]
    lines = [l for l in lines if l]

    # Lượt 1 – dòng có nhãn rõ ràng
    for line in lines:
        for pattern in LOCATION_LINE_PATTERNS[:2]:
            match = pattern.search(line)
            if not match:
                continue
            loc = normalize_ws(match.group("loc"))
            loc = LOCATION_PREFIX_RE.sub("", loc)
            loc = re.split(r"(?:\s+-\s+|\s*\|\s*)", loc)[0]
            loc = re.split(r"[.;!]\s", loc)[0]
            if _accept_location(loc, result):
                return
            break

    # Lượt 2 – mẫu chung (phòng/sân/hội trường…), bỏ qua dòng quá dài kiểu văn xuôi
    for line in lines:
        if len(line) > 160:
            continue
        for pattern in LOCATION_LINE_PATTERNS[2:]:
            match = pattern.search(line)
            if match and _accept_location(match.group("loc"), result):
                return

    # Lượt 3 – tên cơ sở xuất hiện trần trong bài
    low = strip_accents(text)
    if "linh trung" in low:
        result.location = "Cơ sở Linh Trung (theo nội dung bài đăng)"
        result.campus = "Linh Trung"
    elif "nguyen van cu" in low:
        result.location = "Cơ sở Nguyễn Văn Cừ (theo nội dung bài đăng)"
        result.campus = "NVC"
    elif "online" in low or "truc tuyen" in low:
        result.location = "Trực tuyến (Online)"
        result.campus = "Online"


# ---------------------------------------------------------------------------
# Bóc tách nội dung / đơn vị tổ chức
# ---------------------------------------------------------------------------
def extract_organizer(text: str, result: ExtractionResult) -> None:
    """Bóc đơn vị tổ chức: ưu tiên dòng có nhãn, sau đó mẫu 'X tổ chức', cuối cùng tên đơn vị."""
    lines = [normalize_ws(strip_emoji(l)) for l in text.splitlines()]
    lines = [l for l in lines if l]
    title_norm = strip_accents(result.title)

    def _clean(org: str) -> str:
        org = ORGANIZER_CUT_RE.split(org)[0]
        return normalize_ws(org).strip(" .,:;-–—")

    # Lượt 1 – nhãn "Đơn vị tổ chức:" / "Ban tổ chức:"
    for line in lines:
        match = ORGANIZER_PATTERNS[0].search(line)
        if match:
            org = _clean(match.group("org"))
            if 4 <= len(org) <= 130:
                result.organizer = org
                return

    # Lượt 2 – mẫu "X tổ chức / triển khai"
    for line in lines:
        match = ORGANIZER_PATTERNS[1].search(line)
        if match:
            org = _clean(match.group("org"))
            if 4 <= len(org) <= 130 and strip_accents(org)[:25] not in title_norm:
                result.organizer = org
                return

    # Lượt 3 – tên đơn vị chuẩn mực xuất hiện trong bài (bỏ qua chính tiêu đề)
    for line in lines:
        if strip_accents(line)[:20] in title_norm and len(line) > 30:
            continue
        match = ORGANIZER_PATTERNS[2].search(line)
        if match:
            org = _clean(match.group("org"))
            if 4 <= len(org) <= 130:
                result.organizer = org
                return


# ---------------------------------------------------------------------------
# Bóc tách điểm ĐRL
# ---------------------------------------------------------------------------
def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip()]


def extract_score(text: str, result: ExtractionResult) -> None:
    result.drl_mentioned = bool(DRL_MENTION_RE.search(text))
    sentences = _split_sentences(text)
    for sentence in sentences:
        for pattern in SCORE_PATTERNS:
            m = pattern.search(sentence)
            if not m:
                continue
            raw = m.group("score").replace(",", ".")
            try:
                score = float(raw)
            except ValueError:
                continue
            if not (0 <= score <= 30):
                continue
            low = strip_accents(sentence)
            event_markers = ["nay", "chuong trinh", "hoat dong", "su kien", "tham gia",
                             "cuoc thi", "workshop", "hoi thao", "ngay hoi", "tham du"]
            rule_markers = ["quy che", "quy dinh", "theo muc", "tieu chi", "danh muc",
                            "diem ren luyen duoc tinh"]
            is_rule = any(mk in low for mk in rule_markers) and not any(
                mk in low for mk in ["hoat dong nay", "chuong trinh nay", "su kien nay"]
            )
            result.expected_score = score
            result.has_score_mention_in_text = True
            result.score_evidence = normalize_ws(sentence)[:300]
            result.score_context = "RULE_GENERIC" if is_rule else "EVENT_SPECIFIC"
            if not result.drl_mentioned:
                result.drl_mentioned = True
            return


# ---------------------------------------------------------------------------
# Bóc tách mã tiêu chí dự kiến
# ---------------------------------------------------------------------------
def _build_criterion_spaces(criteria_catalog: Optional[Iterable[dict]]
                            ) -> list[tuple[str, str, set[str]]]:
    catalog = list(criteria_catalog or [])
    spaces: list[tuple[str, str, set[str]]] = []
    if catalog:
        for c in catalog:
            code = str(c.get("code", "")).strip()
            name = str(c.get("name", "")).strip()
            if not code:
                continue
            keywords: set[str] = set()
            for word in strip_accents(name).split():
                if len(word) > 3 and word not in CRITERION_STOPWORDS:
                    keywords.add(word)
            for trigger, kws in CRITERION_KEYWORD_RULES:
                if any(t in strip_accents(name) for t in trigger):
                    keywords.update(kws)
            spaces.append((code, name, keywords))
        return spaces

    # Khung 5 nhóm đúng như hcmus.drl.vn hiển thị (xem drl/seed_data.py).
    defaults = {
        "TC_1": ("trach nhiem chap hanh phap luat noi quy quy che nha truong "
                 "y thuc ky luat"),
        "TC_2": ("trach nhiem tinh than thai do trong hoc tap ket qua hoc tap "
                 "diem hoc tap"),
        "TC_3": ("hoat dong chinh tri xa hoi van hoa van nghe the thao "
                 "tinh nguyen hoi thao workshop cuoc thi phong chong toi pham "
                 "te nan xa hoi"),
        "TC_4": ("trach nhiem cong dan quan he cong dong hien mau nhan dao "
                 "hoat dong vi cong dong ky tuc xa dia phuong"),
        "TC_5": ("cong tac can bo lop cong tac doan the can bo doan hoi "
                 "thanh tich xuat sac khen thuong"),
    }
    for code, name in defaults.items():
        keywords = {w for w in name.split() if len(w) > 3 and w not in CRITERION_STOPWORDS}
        for trigger, kws in CRITERION_KEYWORD_RULES:
            if any(t in name for t in trigger):
                keywords.update(kws)
        spaces.append((code, name, keywords))
    return spaces


def extract_criterion(text: str, criteria_catalog: Optional[Iterable[dict]] = None,
                      result: Optional[ExtractionResult] = None) -> None:
    """Gán mã tiêu chí dự kiến bằng so khớp từ khoá ngữ nghĩa.

    Đây là SUY LUẬN NGỮ CẢNH (cần con người xác minh), không phải xác nhận quy
    chế. Nhãn đi kèm luôn là POTENTIAL_DRL + NEEDS_HUMAN_REVIEW.
    """
    if result is None:
        return
    norm_body = strip_accents(text)
    norm_title = strip_accents(result.title)
    spaces = _build_criterion_spaces(criteria_catalog)

    best_code, best_name, best_score, best_kws = None, None, 0.0, []
    for code, name, keywords in spaces:
        matched = []
        score = 0.0
        for kw in keywords:
            hit_body = _kw_hit(norm_body, kw)
            if not hit_body:
                continue
            weight = float(len(kw.split()))  # cụm càng dài càng đặc trưng
            if _kw_hit(norm_title, kw):
                weight *= 1.6
            score += weight
            matched.append(kw)
        if score > best_score:
            best_code, best_name, best_score, best_kws = code, name, score, matched

    if best_code and best_score >= 2.0:
        result.criterion_code = best_code
        result.criterion_confidence = min(0.95, 0.35 + 0.10 * best_score)
        result.criterion_keywords = sorted(best_kws, key=len, reverse=True)[:6]


# ---------------------------------------------------------------------------
# Phân loại loại bài đăng
# ---------------------------------------------------------------------------
def detect_post_type(text: str) -> str:
    norm = strip_accents(text)
    has_reg = bool(_any_hit(norm, ["dang ky", "dang ki", "link dang ky", "form dang ky"]))
    if _any_hit(norm, RESULT_SIGNALS):
        return "result_announcement"
    if _any_hit(norm, CHANGE_SIGNALS):
        return "schedule_change"
    if _any_hit(norm, REMINDER_SIGNALS) and has_reg:
        return "deadline_reminder"
    if _any_hit(norm, ["tuyen dung", "tuyen thanh vien", "chieu sinh", "ung tuyen"]):
        return "recruitment"
    if _any_hit(norm, ["chuc mung", "giam gia", "khuyen mai", "uu dai", "hoc phi", "lich nghi"]):
        return "promotion"
    if _any_hit(norm, ACTIVITY_SIGNALS):
        if _any_hit(norm, REMINDER_SIGNALS):
            return "deadline_reminder"
        return "event_announcement"
    if _any_hit(norm, ["thong bao", "khao sat", "khao sat", "quy che", "ke hoach"]):
        return "administrative"
    return "other"


# ---------------------------------------------------------------------------
# Phân loại 2 bước
# ---------------------------------------------------------------------------
def _compute_missing_flags(text: str, result: ExtractionResult) -> dict:
    """Tính 4 cờ thiếu dữ liệu trọng tâm trên dữ liệu đã bóc tách."""
    return {
        "is_missing_time": result.start_time is None and result.registration_deadline is None,
        "is_missing_location": not result.location,
        "is_missing_content": len(re.sub(r"\s+", "", text or "")) < 30,
        "is_missing_score": result.expected_score is None,
    }


def classify_two_step(text: str, result: ExtractionResult) -> None:
    """Áp dụng đúng quy tắc 2 bước + 4 nhóm thông tin (mục 4 & 5 đề bài).

    Cờ thiếu dữ liệu (theo đúng định nghĩa 4 nhóm thông tin trọng tâm):
    - is_missing_time     : không có cả thời gian diễn ra lẫn hạn đăng ký
    - is_missing_location : không có địa điểm / cơ sở / hình thức Online
    - is_missing_content  : văn bản quá ngắn (< 30 ký tự), không đủ nội dung
    - is_missing_score    : không trích xuất được Điểm ĐRL kỳ vọng cụ thể

    Ánh xạ nhãn:
    - Thiếu Time / Location / Content        → INSUFFICIENT_INFO
    - Đủ 3 nhóm trên + có điểm ĐRL cụ thể    → POTENTIAL_DRL (NEEDS_HUMAN_REVIEW)
    - Đủ 3 nhóm trên, nhắc ĐRL nhưng chỉ nêu
      chung "theo quy chế" (không rõ điểm)   → INSUFFICIENT_INFO (khuyết nhóm 4)
    - Đủ 3 nhóm trên, KHÔNG nhắc gì về ĐRL   → EVENT_CANDIDATE
    - Không phải hoạt động tham gia được     → NOT_RELEVANT
    """
    norm = strip_accents(text)
    activity_hits = _any_hit(norm, ACTIVITY_SIGNALS)
    strong_hits = _any_hit(norm, ACTIVITY_STRONG_SIGNALS)
    irrelevant_hits = _any_hit(norm, NOT_RELEVANT_SIGNALS)
    result.registration_present = bool(_any_hit(norm, REGISTRATION_SIGNALS))

    # --- BƯỚC 1: có phải hoạt động thực tế sinh viên tham gia được? ---
    strong_irrelevant = _any_hit(norm, STRONG_IRRELEVANT_SIGNALS)
    core_event_hits = _any_hit(norm, CORE_EVENT_SIGNALS)
    negation_hits = _any_hit(norm, NON_EVENT_NEGATIONS)

    # Ưu tiên 0: bài CHÚC MỪNG THÀNH TÍCH (kể cả có nhắc "cuộc thi" đã diễn ra)
    congrats = _any_hit(norm, CONGRATULATION_SIGNALS)
    is_congratulation = (
        "chuc mung" in congrats
        and any(w in congrats for w in ("dat giai", "thanh tich", "bieu duong", "vinh danh"))
        and not result.registration_present
    )

    # Ưu tiên 1a: tín hiệu THƯƠNG MẠI rõ ràng (giảm giá/ưu đãi mua hàng/khuyến mãi)
    # → luôn NOT_RELEVANT dù văn bản có chữ "chương trình", trừ khi có lõi sự kiện
    #   và có đăng ký tham gia (khi đó để bước 2 quyết định).
    commerce_hits = _any_hit(norm, [
        "giam gia", "khuyen mai", "uu dai danh rieng", "mua laptop", "mua hang",
        "chi danh cho sinh vien mua", "nha tai tro",
    ])
    if commerce_hits and not (core_event_hits and result.registration_present):
        result.is_student_participation_possible = False
        result.relevance_label = config.LABEL_NOT_RELEVANT
        result.relevance_reason = (
            "Bước 1: bài là chương trình ưu đãi/khuyến mãi thương mại "
            f"({', '.join(commerce_hits[:3])}), không phải hoạt động rèn luyện để sinh viên tham gia."
        )
        result.rejection_reason = f"Tín hiệu thương mại: {', '.join(commerce_hits[:3])}"
        result.missing_flags = _compute_missing_flags(text, result)
        return

    # Ưu tiên 1b: phủ định rõ ràng hoặc tín hiệu loại trừ mạnh mà KHÔNG có lõi sự kiện
    if is_congratulation or negation_hits or (strong_irrelevant and not core_event_hits):
        result.is_student_participation_possible = False
        result.relevance_label = config.LABEL_NOT_RELEVANT
        reason_hits = (congrats if is_congratulation else (negation_hits or strong_irrelevant))[:3]
        result.relevance_reason = (
            "Bước 1: bài mang tín hiệu quảng bá/chúc mừng/hành chính hoặc phủ định hoạt động "
            f"({', '.join(reason_hits)}), không có hoạt động để sinh viên tham gia."
        )
        result.rejection_reason = f"Tín hiệu loại trừ: {', '.join(reason_hits)}"
        result.missing_flags = _compute_missing_flags(text, result)
        return

    if not activity_hits:
        result.is_student_participation_possible = False
        result.relevance_label = config.LABEL_NOT_RELEVANT
        result.relevance_reason = (
            "Bước 1: không tìm thấy dấu hiệu hoạt động sinh viên tham gia được "
            f"({', '.join(irrelevant_hits[:3]) or 'không có hoạt động'})."
        )
        result.rejection_reason = "Không có dấu hiệu hoạt động sinh viên tham gia được."
        result.missing_flags = _compute_missing_flags(text, result)
        return

    result.is_student_participation_possible = True

    # --- BƯỚC 2: cờ thiếu dữ liệu trên 4 nhóm thông tin ---
    flags = _compute_missing_flags(text, result)
    missing_time = flags["is_missing_time"]
    missing_location = flags["is_missing_location"]
    missing_content = flags["is_missing_content"]
    missing_score = flags["is_missing_score"]
    result.missing_flags = flags

    if missing_time or missing_location or missing_content:
        result.relevance_label = config.LABEL_INSUFFICIENT
        missing_names = []
        if missing_time:
            missing_names.append("Thời gian")
        if missing_location:
            missing_names.append("Địa điểm / hình thức")
        if missing_content:
            missing_names.append("Nội dung")
        result.relevance_reason = (
            "Bước 2: là hoạt động sinh viên tham gia được nhưng THIẾU "
            + ", ".join(missing_names)
            + " → cần bổ sung thông tin trước khi đưa vào lộ trình."
        )
        result.rejection_reason = "Thiếu: " + ", ".join(missing_names)
        return

    # LƯU Ý: trước đây khối này LOẠI bài chỉ vì "có nhắc ĐRL mà không ghi điểm".
    # Đó là hiểu sai bản chất: bài đăng của trường không công bố điểm, nên việc
    # không có điểm KHÔNG phải thiếu sót và KHÔNG được loại hoạt động. Điểm luôn
    # là ước lượng 3–5đ (xem drl/score_estimate.py).

    # --- BƯỚC 2: có đủ nội dung mô tả hoạt động (nhóm 3) không? ---
    #    Có tín hiệu "mời/đăng ký" nhưng không có lõi sự kiện (hội thảo, cuộc thi,
    #    chiến dịch, ngày hội…) và cũng không có địa điểm → nội dung chưa đủ rõ.
    core_event = _any_hit(norm, CORE_EVENT_SIGNALS)
    if not core_event:
        result.relevance_label = config.LABEL_INSUFFICIENT
        result.missing_flags["is_missing_content"] = True
        result.relevance_reason = (
            "Bước 2: bài chỉ mời đăng ký/tham gia nhưng KHÔNG mô tả hoạt động cụ thể "
            "(không có loại hoạt động, không có địa điểm/đơn vị tổ chức) → thiếu Nội dung, "
            "cần bổ sung trước khi đưa vào lộ trình."
        )
        result.rejection_reason = "Thiếu: Nội dung hoạt động cụ thể."
        return

    # --- BƯỚC 2: có căn cứ ĐRL để tính điểm? ---
    if result.expected_score is not None:
        result.relevance_label = config.LABEL_POTENTIAL
        if result.criterion_code:
            result.relevance_reason = (
                "Bước 2: bài đăng nêu điểm ĐRL cụ thể của hoạt động và khớp ngữ cảnh tiêu chí "
                f"{result.criterion_code}, nhưng CHƯA được đơn vị tổ chức/Admin xác nhận "
                "→ chỉ cộng vào Điểm dự kiến (Potential), trạng thái NEEDS_HUMAN_REVIEW."
            )
        else:
            result.relevance_reason = (
                "Bước 2: bài đăng nêu điểm ĐRL cụ thể nhưng chưa xác định được mã tiêu chí "
                "→ chỉ cộng vào Điểm dự kiến (Potential), trạng thái NEEDS_HUMAN_REVIEW."
            )
    else:
        # Bài KHÔNG ghi điểm — đây là trường hợp BÌNH THƯỜNG, không phải thiếu sót.
        # Bài đăng của trường hầu như không bao giờ công bố "hoạt động này bao nhiêu
        # điểm"; điểm chỉ chốt sau khi Phòng CTSV duyệt. Vì vậy hoạt động vẫn được
        # xếp vào diện TIỀM NĂNG với ước lượng 3–5đ, để vào được lộ trình gợi ý.
        result.relevance_label = config.LABEL_POTENTIAL
        if result.criterion_code:
            result.relevance_reason = (
                "Bước 2: hoạt động có thật, tham gia được, khớp ngữ cảnh tiêu chí "
                f"{result.criterion_code}. Bài đăng không nêu điểm cụ thể — điều này là "
                "bình thường vì điểm ĐRL chỉ được chốt sau khi Phòng CTSV duyệt. "
                f"App ước lượng {config.SCORE_ESTIMATE_MIN:g}–{config.SCORE_ESTIMATE_MAX:g}đ."
            )
        else:
            result.relevance_reason = (
                "Bước 2: hoạt động có thật, tham gia được. Bài đăng không nêu điểm và chưa "
                "khớp được mã tiêu chí cụ thể — vẫn đưa vào diện tiềm năng với ước lượng "
                f"{config.SCORE_ESTIMATE_MIN:g}–{config.SCORE_ESTIMATE_MAX:g}đ để sinh viên "
                "cân nhắc."
            )

    if result.registration_deadline:
        try:
            deadline = datetime.strptime(result.registration_deadline, "%Y-%m-%d %H:%M")
            if deadline < datetime.now():
                result.warnings.append(
                    f"Hạn đăng ký ({result.registration_deadline}) đã qua so với thời điểm phân tích."
                )
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# API công khai
# ---------------------------------------------------------------------------
def analyze_post(
    raw_text: str,
    url: str = "",
    criteria_catalog: Optional[Iterable[dict]] = None,
    fallback_title_hint: str = "",
) -> dict[str, Any]:
    """Phân tích 1 bài đăng → dict đúng Schema 1 (JSON đầu ra chuẩn).

    Hàm này không gọi mạng, chạy được 100% offline.
    """
    text = (raw_text or "").strip()
    result = ExtractionResult()
    result.title = clean_title(text) or fallback_title_hint or "Bài đăng chưa có tiêu đề"
    result.description = normalize_ws(text)[:1200]
    result.post_type = detect_post_type(text)

    extract_time_info(text, result)
    extract_location(text, result)
    extract_organizer(text, result)
    extract_score(text, result)
    extract_criterion(text, criteria_catalog, result)
    classify_two_step(text, result)

    citations = []
    if result.criterion_code:
        catalog = {str(c.get("code")): c for c in (criteria_catalog or [])}
        ref = catalog.get(result.criterion_code, {}).get("rule_reference")
        if ref:
            citations.append(ref)
            result.rule_citation = ref

    status = (config.VERIFY_NEEDS_REVIEW
              if result.relevance_label == config.LABEL_POTENTIAL else config.VERIFY_NONE)
    if result.relevance_label == config.LABEL_INSUFFICIENT:
        status = config.VERIFY_NEEDS_REVIEW

    return {
        "post_type": result.post_type,
        "relevance_label": result.relevance_label,
        "relevance_reason": result.relevance_reason,
        "is_student_participation_possible": result.is_student_participation_possible,
        "activity": {
            "title": result.title,
            "organizer": result.organizer,
            "location": result.location,
            "campus": result.campus,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "registration_deadline": result.registration_deadline,
            "expected_score": result.expected_score,
            "criterion_code": result.criterion_code,
        },
        "missing_flags": result.missing_flags,
        "drl_assessment": {
            "status": status,
            "rule_citations": citations,
            "reason": (
                f"Khớp ngữ cảnh tiêu chí {result.criterion_code} qua từ khoá "
                f"{', '.join(result.criterion_keywords)}. Cần xác minh danh sách điểm danh chính thức."
                if result.criterion_code
                else "Chưa tìm thấy căn cứ quy chế tương ứng trong danh mục DRLCriteria."
            ),
        },
        "extraction_meta": {
            "score_context": result.score_context,
            "score_evidence": result.score_evidence,
            "criterion_confidence": round(result.criterion_confidence, 2),
            "criterion_keywords": result.criterion_keywords,
            "post_type_label": POST_TYPE_LABELS.get(result.post_type, result.post_type),
            "registration_present": result.registration_present,
            "drl_mentioned": result.drl_mentioned,
            "assumptions": result.assumptions,
            "warnings": result.warnings,
            "rejection_reason": result.rejection_reason,
            "source_url": url,
        },
    }


# ---------------------------------------------------------------------------
# Gợi ý liên kết cập nhật sự kiện (parent linking)
# ---------------------------------------------------------------------------
def suggest_parent_activity(
    raw_text: str,
    existing_activities: list[dict],
    threshold: float = 0.42,
) -> Optional[dict]:
    """Nếu bài đăng là nhắc hạn / đổi lịch / công bố kết quả, gợi ý sự kiện gốc."""
    if not existing_activities:
        return None
    post_type = detect_post_type(raw_text)
    if post_type not in {"deadline_reminder", "schedule_change", "result_announcement"}:
        return None

    norm_post = strip_accents(raw_text)
    best: Optional[dict] = None
    best_score = 0.0
    for act in existing_activities:
        title = act.get("title") or ""
        if not title or len(title) < 8:
            continue
        title_norm = strip_accents(title)
        ratio = SequenceMatcher(None, norm_post[:2000], title_norm).ratio()
        tokens = [w for w in title_norm.split() if len(w) > 3 and w not in CRITERION_STOPWORDS]
        hit = sum(1 for w in set(tokens) if w in norm_post)
        token_score = hit / max(1, len(set(tokens)))
        score = 0.35 * ratio + 0.65 * token_score
        if score > best_score:
            best_score = score
            best = act
    if best and best_score >= threshold:
        return {
            "activity_id": int(best["id"]),
            "title": best["title"],
            "confidence": round(float(best_score), 2),
            "post_type": post_type,
            "post_type_label": POST_TYPE_LABELS.get(post_type, post_type),
        }
    return None
