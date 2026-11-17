"""Lớp truy cập SQLite cho Smart DRL Assistant (MVP).

- Tự động tạo file ``smart_drl_mvp.db`` và toàn bộ schema khi khởi động.
- Toàn bộ thao tác đi qua ``get_connection()`` để bật FOREIGN KEY + row_factory.
- Các hàm ``insert_*`` / ``update_*`` trả về id để UI dùng lại.

Ghi chú MVP: theo chỉ đạo của giảng viên, hệ thống CHẤP NHẬN dữ liệu trùng lặp
(Skip Complex Deduplication). Mỗi bài đăng vẫn được lưu kèm ``content_hash``
(SHA-256) làm tiền đề nâng cấp chống trùng ở phiên bản sau, nhưng KHÔNG chặn
việc ghi trùng.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from . import config

VN_TZ = timezone(timedelta(hours=7))


# ---------------------------------------------------------------------------
# Kết nối & khởi tạo schema
# ---------------------------------------------------------------------------
def get_connection(db_path: Optional[Path | str] = None) -> sqlite3.Connection:
    """Mở kết nối SQLite (tự tạo file nếu chưa có)."""
    path = Path(db_path) if db_path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def transaction(db_path: Optional[Path | str] = None):
    """Context manager: commit khi thành công, rollback khi lỗi."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
-- Bảng 1: Nguồn dữ liệu (mặc định fanpage OSA HCMUS)
CREATE TABLE IF NOT EXISTS Sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    url               TEXT NOT NULL,
    source_type       TEXT NOT NULL DEFAULT 'facebook_page',
    connection_status TEXT NOT NULL DEFAULT 'MANUAL',
    last_synced_at    TEXT
);

-- Bảng 2: Bài đăng thô thu thập được
CREATE TABLE IF NOT EXISTS SourcePosts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           INTEGER REFERENCES Sources(id),
    external_post_id    TEXT,
    url                 TEXT,
    published_at        TEXT,
    collected_at        TEXT NOT NULL,
    raw_text            TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    fetch_method        TEXT NOT NULL,
    relevance_label     TEXT,
    rejection_reason    TEXT,
    is_demo             INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL
);

-- Bảng 3: Hoạt động bóc tách từ bài đăng
CREATE TABLE IF NOT EXISTS Activities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_post_id        INTEGER REFERENCES SourcePosts(id),
    parent_activity_id    INTEGER REFERENCES Activities(id),
    title                 TEXT NOT NULL,
    description           TEXT,
    organizer             TEXT,
    location              TEXT,
    campus                TEXT,
    start_time            TEXT,
    end_time              TEXT,
    duration_minutes      INTEGER,
    speaker               TEXT,
    start_raw             TEXT,
    end_raw               TEXT,
    registration_deadline TEXT,
    expected_score        REAL,          -- điểm GIỮA của khoảng ước lượng (để xếp hạng)
    expected_score_min    REAL,          -- cận dưới khoảng ước lượng (thường 3)
    expected_score_max    REAL,          -- cận trên khoảng ước lượng (thường 5)
    score_estimate_source TEXT,          -- DEFAULT_RANGE | POST_MENTION | ADMIN_SET
    criterion_code        TEXT,
    relevance_label       TEXT NOT NULL DEFAULT 'EVENT_CANDIDATE',
    verification_status   TEXT NOT NULL DEFAULT 'UNVERIFIED',
    is_missing_time       INTEGER NOT NULL DEFAULT 0,
    is_missing_location   INTEGER NOT NULL DEFAULT 0,
    is_missing_content    INTEGER NOT NULL DEFAULT 0,
    is_missing_score      INTEGER NOT NULL DEFAULT 0,
    ai_explanation        TEXT,
    ai_source             TEXT,
    is_demo               INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL
);

-- Bảng 3b: Hoạt động sinh viên đã đánh dấu HOÀN THÀNH
-- Điểm của hoạt động là DỰ ĐOÁN (xem drl/progress_predict.py); bảng này chỉ ghi
-- "sinh viên xác nhận đã tham gia", không ghi điểm chính thức.
CREATE TABLE IF NOT EXISTS StudentActivityDone (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL,
    activity_id   INTEGER NOT NULL,
    completed_at  TEXT NOT NULL,
    note          TEXT,
    UNIQUE(student_id, activity_id)
);
CREATE INDEX IF NOT EXISTS idx_done_student ON StudentActivityDone(student_id);

-- Bảng 4: Danh mục tiêu chí ĐRL (đồng bộ từ hcmus.drl.vn)
CREATE TABLE IF NOT EXISTS DRLCriteria (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT NOT NULL,
    name             TEXT NOT NULL,
    category         TEXT,
    max_score        REAL NOT NULL DEFAULT 0,
    mandatory        INTEGER NOT NULL DEFAULT 0,
    evidence_required TEXT,
    rule_reference   TEXT,
    is_demo          INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT
);

-- Bảng 5: Hồ sơ sinh viên theo học kỳ
CREATE TABLE IF NOT EXISTS StudentProfile (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id            TEXT NOT NULL,
    full_name             TEXT,
    faculty               TEXT,
    semester              TEXT NOT NULL,
    current_total_score   REAL,          -- NULL = CHƯA đồng bộ điểm (khác 0 điểm)
    score_type            TEXT NOT NULL DEFAULT 'SELF_DECLARED',
    target_score          REAL NOT NULL DEFAULT 0,
    has_detailed_criteria INTEGER NOT NULL DEFAULT 0,
    updated_at            TEXT NOT NULL
);

-- Bảng 6: Tiến độ từng tiêu chí ĐRL của sinh viên
CREATE TABLE IF NOT EXISTS StudentCriterionProgress (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     TEXT NOT NULL,
    semester       TEXT NOT NULL,
    criterion_code TEXT NOT NULL,
    current_score  REAL NOT NULL DEFAULT 0,
    max_score      REAL NOT NULL DEFAULT 0,
    status         TEXT,
    updated_at     TEXT NOT NULL,
    UNIQUE (student_id, semester, criterion_code)
);

-- Bảng 7: Thời khóa biểu đồng bộ từ portal.ctdb.hcmus.edu.vn
CREATE TABLE IF NOT EXISTS StudentSchedule (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL,
    semester      TEXT,
    course_code   TEXT NOT NULL,
    course_name   TEXT,
    day_of_week   TEXT NOT NULL,
    start_time    TEXT NOT NULL,
    end_time      TEXT NOT NULL,
    room          TEXT,
    campus        TEXT,
    synced_from   TEXT NOT NULL DEFAULT 'HCMUS_CHROME_EXTENSION_V1',
    is_demo       INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    -- Hoạt động cá nhân do người dùng tự thêm (đi làm, học thêm, việc bận…)
    event_type    TEXT NOT NULL DEFAULT 'class',
    event_date    TEXT,
    color         TEXT,
    notes         TEXT,
    repeat_until  TEXT
);

-- Bảng 8: Nhật ký thao tác (audit)
CREATE TABLE IF NOT EXISTS AuditLogs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL,
    details    TEXT,
    created_at TEXT NOT NULL
);

-- Bảng phụ (hỗ trợ lưu vết AI):
CREATE TABLE IF NOT EXISTS AIAnalyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     INTEGER REFERENCES SourcePosts(id),
    ai_provider TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_hash      ON SourcePosts(content_hash);
CREATE INDEX IF NOT EXISTS idx_posts_label     ON SourcePosts(relevance_label);
CREATE INDEX IF NOT EXISTS idx_act_label       ON Activities(relevance_label);
CREATE INDEX IF NOT EXISTS idx_act_verify      ON Activities(verification_status);
CREATE INDEX IF NOT EXISTS idx_progress_student ON StudentCriterionProgress(student_id, semester);
CREATE INDEX IF NOT EXISTS idx_schedule_student ON StudentSchedule(student_id);
"""


#: Cột thêm sau khi phát hành – tự động migrate cho DB cũ (không mất dữ liệu).
MIGRATION_COLUMNS = {
    "duration_minutes": "INTEGER",
    "speaker": "TEXT",
    "start_raw": "TEXT",
    "end_raw": "TEXT",
    # --- Điểm hoạt động là ƯỚC LƯỢNG dạng khoảng 3–5đ ---
    "expected_score_min": "REAL",
    "expected_score_max": "REAL",
    "score_estimate_source": "TEXT",
    # --- Thời khóa biểu: cho phép người dùng tự thêm hoạt động cá nhân ---
    "event_type": "TEXT",        # 'class' = môn học | 'personal' = tự thêm
    "event_date": "TEXT",        # YYYY-MM-DD cho hoạt động 1 lần (NULL = lặp theo tuần)
    "color": "TEXT",             # mã màu hiển thị trên lịch
    "notes": "TEXT",             # ghi chú tự do
    "repeat_until": "TEXT",      # ngày kết thúc lặp (NULL = cả học kỳ)
}


def _migrate(conn) -> list[str]:
    """Thêm các cột còn thiếu vào bảng có sẵn. Trả về danh sách cột đã thêm."""
    added = []
    for table in ("Activities", "SourcePosts", "StudentSchedule"):
        try:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:  # noqa: BLE001 – bảng chưa tồn tại
            continue
        for col, coltype in MIGRATION_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
                added.append(f"{table}.{col}")

    # SQLite không ALTER được ràng buộc NOT NULL → dựng lại bảng nếu DB cũ
    # còn NOT NULL trên current_total_score. Không cho NULL thì không phân biệt
    # được "chưa đồng bộ điểm" với "0 điểm thật" — đúng lỗi người dùng báo.
    try:
        info = list(conn.execute("PRAGMA table_info(StudentProfile)"))
    except Exception:  # noqa: BLE001
        return added
    score_col = next((r for r in info if r[1] == "current_total_score"), None)
    if score_col is not None and score_col[3]:  # cột thứ 3 = notnull
        conn.execute("ALTER TABLE StudentProfile RENAME TO _StudentProfile_old")
        conn.execute(
            """CREATE TABLE StudentProfile (
                   id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                   student_id            TEXT NOT NULL,
                   full_name             TEXT,
                   faculty               TEXT,
                   semester              TEXT NOT NULL,
                   current_total_score   REAL,
                   score_type            TEXT NOT NULL DEFAULT 'SELF_DECLARED',
                   target_score          REAL NOT NULL DEFAULT 0,
                   has_detailed_criteria INTEGER NOT NULL DEFAULT 0,
                   updated_at            TEXT NOT NULL
               )"""
        )
        conn.execute(
            """INSERT INTO StudentProfile(id, student_id, full_name, faculty, semester,
                   current_total_score, score_type, target_score, has_detailed_criteria,
                   updated_at)
               SELECT id, student_id, full_name, faculty, semester, current_total_score,
                      score_type, target_score, has_detailed_criteria, updated_at
               FROM _StudentProfile_old"""
        )
        conn.execute("DROP TABLE _StudentProfile_old")
        added.append("StudentProfile.current_total_score → cho phép NULL")
    return added


def init_db(db_path: Optional[Path | str] = None) -> Path:
    """Tạo toàn bộ bảng nếu chưa tồn tại. Trả về đường dẫn DB thực tế.

    DB cũ được migrate tại chỗ để thêm cột mới (giữ nguyên dữ liệu đã có).
    """
    path = Path(db_path) if db_path else config.DB_PATH
    with transaction(path) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate(conn)
    return path


# ---------------------------------------------------------------------------
# Tiện ích chung
# ---------------------------------------------------------------------------
def utcnow_iso() -> str:
    """Thời điểm hiện tại theo múi giờ Việt Nam, chuẩn ISO 8601."""
    return datetime.now(VN_TZ).isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def content_hash(text: str) -> str:
    """SHA-256 của văn bản (đã chuẩn hoá khoảng trắng) – tiền đề chống trùng."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def row_to_dict(row: sqlite3.Row | None) -> dict:
    return dict(row) if row is not None else {}


def query_df(sql: str, params: Iterable[Any] = (), db_path: Optional[Path | str] = None) -> pd.DataFrame:
    """Chạy SELECT và trả về DataFrame (rỗng nếu không có dòng nào)."""
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(sql, conn, params=list(params))
    finally:
        conn.close()


def scalar(sql: str, params: Iterable[Any] = (), db_path: Optional[Path | str] = None, default=None):
    conn = get_connection(db_path)
    try:
        row = conn.execute(sql, list(params)).fetchone()
        return row[0] if row is not None else default
    finally:
        conn.close()


def log_action(action: str, details: str | dict, db_path: Optional[Path | str] = None) -> None:
    """Ghi AuditLogs – mọi thao tác quan trọng đều được lưu vết."""
    if isinstance(details, (dict, list)):
        details = json.dumps(details, ensure_ascii=False)
    with transaction(db_path) as conn:
        conn.execute(
            "INSERT INTO AuditLogs(action, details, created_at) VALUES (?,?,?)",
            (action, details, utcnow_iso()),
        )


def recent_audit(limit: int = 30, db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df(
        "SELECT action, details, created_at FROM AuditLogs ORDER BY id DESC LIMIT ?",
        (limit,),
        db_path,
    )


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
def ensure_default_source(db_path: Optional[Path | str] = None) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM Sources WHERE url = ?", (config.OSA_FACEBOOK_URL,)
        ).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO Sources(name, url, source_type, connection_status, last_synced_at) "
            "VALUES (?,?,?,?,?)",
            (
                "Fanpage OSA HCMUS (Facebook)",
                config.OSA_FACEBOOK_URL,
                "facebook_page",
                "MANUAL_ONLY (Graph API giới hạn quyền)",
                None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def create_source(name: str, url: str, source_type: str = "public_web",
                  connection_status: str = "AUTO_CRAWL",
                  db_path: Optional[Path | str] = None) -> int:
    """Tạo mới (hoặc lấy lại) một nguồn theo URL. Trả về source_id.

    Dùng cho bộ thu thập tự động: mỗi cổng công khai của trường là một nguồn.
    """
    with transaction(db_path) as conn:
        row = conn.execute("SELECT id FROM Sources WHERE url = ?", (url,)).fetchone()
        if row:
            return int(row["id"])
        cur = conn.execute(
            "INSERT INTO Sources(name, url, source_type, connection_status, last_synced_at) "
            "VALUES (?,?,?,?,?)",
            (name, url, source_type, connection_status, utcnow_iso()),
        )
        return int(cur.lastrowid)


def get_sources(db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df("SELECT * FROM Sources ORDER BY id", (), db_path)


def touch_source(source_id: int, db_path: Optional[Path | str] = None) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            "UPDATE Sources SET last_synced_at = ? WHERE id = ?", (utcnow_iso(), source_id)
        )


# ---------------------------------------------------------------------------
# SourcePosts
# ---------------------------------------------------------------------------
def insert_source_post(
    source_id: int,
    raw_text: str,
    url: str | None,
    fetch_method: str,
    external_post_id: str | None = None,
    published_at: str | None = None,
    relevance_label: str | None = None,
    rejection_reason: str | None = None,
    is_demo: bool = False,
    db_path: Optional[Path | str] = None,
) -> int:
    """Lưu 1 bài đăng thô. LUÔN ghi mới (cho phép trùng – đúng chủ trương MVP)."""
    now = utcnow_iso()
    with transaction(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO SourcePosts(source_id, external_post_id, url, published_at,
                   collected_at, raw_text, content_hash, fetch_method, relevance_label,
                   rejection_reason, is_demo, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                source_id,
                external_post_id,
                url,
                published_at,
                now,
                raw_text,
                content_hash(raw_text),
                fetch_method,
                relevance_label,
                rejection_reason,
                1 if is_demo else 0,
                now,
            ),
        )
        return int(cur.lastrowid)


def update_post_label(post_id: int, label: str, reason: str | None = None,
                      db_path: Optional[Path | str] = None) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            "UPDATE SourcePosts SET relevance_label = ?, rejection_reason = ? WHERE id = ?",
            (label, reason, post_id),
        )


def get_posts(db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df("SELECT * FROM SourcePosts ORDER BY id DESC", (), db_path)


def get_post(post_id: int, db_path: Optional[Path | str] = None) -> dict:
    conn = get_connection(db_path)
    try:
        return row_to_dict(conn.execute("SELECT * FROM SourcePosts WHERE id=?", (post_id,)).fetchone())
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------
ACTIVITY_INSERT_COLUMNS = [
    "source_post_id", "parent_activity_id", "title", "description", "organizer",
    "location", "campus", "start_time", "end_time", "duration_minutes",
    "speaker", "start_raw", "end_raw", "registration_deadline",
    "expected_score", "expected_score_min", "expected_score_max", "score_estimate_source",
    "criterion_code", "relevance_label", "verification_status",
    "is_missing_time", "is_missing_location", "is_missing_content", "is_missing_score",
    "ai_explanation", "ai_source", "is_demo",
]


def insert_activity(activity: dict, db_path: Optional[Path | str] = None) -> int:
    """Chèn 1 hoạt động. ``activity`` là dict theo ACTIVITY_INSERT_COLUMNS."""
    payload = {k: activity.get(k) for k in ACTIVITY_INSERT_COLUMNS}
    payload["is_demo"] = 1 if activity.get("is_demo") else 0
    # Cột NOT NULL phải có 0 thay vì None — nếu không SQLite ném IntegrityError
    # ngay khi bộ phân tích không gắn cờ thiếu dữ liệu (đã gặp khi test).
    for flag in ("is_missing_time", "is_missing_location", "is_missing_content",
                 "is_missing_score"):
        payload[flag] = 1 if activity.get(flag) else 0
    if not str(payload.get("relevance_label") or "").strip():
        payload["relevance_label"] = config.LABEL_EVENT_CANDIDATE
    if not str(payload.get("verification_status") or "").strip():
        payload["verification_status"] = config.VERIFY_NONE
    payload["created_at"] = utcnow_iso()
    cols = list(payload.keys())
    placeholders = ",".join(["?"] * len(cols))
    with transaction(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO Activities({','.join(cols)}) VALUES ({placeholders})",
            [payload[c] for c in cols],
        )
        return int(cur.lastrowid)


def update_activity(activity_id: int, updates: dict,
                    db_path: Optional[Path | str] = None) -> None:
    allowed = {k: v for k, v in updates.items() if k in set(ACTIVITY_INSERT_COLUMNS) | {"created_at"}}
    if not allowed:
        return
    sets = ", ".join(f"{k} = ?" for k in allowed)
    with transaction(db_path) as conn:
        conn.execute(f"UPDATE Activities SET {sets} WHERE id = ?",
                     [*allowed.values(), activity_id])


def count_duplicates(db_path: Optional[Path | str] = None) -> dict:
    """Đếm số hoạt động trùng theo ``external_post_id`` hoặc theo tiêu đề+ngày.

    Bản ghi trùng KHÔNG tự động xoá (chính sách MVP: cho phép trùng). Hàm này chỉ
    cung cấp số liệu để người dùng quyết định có gộp hay không.
    """
    conn = get_connection(db_path)
    try:
        by_external = conn.execute(
            """SELECT COALESCE(SUM(c - 1), 0) FROM (
                   SELECT COUNT(*) AS c FROM SourcePosts
                   WHERE external_post_id IS NOT NULL AND external_post_id <> ''
                   GROUP BY external_post_id HAVING c > 1)"""
        ).fetchone()[0]
        by_title = conn.execute(
            """SELECT COALESCE(SUM(c - 1), 0) FROM (
                   SELECT COUNT(*) AS c FROM Activities
                   WHERE is_demo = 0
                   GROUP BY LOWER(TRIM(REPLACE(REPLACE(title, '“', '"'), '”', '"')))
                   HAVING c > 1)"""
        ).fetchone()[0]
        return {
            "dup_by_post_id": int(by_external or 0),
            "dup_by_title": int(by_title or 0),
        }
    finally:
        conn.close()


def merge_duplicates(db_path: Optional[Path | str] = None) -> dict:
    """GỘP hoạt động trùng: giữ bản ghi có ĐIỂM CAO NHẤT trong nhóm, xoá bản còn lại.

    Nhóm xác định theo (tiêu đề chuẩn hoá, ngày bắt đầu). Chỉ xét ``is_demo = 0``
    để không bao giờ đụng vào dữ liệu mẫu. Bản được giữ sẽ được bổ sung các trường
    còn trống từ bản bị xoá (địa điểm, đơn vị, giờ kết thúc) — không ghi đè dữ liệu
    đã có, không bịa thêm.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM Activities WHERE is_demo = 0 ORDER BY id"""
        ).fetchall()
    finally:
        conn.close()
    def _norm_title(value: str) -> str:
        """Chuẩn hoá mạnh để nhận ra cùng một hoạt động do nhiều nguồn đăng."""
        import re
        import unicodedata

        txt = str(value or "").lower()
        txt = unicodedata.normalize("NFD", txt)
        txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
        txt = re.sub(r"[^a-z0-9\s]", " ", txt)
        return re.sub(r"\s+", " ", txt).strip()

    groups: dict[tuple, list] = {}
    for row in rows:
        rec = row_to_dict(row)
        # Nhóm theo TIÊU ĐỀ đã chuẩn hoá (bỏ dấu, bỏ ký tự đặc biệt). Ngày không
        # đưa vào khoá vì cùng một hoạt động có thể bị nguồn này ghi ngày, nguồn
        # kia bỏ trống — nếu ghép cả ngày sẽ bỏ sót trùng.
        key = (_norm_title(rec.get("title")),)
        groups.setdefault(key, []).append(rec)

    n_merged = 0
    n_deleted = 0
    for key, items in groups.items():
        if len(items) < 2:
            continue
        # Giữ bản có điểm cao nhất; hoà thì giữ bản đầy đủ thông tin hơn
        items.sort(key=lambda r: (
            float(r.get("expected_score") or -1),
            sum(1 for f in ("start_time", "end_time", "location", "organizer", "criterion_code")
                if r.get(f)),
        ), reverse=True)
        keep, drop = items[0], items[1:]
        patch = {}
        for field_name in ("start_time", "end_time", "location", "campus",
                           "organizer", "criterion_code", "registration_deadline"):
            if not keep.get(field_name):
                for other in drop:
                    if other.get(field_name):
                        patch[field_name] = other[field_name]
                        break
        if patch:
            update_activity(int(keep["id"]), patch, db_path)
        for other in drop:
            with transaction(db_path) as conn:
                conn.execute("DELETE FROM Activities WHERE id = ?", (int(other["id"]),))
            n_deleted += 1
        n_merged += 1

    log_action("MERGE_DUPLICATES", {"groups": n_merged, "deleted": n_deleted}, db_path)
    return {"groups_merged": n_merged, "rows_deleted": n_deleted}


def purge_expired_real_activities(db_path: Optional[Path | str] = None) -> dict:
    """Xoá các hoạt động THẬT đã kết thúc (chỉ is_demo = 0, giữ nguyên dữ liệu mẫu).

    Dùng khi kho bị lẫn sự kiện cũ do lượt thu thập trước lấy toàn bộ lịch sử.
    Mục không rõ ngày được GIỮ LẠI (không đủ căn cứ để kết luận đã diễn ra).
    """
    from datetime import datetime

    now = datetime.now()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, start_time, end_time FROM Activities WHERE is_demo = 0"
        ).fetchall()
    finally:
        conn.close()

    expired_ids: list[int] = []
    for row in rows:
        rec = {"start_time": row["start_time"], "end_time": row["end_time"]}
        end_raw = str(rec["end_time"] or "") or str(rec["start_time"] or "")
        if len(end_raw) < 10:
            continue
        end_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                end_dt = datetime.strptime(
                    end_raw[:16] if ":" in end_raw else end_raw[:10], fmt)
                break
            except ValueError:
                continue
        if end_dt is not None and end_dt.date() < now.date():
            expired_ids.append(int(row["id"]))

    if expired_ids:
        with transaction(db_path) as conn:
            conn.executemany("DELETE FROM Activities WHERE id = ?",
                             [(i,) for i in expired_ids])
    log_action("PURGE_EXPIRED", {"deleted": len(expired_ids)}, db_path)
    return {"deleted": len(expired_ids)}


def get_activities(include_demo: bool = True,
                   db_path: Optional[Path | str] = None) -> pd.DataFrame:
    sql = """
        SELECT a.*, p.url AS post_url, p.fetch_method, p.collected_at AS post_collected_at,
               p.raw_text
        FROM Activities a
        LEFT JOIN SourcePosts p ON p.id = a.source_post_id
    """
    if not include_demo:
        sql += " WHERE a.is_demo = 0"
    sql += " ORDER BY a.id DESC"
    return query_df(sql, (), db_path)


def get_activity(activity_id: int, db_path: Optional[Path | str] = None) -> dict:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """SELECT a.*, p.url AS post_url, p.fetch_method, p.raw_text
               FROM Activities a LEFT JOIN SourcePosts p ON p.id = a.source_post_id
               WHERE a.id = ?""",
            (activity_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def set_verification_status(activity_id: int, status: str, label: str | None = None,
                            note: str | None = None,
                            db_path: Optional[Path | str] = None) -> None:
    conn = get_connection(db_path)
    try:
        current = row_to_dict(conn.execute(
            "SELECT * FROM Activities WHERE id=?", (activity_id,)
        ).fetchone())
    finally:
        conn.close()
    if not current:
        return
    new_label = label if label else current.get("relevance_label")
    explanation = current.get("ai_explanation") or ""
    if note:
        explanation = (explanation + "\n\n" if explanation else "") + f"[Admin] {note}"
    update_activity(activity_id, {
        "verification_status": status,
        "relevance_label": new_label,
        "ai_explanation": explanation,
    }, db_path)
    log_action("VERIFY_ACTIVITY",
               {"activity_id": activity_id, "status": status, "note": note or ""},
               db_path)


def link_parent_activity(activity_id: int, parent_id: int | None,
                         db_path: Optional[Path | str] = None) -> None:
    update_activity(activity_id, {"parent_activity_id": parent_id}, db_path)
    log_action("LINK_PARENT_ACTIVITY",
               {"activity_id": activity_id, "parent_activity_id": parent_id}, db_path)


# ---------------------------------------------------------------------------
# DRLCriteria
# ---------------------------------------------------------------------------
def upsert_criterion(criteria: dict, db_path: Optional[Path | str] = None) -> None:
    now = utcnow_iso()
    with transaction(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM DRLCriteria WHERE code = ?", (criteria["code"],)
        ).fetchone()
        values = (
            criteria["code"],
            criteria.get("name", ""),
            criteria.get("category", ""),
            float(criteria.get("max_score", 0) or 0),
            1 if criteria.get("mandatory") else 0,
            criteria.get("evidence_required", ""),
            criteria.get("rule_reference", ""),
            1 if criteria.get("is_demo") else 0,
            now,
        )
        if existing:
            conn.execute(
                """UPDATE DRLCriteria SET name=?, category=?, max_score=?, mandatory=?,
                       evidence_required=?, rule_reference=?, is_demo=?, updated_at=?
                   WHERE code=?""",
                (*values[1:], criteria["code"]),
            )
        else:
            conn.execute(
                """INSERT INTO DRLCriteria(code, name, category, max_score, mandatory,
                       evidence_required, rule_reference, is_demo, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                values,
            )


def get_criteria(db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df("SELECT * FROM DRLCriteria ORDER BY code", (), db_path)


def get_criteria_dict(db_path: Optional[Path | str] = None) -> dict[str, dict]:
    df = get_criteria(db_path)
    return {row["code"]: row for row in df.to_dict("records")}


# ---------------------------------------------------------------------------
# StudentProfile
# ---------------------------------------------------------------------------
def _score_or_null(value):
    """Điểm ĐRL: None = CHƯA BIẾT (chưa đồng bộ), 0 = thật sự 0 điểm.

    Phân biệt này rất quan trọng: gói JSON chỉ chứa thời khóa biểu gửi
    ``current_total_score: null``. Nếu ghi thành 0 thì dashboard hiện
    "Điểm hiện tại đã có: 0" trong khi sinh viên thật ra chưa đồng bộ điểm —
    đúng lỗi người dùng báo.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upsert_profile(profile: dict, db_path: Optional[Path | str] = None) -> int:
    """Ghi đè hồ sơ của (student_id, semester); trả về id."""
    now = utcnow_iso()
    sid = str(profile["student_id"]).strip()
    semester = str(profile["semester"]).strip()
    with transaction(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM StudentProfile WHERE student_id=? AND semester=?",
            (sid, semester),
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE StudentProfile SET full_name=?, faculty=?, current_total_score=?,
                       score_type=?, target_score=?, has_detailed_criteria=?, updated_at=?
                   WHERE id=?""",
                (
                    profile.get("full_name", ""),
                    profile.get("faculty", ""),
                    _score_or_null(profile.get("current_total_score")),
                    profile.get("score_type", config.SCORE_TYPE_SELF_DECLARED),
                    float(profile.get("target_score", 0) or 0),
                    1 if profile.get("has_detailed_criteria") else 0,
                    now,
                    int(row["id"]),
                ),
            )
            return int(row["id"])
        cur = conn.execute(
            """INSERT INTO StudentProfile(student_id, full_name, faculty, semester,
                   current_total_score, score_type, target_score, has_detailed_criteria, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                sid,
                profile.get("full_name", ""),
                profile.get("faculty", ""),
                semester,
                _score_or_null(profile.get("current_total_score")),
                profile.get("score_type", config.SCORE_TYPE_SELF_DECLARED),
                float(profile.get("target_score", 0) or 0),
                1 if profile.get("has_detailed_criteria") else 0,
                now,
            ),
        )
        return int(cur.lastrowid)


def get_profile(student_id: str, semester: str | None = None,
                db_path: Optional[Path | str] = None) -> dict:
    conn = get_connection(db_path)
    try:
        if semester:
            row = conn.execute(
                "SELECT * FROM StudentProfile WHERE student_id=? AND semester=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (student_id, semester),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM StudentProfile WHERE student_id=? ORDER BY updated_at DESC LIMIT 1",
                (student_id,),
            ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def list_profiles(db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df(
        "SELECT * FROM StudentProfile ORDER BY updated_at DESC", (), db_path
    )


def latest_profile(db_path: Optional[Path | str] = None) -> dict:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM StudentProfile ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# StudentActivityDone – đánh dấu hoàn thành (đầu vào của tiến độ DỰ ĐOÁN)
# ---------------------------------------------------------------------------
def mark_activity_done(activity_id: int, student_id: str | None = None,
                       note: str | None = None,
                       db_path: Optional[Path | str] = None) -> bool:
    """Đánh dấu sinh viên đã hoàn thành hoạt động. Trả về True nếu thêm mới."""
    sid = str(student_id or "").strip()
    if not sid:
        profile = latest_profile(db_path)
        sid = str(profile.get("student_id") or "").strip()
    if not sid:
        return False
    with transaction(db_path) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM StudentActivityDone WHERE student_id=? AND activity_id=?",
            (sid, int(activity_id)),
        ).fetchone()[0]
        if before:
            return False
        conn.execute(
            """INSERT INTO StudentActivityDone(student_id, activity_id, completed_at, note)
               VALUES (?,?,?,?)""",
            (sid, int(activity_id), utcnow_iso(), (note or "").strip() or None),
        )
    log_action("MARK_DONE", {"student_id": sid, "activity_id": int(activity_id)},
               db_path)
    return True


def unmark_activity_done(activity_id: int, student_id: str | None = None,
                         db_path: Optional[Path | str] = None) -> bool:
    """Bỏ đánh dấu hoàn thành. Trả về True nếu có dòng bị xoá."""
    sid = str(student_id or "").strip()
    if not sid:
        profile = latest_profile(db_path)
        sid = str(profile.get("student_id") or "").strip()
    if not sid:
        return False
    with transaction(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM StudentActivityDone WHERE student_id=? AND activity_id=?",
            (sid, int(activity_id)),
        )
        removed = cur.rowcount > 0
    if removed:
        log_action("UNMARK_DONE", {"student_id": sid, "activity_id": int(activity_id)},
                   db_path)
    return removed


def get_completed_activities(student_id: str | None = None,
                             db_path: Optional[Path | str] = None) -> pd.DataFrame:
    """Các hoạt động đã đánh dấu hoàn thành, kèm điểm dự đoán của hoạt động."""
    sid = str(student_id or "").strip()
    if not sid:
        profile = latest_profile(db_path)
        sid = str(profile.get("student_id") or "").strip()
    if not sid:
        return pd.DataFrame()
    return query_df(
        """SELECT d.activity_id, d.completed_at, d.note,
                  a.title, a.criterion_code, a.start_time, a.end_time,
                  a.expected_score, a.expected_score_min, a.expected_score_max,
                  a.score_estimate_source
           FROM StudentActivityDone d
           JOIN Activities a ON a.id = d.activity_id
           WHERE d.student_id = ?
           ORDER BY d.completed_at DESC""",
        (sid,),
        db_path,
    )


def clear_completed_activities(student_id: str | None = None,
                               db_path: Optional[Path | str] = None) -> int:
    """Xoá toàn bộ dấu hoàn thành của sinh viên. Trả về số dòng đã xoá."""
    sid = str(student_id or "").strip()
    if not sid:
        profile = latest_profile(db_path)
        sid = str(profile.get("student_id") or "").strip()
    if not sid:
        return 0
    with transaction(db_path) as conn:
        cur = conn.execute("DELETE FROM StudentActivityDone WHERE student_id=?", (sid,))
        n = cur.rowcount
    if n:
        log_action("RESET_COMPLETED", {"student_id": sid, "rows": n}, db_path)
    return n


# ---------------------------------------------------------------------------
# StudentCriterionProgress
# ---------------------------------------------------------------------------
def purge_all_demo_data(db_path: Optional[Path | str] = None) -> dict:
    """Dọn SẠCH mọi dấu vết dữ liệu mẫu trong database. Chạy mỗi lần khởi động.

    Vì sao cần: người dùng đã cài bản trước, DB của họ vẫn còn hồ sơ
    ``[DEMO] Nguyễn Văn A``, 11 hoạt động mẫu và bảng tiến độ 61 điểm. Bản mới
    không bao giờ sinh ra chúng nữa, nhưng không tự xoá thì màn hình vẫn hiện
    dữ liệu giả chồng lên dữ liệu thật.

    Trả về số dòng đã xoá theo từng bảng.
    """
    counts = {"activities": 0, "posts": 0, "profiles": 0,
              "progress": 0, "schedule": 0, "analyses": 0}
    with transaction(db_path) as conn:
        # 1. Hoạt động / bài đăng mang cờ is_demo
        cur = conn.execute("DELETE FROM Activities WHERE is_demo = 1")
        counts["activities"] += int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM SourcePosts WHERE is_demo = 1")
        counts["posts"] += int(cur.rowcount or 0)

        # 2. Hồ sơ có tên bắt đầu bằng nhãn demo
        cur = conn.execute(
            "SELECT student_id, semester FROM StudentProfile "
            "WHERE full_name LIKE '[DEMO]%' OR full_name LIKE '%[DEMO]%'"
        )
        demo_profiles = cur.fetchall()
        for sid, sem in demo_profiles:
            cur = conn.execute(
                "DELETE FROM StudentCriterionProgress WHERE student_id = ? AND semester = ?",
                (sid, sem),
            )
            counts["progress"] += int(cur.rowcount or 0)
            cur = conn.execute(
                "DELETE FROM StudentSchedule WHERE student_id = ? AND semester = ?",
                (sid, sem),
            )
            counts["schedule"] += int(cur.rowcount or 0)
            conn.execute(
                "DELETE FROM StudentProfile WHERE student_id = ? AND semester = ?",
                (sid, sem),
            )
            counts["profiles"] += 1

        # 3. Tiến độ / thời khóa biểu còn sót của hồ sơ demo đã xoá
        cur = conn.execute(
            "DELETE FROM StudentCriterionProgress WHERE student_id NOT IN "
            "(SELECT student_id FROM StudentProfile)"
        )
        counts["progress"] += int(cur.rowcount or 0)
        cur = conn.execute(
            "DELETE FROM StudentSchedule WHERE student_id NOT IN "
            "(SELECT student_id FROM StudentProfile)"
        )
        counts["schedule"] += int(cur.rowcount or 0)
        # Bảng AIAnalyses ở vài bản không có cột is_demo → kiểm tra schema trước.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(AIAnalyses)")}
        if "is_demo" in cols:
            cur = conn.execute("DELETE FROM AIAnalyses WHERE is_demo = 1")
            counts["analyses"] += int(cur.rowcount or 0)
    return counts


def purge_demo_activities(db_path: Optional[Path | str] = None) -> dict:
    """Xoá mọi hoạt động/bài đăng MẪU (is_demo = 1). Trả về số dòng đã xoá."""
    counts = {"activities": 0, "posts": 0}
    with transaction(db_path) as conn:
        cur = conn.execute("DELETE FROM Activities WHERE is_demo = 1")
        counts["activities"] = int(cur.rowcount or 0)
        cur = conn.execute("DELETE FROM SourcePosts WHERE is_demo = 1")
        counts["posts"] = int(cur.rowcount or 0)
    return counts


def wipe_demo_profile(db_path: Optional[Path | str] = None) -> dict:
    """Xoá hồ sơ mẫu [DEMO] + tiến độ + TKB mẫu. Trả về số dòng đã xoá.

    Vì sao cần: dữ liệu seed demo là **[DEMO] Nguyễn Văn A – 61 điểm**. Nếu người
    dùng chỉ đồng bộ JSON mới mà không xoá, màn hình vẫn hiện điểm mẫu và rất dễ
    tưởng đó là điểm thật của mình.
    """
    counts = {"profiles": 0, "progress": 0, "schedule": 0}
    with transaction(db_path) as conn:
        demo_ids = [
            str(row[0]) for row in conn.execute(
                "SELECT student_id FROM StudentProfile WHERE full_name LIKE '[DEMO]%' "
                "OR full_name LIKE '%[DEMO]%'"
            )
        ]
        for sid in demo_ids:
            cur = conn.execute("DELETE FROM StudentCriterionProgress WHERE student_id=?", (sid,))
            counts["progress"] += int(cur.rowcount or 0)
            cur = conn.execute("DELETE FROM StudentSchedule WHERE student_id=?", (sid,))
            counts["schedule"] += int(cur.rowcount or 0)
            cur = conn.execute("DELETE FROM StudentProfile WHERE student_id=?", (sid,))
            counts["profiles"] += int(cur.rowcount or 0)
        # TKB mẫu có thể nằm dưới MSSV khác: xoá theo cờ is_demo
        cur = conn.execute("DELETE FROM StudentSchedule WHERE is_demo = 1 OR synced_from LIKE '%DEMO%'")
        counts["schedule"] += int(cur.rowcount or 0)
    return counts


def clear_criterion_progress(student_id: str, semester: str,
                            db_path: Optional[Path | str] = None) -> int:
    """Xoá toàn bộ tiến độ tiêu chí của (student_id, semester). Trả về số dòng đã xoá.

    Dùng khi người dùng đồng bộ một tổng điểm MỚI nhưng gói không kèm bảng tiêu chí:
    giữ lại bảng cũ sẽ khiến tổng điểm và bảng chi tiết **mâu thuẫn nhau**
    (ví dụ tổng = 0 mà mỗi tiêu chí vẫn hiện 18, 10, 6…).
    """
    with transaction(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM StudentCriterionProgress WHERE student_id=? AND semester=?",
            (student_id, semester),
        )
        return int(cur.rowcount or 0)


def ensure_rule_framework(db_path: Optional[Path | str] = None) -> int:
    """Nạp KHUNG QUY CHẾ ĐRL (điểm tối đa từng tiêu chí) nếu danh mục còn trống.

    Vì sao cần tự nạp: extension không đọc được cột "điểm tối đa" trên trang ĐRL,
    nên gói JSON gửi ``max_score = null``. Không có điểm tối đa thì app không thể
    nói tiêu chí nào còn thiếu bao nhiêu — biểu đồ tiến độ sẽ vô nghĩa.
    Khung quy chế KHÔNG phải dữ liệu mẫu: đây là cấu trúc điểm theo quy chế, dùng
    để đối chiếu, không phải hoạt động/hồ sơ giả của sinh viên.
    """
    from . import seed_data

    existing = get_criteria(db_path)
    if not existing.empty:
        return 0
    n = 0
    for crit in seed_data.DEMO_CRITERIA:
        upsert_criterion({**crit, "is_demo": 0}, db_path)
        n += 1
    return n


def replace_criterion_progress(student_id: str, semester: str, rows: list[dict],
                               db_path: Optional[Path | str] = None) -> int:
    """Thay toàn bộ tiến độ tiêu chí của (student_id, semester). Trả về số dòng.

    ``max_score`` để trống (None) là chuyện BÌNH THƯỜNG: extension không đọc được
    cột điểm tối đa khi trang ĐRL không hiển thị nó. Trường hợp đó lấy điểm tối đa
    từ danh mục ``DRLCriteria`` (khung quy chế). Ghi 0 sẽ khiến "còn thiếu =
    max − current" luôn bằng 0 và biểu đồ tiến độ hiện sai hoàn toàn.
    """
    now = utcnow_iso()
    with transaction(db_path) as conn:
        known_max = {
            row["code"]: float(row["max_score"] or 0)
            for row in conn.execute("SELECT code, max_score FROM DRLCriteria")
        }
        conn.execute(
            "DELETE FROM StudentCriterionProgress WHERE student_id=? AND semester=?",
            (student_id, semester),
        )
        records = []
        for r in rows:
            raw_max = r.get("max_score")
            if raw_max is None or (isinstance(raw_max, str) and not raw_max.strip()):
                max_score = known_max.get(r["criterion_code"], 0.0)
            else:
                try:
                    max_score = float(raw_max)
                except (TypeError, ValueError):
                    max_score = known_max.get(r["criterion_code"], 0.0)
            records.append((
                student_id,
                semester,
                r["criterion_code"],
                float(r.get("current_score", 0) or 0),
                max_score,
                r.get("status", ""),
                now,
            ))
        conn.executemany(
            """INSERT INTO StudentCriterionProgress(student_id, semester, criterion_code,
                   current_score, max_score, status, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            records,
        )
    return len(rows)


def get_criterion_progress(student_id: str, semester: str,
                           db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df(
        """SELECT pr.criterion_code, COALESCE(c.name, pr.criterion_code) AS name,
                  COALESCE(c.category, '') AS category,
                  pr.current_score, pr.max_score, pr.status,
                  COALESCE(c.mandatory, 0) AS mandatory
           FROM StudentCriterionProgress pr
           LEFT JOIN DRLCriteria c ON c.code = pr.criterion_code
           WHERE pr.student_id = ? AND pr.semester = ?
           ORDER BY pr.criterion_code""",
        (student_id, semester),
        db_path,
    )


# ---------------------------------------------------------------------------
# StudentSchedule
# ---------------------------------------------------------------------------
def replace_schedule(student_id: str, semester: str, rows: list[dict],
                     synced_from: str = config.SYNC_SOURCE_TAG,
                     is_demo: bool = False,
                     db_path: Optional[Path | str] = None) -> int:
    now = utcnow_iso()
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM StudentSchedule WHERE student_id=?", (student_id,))
        conn.executemany(
            """INSERT INTO StudentSchedule(student_id, semester, course_code, course_name,
                   day_of_week, start_time, end_time, room, campus, synced_from, is_demo, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    student_id,
                    semester,
                    r.get("course_code", ""),
                    r.get("course_name", ""),
                    r.get("day_of_week", ""),
                    r.get("start_time", ""),
                    r.get("end_time", ""),
                    r.get("room", ""),
                    r.get("campus", "NVC"),
                    r.get("synced_from", synced_from),
                    1 if is_demo else 0,
                    now,
                )
                for r in rows
            ],
        )
    return len(rows)


#: Các cột được ghi khi người dùng tự thêm/sửa một mục thời khóa biểu.
SCHEDULE_EDITABLE_COLUMNS = (
    "course_code", "course_name", "day_of_week", "start_time", "end_time",
    "room", "campus", "event_type", "event_date", "color", "notes", "repeat_until",
)

#: Loại mục trên lịch + nhãn tiếng Việt
SCHEDULE_TYPES = {
    "class": "📚 Môn học",
    "personal": "🔒 Việc bận cá nhân",
}
#: Bảng màu cho lịch (dịu mắt, chữ đậm đọc được trên nền sáng)
SCHEDULE_COLORS = {
    "blue": "#1f6feb",
    "green": "#16a34a",
    "amber": "#d97706",
    "red": "#dc2626",
    "purple": "#7c3aed",
    "slate": "#475569",
}


def add_schedule_entry(student_id: str, semester: str, entry: dict,
                       synced_from: str = "USER_MANUAL",
                       db_path: Optional[Path | str] = None) -> int:
    """Thêm 1 mục thời khóa biểu do người dùng tự nhập.

    Ví dụ: đi làm thêm ca tối, lớp học thêm tiếng Anh, việc gia đình bận
    — những thứ trường không biết nhưng ảnh hưởng tới việc chọn hoạt động.
    """
    payload = {k: entry.get(k) for k in SCHEDULE_EDITABLE_COLUMNS}
    payload["event_type"] = payload.get("event_type") or "personal"
    payload["color"] = payload.get("color") or "slate"
    payload["course_code"] = payload.get("course_code") or "PERSONAL"
    payload["course_name"] = payload.get("course_name") or "Việc bận cá nhân"
    with transaction(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO StudentSchedule(
                   student_id, semester, course_code, course_name, day_of_week,
                   start_time, end_time, room, campus, synced_from, is_demo,
                   updated_at, event_type, event_date, color, notes, repeat_until)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                student_id, semester, payload["course_code"], payload["course_name"],
                payload["day_of_week"], payload["start_time"], payload["end_time"],
                payload.get("room"), payload.get("campus"), synced_from, 0,
                utcnow_iso(), payload["event_type"], payload.get("event_date"),
                payload["color"], payload.get("notes"), payload.get("repeat_until"),
            ),
        )
        return int(cur.lastrowid)


def update_schedule_entry(entry_id: int, updates: dict,
                          db_path: Optional[Path | str] = None) -> None:
    """Sửa một mục thời khóa biểu. Chỉ nhận các cột cho phép sửa."""
    allowed = {k: v for k, v in updates.items() if k in SCHEDULE_EDITABLE_COLUMNS}
    if not allowed:
        return
    allowed["updated_at"] = utcnow_iso()
    sets = ", ".join(f"{k} = ?" for k in allowed)
    with transaction(db_path) as conn:
        conn.execute(
            f"UPDATE StudentSchedule SET {sets} WHERE id = ?",
            [*allowed.values(), entry_id],
        )


def delete_schedule_entry(entry_id: int,
                          db_path: Optional[Path | str] = None) -> None:
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM StudentSchedule WHERE id = ?", (entry_id,))


def get_schedule_entry(entry_id: int,
                       db_path: Optional[Path | str] = None) -> Optional[dict]:
    df = query_df("SELECT * FROM StudentSchedule WHERE id = ?", (entry_id,), db_path)
    return df.iloc[0].to_dict() if not df.empty else None


def get_schedule(student_id: str, db_path: Optional[Path | str] = None) -> pd.DataFrame:
    return query_df(
        """SELECT * FROM StudentSchedule WHERE student_id = ?
           ORDER BY CASE day_of_week
                WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2 WHEN 'Wednesday' THEN 3
                WHEN 'Thursday' THEN 4 WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6
                WHEN 'Sunday' THEN 7 ELSE 8 END, start_time""",
        (student_id,),
        db_path,
    )


# ---------------------------------------------------------------------------
# AI analyses
# ---------------------------------------------------------------------------
def save_ai_analysis(post_id: int | None, ai_provider: str, report: dict,
                     db_path: Optional[Path | str] = None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO AIAnalyses(post_id, ai_provider, report_json, created_at) VALUES (?,?,?,?)",
            (post_id, ai_provider, json.dumps(report, ensure_ascii=False), utcnow_iso()),
        )
        return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Thống kê nhanh cho Dashboard
# ---------------------------------------------------------------------------
def dashboard_stats(db_path: Optional[Path | str] = None) -> dict:
    conn = get_connection(db_path)
    try:
        def one(sql, params=()):
            r = conn.execute(sql, params).fetchone()
            return r[0] if r else 0

        return {
            "n_posts": one("SELECT COUNT(*) FROM SourcePosts"),
            "n_activities": one("SELECT COUNT(*) FROM Activities"),
            "n_verified": one("SELECT COUNT(*) FROM Activities WHERE relevance_label='VERIFIED_DRL'"),
            "n_potential": one("SELECT COUNT(*) FROM Activities WHERE relevance_label='POTENTIAL_DRL'"),
            "n_insufficient": one("SELECT COUNT(*) FROM Activities WHERE relevance_label='INSUFFICIENT_INFO'"),
            "n_not_relevant": one("SELECT COUNT(*) FROM Activities WHERE relevance_label='NOT_RELEVANT'"),
            "n_schedule": one("SELECT COUNT(*) FROM StudentSchedule"),
            "n_criteria": one("SELECT COUNT(*) FROM DRLCriteria"),
            "n_completed": one("SELECT COUNT(*) FROM StudentActivityDone"),
        }
    finally:
        conn.close()
