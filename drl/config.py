"""Cấu hình trung tâm cho Smart DRL Assistant (MVP).

Mọi con số / nhãn nghiệp vụ được gom về đây để tránh "magic string"
rải rác trong code và để Admin dễ chỉnh sửa.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Đường dẫn
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent.parent          # .../smart_drl_assistant
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("SMART_DRL_DB", str(DATA_DIR / "smart_drl_mvp.db")))

# ---------------------------------------------------------------------------
# Nguồn dữ liệu
# ---------------------------------------------------------------------------
OSA_FACEBOOK_URL = "https://www.facebook.com/osa.hcmus"
PORTAL_CTDB_URL = "https://portal.ctdb.hcmus.edu.vn/Login?returnurl=%2fforget-password"
DRL_PORTAL_URL = "https://hcmus.drl.vn/"
SYNC_SOURCE_TAG = "HCMUS_CHROME_EXTENSION_V1"

# ---------------------------------------------------------------------------
# Nhãn phân loại 2 bước (Bước 1: có phải hoạt động tham gia được?
#                              Bước 2: có căn cứ quy chế ĐRL? )
# ---------------------------------------------------------------------------
LABEL_NOT_RELEVANT = "NOT_RELEVANT"
LABEL_INSUFFICIENT = "INSUFFICIENT_INFO"
LABEL_EVENT_CANDIDATE = "EVENT_CANDIDATE"
LABEL_POTENTIAL = "POTENTIAL_DRL"
LABEL_VERIFIED = "VERIFIED_DRL"

RELEVANCE_LABELS = [
    LABEL_NOT_RELEVANT,
    LABEL_INSUFFICIENT,
    LABEL_EVENT_CANDIDATE,
    LABEL_POTENTIAL,
    LABEL_VERIFIED,
]

LABEL_DESCRIPTIONS = {
    LABEL_NOT_RELEVANT: (
        "Tin quảng bá, chúc mừng, tuyển dụng không gắn ĐRL, thông báo hành chính chung. "
        "→ Loại khỏi gợi ý; lưu ở tab 'Bài không liên quan' để Admin rà soát."
    ),
    LABEL_INSUFFICIENT: (
        "Có dấu hiệu là hoạt động sinh viên nhưng khuyết Thời gian / Địa điểm / "
        "Nội dung / Điểm kỳ vọng. → Bật cờ cảnh báo đỏ, yêu cầu bổ sung trước khi vào lộ trình."
    ),
    LABEL_EVENT_CANDIDATE: (
        "Hoạt động có thật, sinh viên tham gia được nhưng chưa có thông tin ĐRL. "
        "→ Hiển thị nhãn 'Chưa rõ quyền lợi ĐRL'."
    ),
    LABEL_POTENTIAL: (
        "Khớp ngữ cảnh một tiêu chí trong quy chế nhưng chưa được xác nhận chính thức. "
        "→ Chỉ cộng vào cột 'Điểm dự kiến (Potential)', trạng thái NEEDS_HUMAN_REVIEW."
    ),
    LABEL_VERIFIED: (
        "Đã có trích dẫn quy chế hợp lệ từ hcmus.drl.vn hoặc Admin đã duyệt. "
        "→ Cộng vào 'Điểm đã xác minh (Verified)' và ưu tiên trong lộ trình."
    ),
}

LABEL_ICONS = {
    LABEL_NOT_RELEVANT: "🚫",
    LABEL_INSUFFICIENT: "⚠️",
    LABEL_EVENT_CANDIDATE: "🔍",
    LABEL_POTENTIAL: "🟡",
    LABEL_VERIFIED: "✅",
}

# ---------------------------------------------------------------------------
# Trạng thái xác minh ĐRL
# ---------------------------------------------------------------------------
VERIFY_NONE = "UNVERIFIED"
VERIFY_NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"
VERIFY_ADMIN_APPROVED = "ADMIN_APPROVED"
VERIFY_RULE_CITED = "RULE_CITED"
VERIFICATION_STATUSES = [
    VERIFY_NONE,
    VERIFY_NEEDS_REVIEW,
    VERIFY_ADMIN_APPROVED,
    VERIFY_RULE_CITED,
]

# ---------------------------------------------------------------------------
# Nguồn điểm hồ sơ sinh viên
# ---------------------------------------------------------------------------
SCORE_TYPE_OFFICIAL = "OFFICIAL_SYNCED"       # Chính thức từ hcmus.drl.vn
SCORE_TYPE_MANUAL = "MANUAL_ESTIMATED"        # Tự tính tạm thời
SCORE_TYPE_SELF_DECLARED = "SELF_DECLARED"    # Tự khai chưa xác minh
SCORE_TYPE_LABELS = {
    SCORE_TYPE_OFFICIAL: "Chính thức trên hcmus.drl.vn",
    SCORE_TYPE_MANUAL: "Tự tính tạm thời",
    SCORE_TYPE_SELF_DECLARED: "Tự khai chưa xác minh",
}

# ---------------------------------------------------------------------------
# Thời gian di chuyển giữa các cơ sở (phút) – dùng cho đồ thị lộ trình
# ---------------------------------------------------------------------------
CAMPUSES = ["NVC", "Linh Trung", "Online"]
CAMPUS_LABELS = {
    "NVC": "Cơ sở Nguyễn Văn Cừ (Q.5)",
    "Linh Trung": "Cơ sở Linh Trung (Thủ Đức)",
    "Online": "Trực tuyến (Online)",
}
DEFAULT_TRAVEL_MINUTES = 30
TRAVEL_MATRIX = {
    ("NVC", "NVC"): 0,
    ("Linh Trung", "Linh Trung"): 0,
    ("Online", "Online"): 0,
    ("NVC", "Linh Trung"): 45,
    ("Linh Trung", "NVC"): 45,
    ("NVC", "Online"): 0,
    ("Online", "NVC"): 0,
    ("Linh Trung", "Online"): 0,
    ("Online", "Linh Trung"): 0,
}
CAMPUS_ALIASES = [
    ("linh trung", "Linh Trung"),
    ("linh trung", "Linh Trung"),
    ("linh trung", "Linh Trung"),
    ("nguyen van cu", "NVC"),
    ("nguyễn văn cừ", "NVC"),
    ("nvc", "NVC"),
    ("q.5", "NVC"),
    ("quận 5", "NVC"),
    ("online", "Online"),
    ("trực tuyến", "Online"),
    ("truc tuyen", "Online"),
    ("zoom", "Online"),
    ("google meet", "Online"),
    ("ms teams", "Online"),
]

# ---------------------------------------------------------------------------
# Thông điệp cảnh báo quan trọng
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Điểm ĐRL của một HOẠT ĐỘNG: luôn là ƯỚC LƯỢNG, không phải sự thật
# ---------------------------------------------------------------------------
# Bài đăng của trường/Đoàn/Khoa gần như KHÔNG BAO GIỜ ghi "hoạt động này được
# bao nhiêu điểm rèn luyện". Điểm chỉ được chốt sau khi có danh sách điểm danh
# và Hội đồng/Phòng CTSV duyệt trên hcmus.drl.vn. Thông lệ mỗi hoạt động được
# cộng khoảng 3–5 điểm tuỳ quy mô và tiêu chí.
#
# Vì vậy app KHÔNG được coi điểm trích từ bài đăng là sự thật, và cũng KHÔNG
# được loại hoạt động chỉ vì bài đăng không ghi điểm.
SCORE_ESTIMATE_MIN = 3.0          # điểm ước lượng thấp nhất cho 1 hoạt động
SCORE_ESTIMATE_MAX = 5.0          # điểm ước lượng cao nhất cho 1 hoạt động
SCORE_ESTIMATE_SOURCE_DEFAULT = "DEFAULT_RANGE"
SCORE_ESTIMATE_SOURCE_POST = "POST_MENTION"
SCORE_ESTIMATE_SOURCE_ADMIN = "ADMIN_SET"
SCORE_ESTIMATE_LABELS = {
    SCORE_ESTIMATE_SOURCE_DEFAULT: "Ước lượng mặc định của app (3–5đ)",
    SCORE_ESTIMATE_SOURCE_POST: "Bài đăng có nhắc điểm – vẫn chỉ là ước lượng",
    SCORE_ESTIMATE_SOURCE_ADMIN: "Admin nhập tay",
}
SCORE_ESTIMATE_NOTE = (
    "Điểm của một hoạt động **luôn là ước lượng** (thường 3–5đ), vì bài đăng của "
    "trường không công bố điểm chính thức. Điểm chính thức chỉ có sau khi Phòng CTSV "
    "duyệt trên hcmus.drl.vn."
)

WARNING_TOTAL_SCORE_ONLY = (
    "Chưa có bảng điểm theo từng tiêu chí, nên hệ thống không biết tiêu chí nào "
    "còn thiếu. Mở **hcmus.drl.vn** → bấm **Quét trang** ở Chrome Extension để lấy "
    "bảng điểm chi tiết, rồi xuất `hcmus_sync.json` nạp lại."
)
WARNING_SCORE_NOT_SYNCED = (
    "Hồ sơ chưa có **tổng điểm ĐRL** (gói JSON vừa nạp chỉ chứa thời khóa biểu). "
    "Đây không phải 0 điểm – hệ thống chỉ chưa biết điểm của bạn. Mở **hcmus.drl.vn** "
    "và quét lại để lấy điểm."
)

DISCLAIMER = (
    "Tiến độ trong app là **DỰ ĐOÁN** (3–5đ mỗi hoạt động), không phải điểm chính thức. "
    "Điểm chính thức do Phòng Công tác Sinh viên – HCMUS quyết định theo quy chế hiện hành "
    "trên hcmus.drl.vn."
)

DEMO_TAG = "[DEMO]"

CAMPUS_KEYS = ["NVC", "Linh Trung", "Online"]
WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_VI = {
    "Monday": "Thứ 2",
    "Tuesday": "Thứ 3",
    "Wednesday": "Thứ 4",
    "Thursday": "Thứ 5",
    "Friday": "Thứ 6",
    "Saturday": "Thứ 7",
    "Sunday": "Chủ nhật",
}
