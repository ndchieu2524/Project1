"""Bóc tách chi tiết hoạt động từ văn bản thông báo – CÓ CĂN CỨ, KHÔNG ĐOÁN.

Triết lý: thà để trống còn hơn điền sai. Mọi trường bóc ra đều kèm câu gốc
(``start_raw``/``end_raw``) để người dùng đối chiếu với bài đăng.

Vì sao phải tách riêng "hạn nộp hồ sơ" khỏi "ngày diễn ra":
    Trong văn bản CTSV, phần lớn ngày xuất hiện là **hạn chót** (nộp hồ sơ,
    đóng phí, khiếu nại), không phải ngày tổ chức. Bóc bừa mọi ngày sẽ khiến
    hệ thống lưu một buổi workshop với ngày hết hạn nộp form.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Nhãn section tiếng Việt
# ---------------------------------------------------------------------------
#: Từ khoá cho biết một dòng/dòng con là NGÀY DIỄN RA
WHEN_LABELS = (
    "thời gian", "thoi gian", "thời điểm", "thoi diem", "khi nào",
    "lịch tổ chức", "ngày tổ chức", "ngày diễn ra", "diễn ra vào",
    "thời gian tổ chức", "thời gian diễn ra", "khai mạc",
)
#: Từ khoá cho biết đó là HẠN CHÓT (không phải ngày diễn ra)
DEADLINE_LABELS = (
    "hạn", "han nộp", "hạn chót", "hạn cuối", "deadline", "đăng ký trước",
    "trước ngày", "hạn đăng ký", "thời hạn", "hạn nộp", "nộp hồ sơ",
    "đóng phí", "khiếu nại", "thắc mắc", "nhận hồ sơ", "xác nhận tham gia",
)
SPEAKER_LABELS = (
    "báo cáo viên", "bao cao vien", "diễn giả", "dien gia", "người trình bày",
    "nguoi trinh bay", "thuyết trình viên", "khách mời", "speaker",
    "người chia sẻ", "giảng viên hướng dẫn",
)
DURATION_LABELS = ("thời lượng", "thoi luong", "kéo dài", "duration")
#: Cụm từ đứng NGAY TRƯỚC một ngày, đánh dấu đó là hạn chót (không phải ngày diễn ra)
#: Cụm từ cho biết ngày đó là mốc THỦ TỤC, không phải ngày hoạt động diễn ra
NON_EVENT_PHRASES = (
    "tích lũy", "tich luy", "tích luỹ", "tinh diem", "tính điểm", "xét duyệt",
    "có hiệu lực", "hiệu lực từ", "áp dụng từ", "năm học 20", "học kỳ", "hoc ky",
    "tính từ", "tinh tu", "được tính", "duoc tinh", "thời gian học", "thời gian làm việc",
)
DEADLINE_PHRASES = (
    "đến hết ngày", "den het ngay", "hạn cuối", "han cuoi", "hạn chót",
    "chậm nhất", "cham nhat", "trước ngày", "truoc ngay", "trước 17g00 ngày",
    "hạn nộp", "han nop", "hạn đăng ký", "thời hạn nộp", "nhận hồ sơ đến",
    "đăng ký đến hết", "đến ngày", "nộp trước", "hoàn tất trước",
)
#: "Hình thức" KHÔNG phải địa điểm (nó nói trực tuyến/trực tiếp, không phải nơi chốn)
LOCATION_LABELS = ("địa điểm", "dia diem", "tổ chức tại", "diễn ra tại", "địa chỉ")
#: Giá trị không phải địa điểm dù đứng sau nhãn
NOT_A_PLACE = (
    "cho vay", "hình thức", "không có tài sản", "trực tuyến", "online", "moodle",
)

# ---------------------------------------------------------------------------
# Regex ngày giờ tiếng Việt
# ---------------------------------------------------------------------------
DATE_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
#: 13g30, 13h30, 13:30, 8 giờ 30, 13g
TIME_RE = re.compile(r"\b(\d{1,2})\s*[gh:]\s*(\d{2})?\b", re.IGNORECASE)
TIME_PREFIX_RE = re.compile(r"(?:lúc|vao|vào|từ|tu)\s*$", re.IGNORECASE)


def _strip_html(raw: str) -> str:
    """Bỏ HTML, giữ xuống dòng ở mỗi thẻ khối để không dính chữ."""
    text = re.sub(r"<(br|/p|/div|/li|/tr|/h\d)[^>]*>", "\n", str(raw or ""),
                  flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _norm(s: str) -> str:
    """Chuẩn hoá để so khớp nhãn: bỏ dấu, viết thường, gộp khoảng trắng."""
    import unicodedata

    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", s).strip().lower()


def _label_kind(text: str) -> Optional[str]:
    """Xác định một dòng là nhãn gì: 'deadline' | 'when' | 'speaker' | 'duration' | None."""
    n = _norm(text)
    if not n or len(n) > 90:  # dòng quá dài là văn xuôi, không phải nhãn
        return None
    # Hạn chót phải kiểm tra TRƯỚC: "thời hạn nộp hồ sơ" chứa cả "thời gian"
    if any(k in n for k in DEADLINE_LABELS):
        return "deadline"
    if any(k in n for k in SPEAKER_LABELS):
        return "speaker"
    if any(k in n for k in DURATION_LABELS):
        return "duration"
    if any(k in n for k in WHEN_LABELS):
        return "when"
    return None


def _parse_date(match) -> Optional[str]:
    d, m, y = (int(x) for x in match.groups())
    try:
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_time(text: str) -> tuple[Optional[str], Optional[int]]:
    """Trả về (giờ:phút, số phút bị làm tròn) nếu tìm thấy giờ hợp lệ."""
    for m in TIME_RE.finditer(text):
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            # "5g" (gam) là bẫy: chỉ nhận khi không có phút mà trước đó có "lúc/vào/từ"
            tail = text[max(0, m.start() - 8):m.start()]
            if not m.group(2) and not TIME_PREFIX_RE.search(tail):
                continue
            return f"{hour:02d}:{minute:02d}", 0
    return None, None


#: Khoảng NGÀY không ghi năm ở mốc đầu: "23/11 – 30/11/2026", "1/12 - 5/12/2026"
_DATE_RANGE_RE = re.compile(
    r"(\d{1,2})[/\-.](\d{1,2})\s*(?:đến|den|->|–|—|-|tới|toi)\s*"
    r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"
)

#: Hai mốc giờ nối nhau bằng gạch/chữ: "13g30 - 16g30", "8g00–11g30", "từ 7g đến 9g"
_TIME_PAIR_RE = re.compile(
    r"(\d{1,2})\s*[gh:]\s*(\d{2})?\s*(?:đến|den|->|–|—|-|tới|toi)\s*(\d{1,2})\s*[gh:]\s*(\d{2})?",
    re.IGNORECASE,
)


def _valid_clock(hour: str, minute: Optional[str]) -> Optional[str]:
    h = int(hour)
    m = int(minute) if minute else 0
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def _split_time_range(text: str) -> tuple[Optional[str], Optional[str]]:
    """Tìm khoảng giờ dạng 'từ 13g30 đến 16g30' hoặc '14g00 - 16g00'.

    Dùng regex bắt CẶP giờ thay vì tách chuỗi theo dấu '-' — tách chuỗi sẽ hỏng
    với dòng kiểu "- Thời gian: 14g00 - 16g00 …" (dấu '-' ở đầu dòng).
    """
    m = _TIME_PAIR_RE.search(text)
    if not m:
        return None, None
    start = _valid_clock(m.group(1), m.group(2))
    end = _valid_clock(m.group(3), m.group(4))
    return start, end


def extract_speaker(text: str) -> tuple[str, str]:
    """Trả về (tên diễn giả, câu gốc). Rỗng nếu không tìm thấy."""
    lines = [ln.strip(" .;:-–—\u00a0") for ln in _strip_html(text).split("\n")]
    for idx, line in enumerate(lines):
        if _label_kind(line) != "speaker" or len(line) > 90:
            continue
        if not _starts_with_label(line, SPEAKER_LABELS):
            continue
        # Dạng 1: "4. Báo cáo viên: BS.CKII. Trần Quang Khải – Bệnh viện..."
        if ":" in line:
            value = line.split(":", 1)[1].strip(" .;-\u00a0")
            if len(value) > 3:
                return value[:300], line[:300]
        # Dạng 2: nhãn đứng riêng, giá trị ở dòng kế tiếp
        for nxt in lines[idx + 1: idx + 4]:
            if not nxt:
                continue
            if _label_kind(nxt):
                break
            if len(nxt) > 3:
                return nxt.strip(" .;-\u00a0")[:300], f"{line} {nxt}"[:300]
            break
    return "", ""


def extract_duration(text: str) -> tuple[Optional[int], str]:
    """Số phút, suy ra TỪ VĂN BẢN (thời lượng ghi rõ hoặc khoảng giờ đầu–cuối)."""
    clean = _strip_html(text)
    for line in clean.split("\n"):
        if _label_kind(line) != "duration":
            continue
        m = re.search(r"(\d{1,3})\s*(?:phút|phut|giờ|gio|tiếng|tieng)", _norm(line))
        if m:
            val = int(m.group(1))
            if "gio" in _norm(line) or "tieng" in _norm(line):
                val *= 60
            if 5 <= val <= 600:
                return val, line.strip()[:200]
    # Khoảng giờ trong cùng một dòng: "từ 13g30 đến 16g30"
    for line in clean.split("\n"):
        if len(line) > 240:
            continue
        if _label_kind(line) not in ("when", None):
            continue
        s, e = _split_time_range(line)
        if s and e:
            try:
                t0 = datetime.strptime(s, "%H:%M")
                t1 = datetime.strptime(e, "%H:%M")
            except ValueError:
                continue
            mins = int((t1 - t0).total_seconds() // 60)
            if 0 < mins <= 600:
                return mins, line.strip()[:200]
    return None, ""


def extract_when(text: str) -> dict:
    """Bóc ngày/giờ diễn ra, LOẠI TRỪ hạn nộp hồ sơ.

    Trả về dict: start_time, end_time, start_raw, end_raw, deadline, confidence,
    và ``rejected`` (danh sách ngày bị loại vì là hạn chót) để người dùng kiểm tra.
    """
    out = {
        "start_time": "", "end_time": "", "start_raw": "", "end_raw": "",
        "deadline": "", "confidence": "none", "rejected": [],
    }
    clean = _strip_html(text)
    lines = [ln.strip(" .;:-\u00a0") for ln in clean.split("\n") if ln.strip()]

    when_lines: list[tuple[str, str]] = []   # (dòng, ngữ cảnh nhãn)
    deadline_dates: list[str] = []

    def _deadline_hits(line: str) -> list[str]:
        """Ngày nằm sau cụm 'đến hết ngày', 'hạn cuối', 'chậm nhất'…"""
        found = []
        norm = _norm(line)
        for m in DATE_RE.finditer(line):
            before = norm[max(0, m.start() - 45):m.start()]
            if any(ph in before for ph in DEADLINE_PHRASES):
                d = _parse_date(m)
                if d:
                    found.append(d)
        return found

    for idx, line in enumerate(lines):
        kind = _label_kind(line)
        if kind == "deadline":
            for m in DATE_RE.finditer(line):
                d = _parse_date(m)
                if d:
                    deadline_dates.append(d)
                break
            continue
        # Ngày đi kèm cụm "hạn chót" nằm trong câu dài (không phải nhãn)
        hits = _deadline_hits(line)
        if hits and kind != "when":
            deadline_dates.extend(h for h in hits if h not in deadline_dates)
            continue
        if kind == "when":
            when_lines.append((line, line))
            for nxt in lines[idx + 1: idx + 3]:
                if _label_kind(nxt) or DATE_RE.search(nxt) is None:
                    break
                when_lines.append((nxt, line))
        elif DATE_RE.search(line) and re.search(
            r"(diễn ra|tổ chức|khai mạc|bắt đầu)", _norm(line)
        ):
            when_lines.append((line, line))

    # Loại các dòng chỉ nói về mốc thủ tục (tích luỹ, hiệu lực, xét duyệt…)
    when_lines = [
        (line, ctx) for line, ctx in when_lines
        if not any(ph in _norm(line) for ph in NON_EVENT_PHRASES)
    ]

    if not when_lines:
        out["deadline"] = deadline_dates[0] if deadline_dates else ""
        return out

    # Nhãn tường minh ("Thời gian: …") đáng tin hơn câu văn chỉ chứa ngày
    when_lines.sort(key=lambda item: 0 if _label_kind(item[0]) == "when" else 1)

    dates: list[tuple[str, str]] = []
    for line, ctx in when_lines:
        # Ưu tiên hiểu dạng KHOẢNG NGÀY "23/11 – 30/11/2026" trước
        rng = _DATE_RANGE_RE.search(line)
        if rng:
            d1, m1, d2, m2, y = (int(x) for x in rng.groups())
            try:
                first = datetime(y, m1, d1).strftime("%Y-%m-%d")
                last = datetime(y, m2, d2).strftime("%Y-%m-%d")
            except ValueError:
                first = last = ""
            if first and last and first <= last:
                src = f"{ctx} → {line}"[:300]
                for day in (first, last):
                    if day not in [x[0] for x in dates]:
                        dates.append((day, src))
                continue
        for m in DATE_RE.finditer(line):
            d = _parse_date(m)
            if d and d not in [x[0] for x in dates]:
                dates.append((d, f"{ctx} → {line}"[:300]))

    # Loại ngày trùng hạn chót nếu có ngày khác thay thế được
    kept = [x for x in dates if x[0] not in deadline_dates]
    if kept:
        out["rejected"] = [x for x in dates if x[0] in deadline_dates]
        dates = kept
    if not dates:
        out["deadline"] = deadline_dates[0] if deadline_dates else ""
        return out

    start_day, start_source = dates[0]
    end_day = dates[1][0] if len(dates) > 1 else start_day

    start_clock = end_clock = None
    for line, _ctx in when_lines:
        r_start, r_end = _split_time_range(line)
        if r_start:
            start_clock, end_clock = r_start, r_end
            break
    if not start_clock:
        for line, _ctx in when_lines:
            start_clock, _ = _parse_time(line)
            if start_clock:
                break

    out["start_time"] = f"{start_day} {start_clock}" if start_clock else f"{start_day} 00:00"
    if end_clock and end_clock != start_clock:
        out["end_time"] = f"{end_day} {end_clock}"
    elif end_day != start_day:
        out["end_time"] = f"{end_day} 23:59"
    # Chốt chặn: nếu ngày kết thúc TRƯỚC ngày bắt đầu thì đó là bóc nhầm —
    # bỏ end_time chứ không lưu dữ liệu vô lý.
    if out["end_time"] and out["end_time"][:10] < out["start_time"][:10]:
        out["end_time"] = ""
        out["end_raw"] = ""
    out["start_raw"] = start_source
    if len(dates) > 1:
        out["end_raw"] = dates[1][1]
    out["deadline"] = deadline_dates[0] if deadline_dates else ""
    out["confidence"] = "high" if start_clock else "medium"
    return out


#: Trường BẮT BUỘC phải có trước khi được lưu vào kho.
REQUIRED_FIELDS = ("title", "start_time", "location", "organizer")

#: Nhãn hiển thị tiếng Việt cho từng trường bắt buộc.
FIELD_LABELS = {
    "title": "tiêu đề",
    "start_time": "ngày diễn ra",
    "location": "địa điểm",
    "organizer": "đơn vị tổ chức",
    "speaker": "người thuyết trình",
}


def required_report(record: dict) -> tuple[bool, list[str]]:
    """Kiểm tra điều kiện "đủ thông tin mới cho vào kho".

    Trả về (đủ_chưa, danh_sách_trường_thiếu). Không bao giờ tự bịa giá trị.
    """
    missing = []
    for field in REQUIRED_FIELDS:
        if not str(record.get(field) or "").strip():
            missing.append(field)
    return (not missing), missing


#: Nhãn phải nằm ở ĐẦU dòng (bỏ số thứ tự "3." hoặc gạch "-" phía trước).
_LABEL_AT_START_RE = re.compile(r"^[\s\-•*\d.)]{0,6}\s*", re.UNICODE)


def _starts_with_label(line: str, labels: tuple[str, ...]) -> bool:
    """Nhãn có ở đầu dòng không? Tránh nhầm câu "Không có địa điểm" thành nhãn."""
    stripped = _LABEL_AT_START_RE.sub("", line)
    n = _norm(stripped)
    return any(n.startswith(_norm(lbl)) for lbl in labels)


def extract_location(text: str) -> tuple[str, str]:
    """Bóc địa điểm từ section "Địa điểm:" / "Tổ chức tại:" → (địa điểm, câu gốc).

    Chỉ nhận khi nhãn đứng ở ĐẦU dòng — nếu không, câu văn như
    "Không có địa điểm" sẽ bị hiểu nhầm là nhãn và lấy nhầm dòng khác.
    """
    lines = [ln.strip(" .;:-–—\u00a0") for ln in _strip_html(text).split("\n")]
    for idx, line in enumerate(lines):
        if len(line) > 200 or not _starts_with_label(line, LOCATION_LABELS):
            continue
        if ":" in line:
            value = line.split(":", 1)[1].strip(" .;- ")
            if len(value) > 4 and not any(b in _norm(value) for b in NOT_A_PLACE):
                return value[:300], line[:300]
            continue
        for nxt in lines[idx + 1: idx + 3]:
            if not nxt:
                continue
            if _label_kind(nxt) or nxt.endswith(":"):
                break
            if len(nxt) > 4 and not any(b in _norm(nxt) for b in NOT_A_PLACE):
                return nxt.strip(" .;- ")[:300], f"{line} {nxt}"[:300]
            break
    return "", ""
