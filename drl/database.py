# -*- coding: utf-8 -*-
"""
drl/database.py — TẦNG DỮ LIỆU SQLite của Smart DRL Assistant
=============================================================
Chủ trì: Thành viên 1 (Kiến trúc hệ thống, Database & Tích hợp)

Trách nhiệm:
  1. Lược đồ SQLite: Sources, SourcePosts, Activities (+ các bảng hỗ trợ tối thiểu:
     StudentProfile, ScheduleEvent, StudentActivity)
  2. Cơ chế KHỬ TRÙNG LẶP hoạt động/bài viết bằng content_hash (SHA-256)
  3. Toàn bộ hàm truy cập dữ liệu dùng chung cho các module khác
     (crawler.py, nlp_engine.py, pathway.py, ui_tab*.py)

Quy ước:
  - Thời gian lưu dạng ISO-8601 chuỗi 'YYYY-MM-DD HH:MM' (giờ địa phương).
  - content_hash = sha256(normalize(title)|normalize(url|organizer|start_time))
    → cùng một hoạt động cào từ 2 nguồn vẫn chỉ lưu 1 bản ghi.
  - Mọi hàm ghi đều idempotent: gọi lại không tạo bản ghi trùng.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from drl.config import DB_PATH, SQLITE_CONNECT_ARGS, VALID_CRITERION_CODES

# ---------------------------------------------------------------------------
# KẾT NỐI & KHỞI TẠO
# ---------------------------------------------------------------------------

def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Mở kết nối SQLite (bật foreign_keys, WAL, row_factory = dict-like)."""
    path = Path(db_path) if db_path else Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), **SQLITE_CONNECT_ARGS)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


SCHEMA_SQL = """
-- ============================================================
-- SOURCES — các nguồn tin cào dữ liệu (CTSV, HCMUS, FIT, FB RSS...)
-- ============================================================
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,          -- mã nguồn, khớp config.CRAWL_SOURCES[].code
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'HTML',  -- API | HTML | RSS
    adapter     TEXT NOT NULL DEFAULT '',      -- adapter trong drl/crawler.py
    url         TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- ============================================================
-- SOURCE_POSTS — bài viết RAW cào về từ nguồn (trước khi NLP xử lý)
-- ============================================================
CREATE TABLE IF NOT EXISTS source_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    title         TEXT NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    published_at  TEXT,                        -- 'YYYY-MM-DD HH:MM' hoặc NULL nếu nguồn không ghi
    organizer     TEXT NOT NULL DEFAULT '',
    content_hash  TEXT NOT NULL UNIQUE,        -- sha256 — CHỐT khử trùng lặp
    raw_json      TEXT,                        -- toàn bộ payload gốc (debug)
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_source_posts_source    ON source_posts(source_id);
CREATE INDEX IF NOT EXISTS idx_source_posts_published ON source_posts(published_at);

-- ============================================================
-- ACTIVITIES — hoạt động ĐRL đã CHUẨN HÓA (sau NLP / đối chiếu quy chế)
-- ============================================================
CREATE TABLE IF NOT EXISTS activities (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id               INTEGER REFERENCES source_posts(id) ON DELETE SET NULL,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    url                   TEXT NOT NULL DEFAULT '',
    organizer             TEXT NOT NULL DEFAULT '',
    start_time            TEXT,                -- 'YYYY-MM-DD HH:MM' (chuẩn YYYY-MM-DD HH:MM theo Data Contract)
    end_time              TEXT,
    registration_deadline TEXT,
    location              TEXT NOT NULL DEFAULT '',
    criterion_code        TEXT,                -- mã tiêu chí hợp lệ theo config.VALID_CRITERION_CODES
    drl_points            REAL NOT NULL DEFAULT 0,
    content_hash          TEXT NOT NULL UNIQUE, -- sha256 — CHỐT khử trùng lặp
    is_active             INTEGER NOT NULL DEFAULT 1,
    extra_json            TEXT,                -- dữ liệu mở rộng (vai trò BTVC/CTV, giải thưởng...)
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_criterion ON activities(criterion_code);
CREATE INDEX IF NOT EXISTS idx_activities_start     ON activities(start_time);
CREATE INDEX IF NOT EXISTS idx_activities_post      ON activities(post_id);

-- ============================================================
-- STUDENT_PROFILE — hồ sơ sinh viên (singleton, id luôn = 1)
-- ============================================================
CREATE TABLE IF NOT EXISTS student_profile (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    student_id      TEXT NOT NULL DEFAULT '',   -- MSSV
    full_name       TEXT NOT NULL DEFAULT '',
    class_name      TEXT NOT NULL DEFAULT '',
    cohort          TEXT NOT NULL DEFAULT '',   -- khóa (vd 'K2022')
    faculty         TEXT NOT NULL DEFAULT '',
    current_semester TEXT NOT NULL DEFAULT '',  -- vd '2026-HK1'
    target_drl      INTEGER NOT NULL DEFAULT 90,
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- SCHEDULE_EVENTS — thời khóa biểu (CTĐB) để tránh trùng lịch
-- ============================================================
CREATE TABLE IF NOT EXISTS schedule_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code   TEXT NOT NULL DEFAULT '',
    course_name   TEXT NOT NULL DEFAULT '',
    day_of_week   INTEGER NOT NULL CHECK (day_of_week BETWEEN 2 AND 8),  -- 2=Thứ 2 ... 8=Chủ nhật
    period_start  INTEGER NOT NULL CHECK (period_start BETWEEN 1 AND 20),
    period_end    INTEGER NOT NULL CHECK (period_end BETWEEN 1 AND 20),
    room          TEXT NOT NULL DEFAULT '',
    semester      TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedule_semester ON schedule_events(semester);

-- ============================================================
-- STUDENT_ACTIVITIES — sinh viên đã/sẽ tham gia hoạt động (phục vụ UI + pathway)
-- ============================================================
CREATE TABLE IF NOT EXISTS student_activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id   INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'planned'
                  CHECK (status IN ('planned', 'registered', 'done', 'skipped')),
    points_earned REAL NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE (activity_id)
);
"""


def init_db(db_path: Path | str | None = None) -> None:
    """Tạo toàn bộ bảng + index nếu chưa có. An toàn khi gọi nhiều lần."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


# ---------------------------------------------------------------------------
# CONTENT_HASH — CƠ CHẾ KHỬ TRÙNG LẶP
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_text(text: Any) -> str:
    """Chuẩn hóa chuỗi trước khi băm: NFC, thường hóa, bỏ dấu câu, gộp khoảng trắng."""
    if text is None:
        return ""
    s = unicodedata.normalize("NFC", str(text)).strip().lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def compute_content_hash(*parts: Any) -> str:
    """SHA-256 của các phần đã chuẩn hóa, nối bằng dấu '|'."""
    payload = "|".join(normalize_text(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def post_hash(title: str, url: str = "", published_at: str | None = None) -> str:
    """Hash cho source_posts. Ưu tiên (title + url); thiếu url thì dùng published_at."""
    return compute_content_hash(title, url or published_at or "")


def activity_hash(title: str, organizer: str = "", start_time: str | None = None, url: str = "") -> str:
    """Hash cho activities. Ưu tiên (title + organizer + start_time); thiếu thì dùng url."""
    key = start_time or url
    return compute_content_hash(title, organizer, key)


# ---------------------------------------------------------------------------
# TIỆN ÍCH CHUNG
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


# ---------------------------------------------------------------------------
# SOURCES
# ---------------------------------------------------------------------------

def upsert_source(source: dict, db_path: Path | str | None = None) -> int:
    """Thêm hoặc cập nhật nguồn theo `code`. Trả về id."""
    now = now_iso()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources (code, name, type, adapter, url, is_active, created_at, updated_at)
            VALUES (:code, :name, :type, :adapter, :url, :is_active, :now, :now)
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name, type=excluded.type, adapter=excluded.adapter,
                url=excluded.url, is_active=excluded.is_active, updated_at=excluded.updated_at
            """,
            {
                "code": source["code"],
                "name": source["name"],
                "type": source.get("type", "HTML"),
                "adapter": source.get("adapter", ""),
                "url": source.get("url", ""),
                "is_active": 1 if source.get("is_active", True) else 0,
                "now": now,
            },
        )
        conn.commit()
        row = conn.execute("SELECT id FROM sources WHERE code = ?", (source["code"],)).fetchone()
        return int(row["id"])


def list_sources(active_only: bool = False, db_path: Path | str | None = None) -> list[dict]:
    sql = "SELECT * FROM sources"
    if active_only:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY id"
    with get_connection(db_path) as conn:
        return _rows_to_dicts(conn.execute(sql).fetchall())


def get_source_by_code(code: str, db_path: Path | str | None = None) -> dict | None:
    with get_connection(db_path) as conn:
        return _row_to_dict(conn.execute("SELECT * FROM sources WHERE code = ?", (code,)).fetchone())


# ---------------------------------------------------------------------------
# SOURCE_POSTS (RAW)
# ---------------------------------------------------------------------------

def insert_source_post(post: dict, db_path: Path | str | None = None) -> tuple[int, bool]:
    """
    Chèn bài viết thô. Trả về (id, created).
    created=False nếu bài đã tồn tại (trùng content_hash) — KHÔNG tạo bản ghi mới.
    """
    source_id = post.get("source_id")
    if source_id is None:
        src = get_source_by_code(post.get("source_code", ""), db_path)
        if src is None:
            raise ValueError(f"Không tìm thấy nguồn với code={post.get('source_code')!r}")
        source_id = src["id"]

    title = (post.get("title") or "").strip()
    if not title:
        raise ValueError("source_post.title không được rỗng")

    url = (post.get("url") or "").strip()
    published_at = _empty_to_none(post.get("published_at"))
    content_hash = post.get("content_hash") or post_hash(title, url, published_at)

    raw_json = post.get("raw_json")
    if raw_json is not None and not isinstance(raw_json, str):
        raw_json = json.dumps(raw_json, ensure_ascii=False)

    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO source_posts
                (source_id, title, content, url, published_at, organizer, content_hash, raw_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id, title, (post.get("content") or "").strip(), url, published_at,
                (post.get("organizer") or "").strip(), content_hash, raw_json, now_iso(),
            ),
        )
        conn.commit()
        if cur.rowcount == 1:
            return int(cur.lastrowid), True
        row = conn.execute("SELECT id FROM source_posts WHERE content_hash = ?", (content_hash,)).fetchone()
        return int(row["id"]), False


def list_source_posts(limit: int = 100, db_path: Path | str | None = None) -> list[dict]:
    with get_connection(db_path) as conn:
        return _rows_to_dicts(
            conn.execute(
                "SELECT p.*, s.code AS source_code, s.name AS source_name "
                "FROM source_posts p JOIN sources s ON s.id = p.source_id "
                "ORDER BY COALESCE(p.published_at, p.created_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        )


# ---------------------------------------------------------------------------
# ACTIVITIES (CHUẨN HÓA)
# ---------------------------------------------------------------------------

def insert_activity(activity: dict, db_path: Path | str | None = None) -> tuple[int, bool]:
    """
    Chèn hoạt động ĐRL đã chuẩn hóa. Trả về (id, created).
    Khử trùng theo content_hash; nếu activity_id tương ứng post_id đã có thì trả về bản ghi cũ.
    criterion_code (nếu có) BẮT BUỘC thuộc config.VALID_CRITERION_CODES (Data Contract với TV4).
    """
    title = (activity.get("title") or "").strip()
    if not title:
        raise ValueError("activity.title không được rỗng")

    criterion_code = _empty_to_none(activity.get("criterion_code"))
    if criterion_code and criterion_code not in VALID_CRITERION_CODES:
        raise ValueError(
            f"criterion_code={criterion_code!r} không hợp lệ. "
            "Xem config.VALID_CRITERION_CODES hoặc để trống chờ TV4 gán."
        )

    organizer = (activity.get("organizer") or "").strip()
    start_time = _empty_to_none(activity.get("start_time"))
    url = (activity.get("url") or "").strip()
    content_hash = activity.get("content_hash") or activity_hash(title, organizer, start_time, url)

    extra_json = activity.get("extra_json")
    if extra_json is not None and not isinstance(extra_json, str):
        extra_json = json.dumps(extra_json, ensure_ascii=False)

    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO activities
                (post_id, title, description, url, organizer, start_time, end_time,
                 registration_deadline, location, criterion_code, drl_points,
                 content_hash, is_active, extra_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity.get("post_id"), title, (activity.get("description") or "").strip(),
                url, organizer, start_time, _empty_to_none(activity.get("end_time")),
                _empty_to_none(activity.get("registration_deadline")),
                (activity.get("location") or "").strip(), criterion_code,
                float(activity.get("drl_points") or 0), content_hash,
                1 if activity.get("is_active", True) else 0, extra_json, now_iso(),
            ),
        )
        conn.commit()
        if cur.rowcount == 1:
            return int(cur.lastrowid), True
        row = conn.execute("SELECT id FROM activities WHERE content_hash = ?", (content_hash,)).fetchone()
        return int(row["id"]), False


def list_activities(
    criterion_code: str | None = None,
    only_upcoming: bool = False,
    active_only: bool = True,
    limit: int | None = None,
    db_path: Path | str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM activities WHERE 1=1"
    params: list[Any] = []
    if active_only:
        sql += " AND is_active = 1"
    if criterion_code:
        sql += " AND criterion_code = ?"
        params.append(criterion_code)
    if only_upcoming:
        sql += " AND (start_time IS NULL OR start_time >= ?)"
        params.append(datetime.now().strftime("%Y-%m-%d 00:00"))
    sql += " ORDER BY COALESCE(start_time, created_at) ASC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection(db_path) as conn:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())


def count_activities(db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0])


def get_activity_by_hash(content_hash: str, db_path: Path | str | None = None) -> dict | None:
    with get_connection(db_path) as conn:
        return _row_to_dict(conn.execute("SELECT * FROM activities WHERE content_hash = ?", (content_hash,)).fetchone())


# ---------------------------------------------------------------------------
# STUDENT_PROFILE (singleton)
# ---------------------------------------------------------------------------

def get_student_profile(db_path: Path | str | None = None) -> dict:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM student_profile WHERE id = 1").fetchone()
        return dict(row) if row else {
            "id": 1, "student_id": "", "full_name": "", "class_name": "", "cohort": "",
            "faculty": "Khoa Công nghệ Thông tin", "current_semester": "", "target_drl": 90,
        }


def save_student_profile(profile: dict, db_path: Path | str | None = None) -> None:
    now = now_iso()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO student_profile
                (id, student_id, full_name, class_name, cohort, faculty, current_semester, target_drl, updated_at)
            VALUES (1, :student_id, :full_name, :class_name, :cohort, :faculty, :current_semester, :target_drl, :now)
            ON CONFLICT(id) DO UPDATE SET
                student_id=excluded.student_id, full_name=excluded.full_name,
                class_name=excluded.class_name, cohort=excluded.cohort,
                faculty=excluded.faculty, current_semester=excluded.current_semester,
                target_drl=excluded.target_drl, updated_at=excluded.updated_at
            """,
            {
                "student_id": profile.get("student_id", ""),
                "full_name": profile.get("full_name", ""),
                "class_name": profile.get("class_name", ""),
                "cohort": profile.get("cohort", ""),
                "faculty": profile.get("faculty", "Khoa Công nghệ Thông tin"),
                "current_semester": profile.get("current_semester", ""),
                "target_drl": int(profile.get("target_drl", 90)),
                "now": now,
            },
        )
        conn.commit()


# ---------------------------------------------------------------------------
# SCHEDULE_EVENTS (thời khóa biểu — tránh trùng lịch)
# ---------------------------------------------------------------------------

def add_schedule_event(event: dict, db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO schedule_events
                (course_code, course_name, day_of_week, period_start, period_end, room, semester, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("course_code", ""), event.get("course_name", ""),
                int(event["day_of_week"]), int(event["period_start"]), int(event["period_end"]),
                event.get("room", ""), event.get("semester", ""), now_iso(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_schedule_events(semester: str | None = None, db_path: Path | str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM schedule_events", []
    if semester:
        sql += " WHERE semester = ?"
        params.append(semester)
    sql += " ORDER BY day_of_week, period_start"
    with get_connection(db_path) as conn:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())


def clear_schedule_events(semester: str | None = None, db_path: Path | str | None = None) -> int:
    with get_connection(db_path) as conn:
        if semester:
            cur = conn.execute("DELETE FROM schedule_events WHERE semester = ?", (semester,))
        else:
            cur = conn.execute("DELETE FROM schedule_events")
        conn.commit()
        return cur.rowcount


# ---------------------------------------------------------------------------
# STUDENT_ACTIVITIES — ghi nhận tham gia hoạt động
# ---------------------------------------------------------------------------

def mark_activity(activity_id: int, status: str = "planned", points_earned: float = 0.0,
                  note: str = "", db_path: Path | str | None = None) -> None:
    now = now_iso()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO student_activities (activity_id, status, points_earned, note, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                status=excluded.status, points_earned=excluded.points_earned,
                note=excluded.note, updated_at=excluded.updated_at
            """,
            (activity_id, status, float(points_earned), note, now, now),
        )
        conn.commit()


def list_student_activities(db_path: Path | str | None = None) -> list[dict]:
    with get_connection(db_path) as conn:
        return _rows_to_dicts(
            conn.execute(
                "SELECT sa.*, a.title, a.criterion_code, a.drl_points, a.start_time "
                "FROM student_activities sa JOIN activities a ON a.id = sa.activity_id "
                "ORDER BY sa.updated_at DESC"
            ).fetchall()
        )


# ---------------------------------------------------------------------------
# THỐNG KÊ (phục vụ UI & kiểm thử)
# ---------------------------------------------------------------------------

def get_db_stats(db_path: Path | str | None = None) -> dict:
    with get_connection(db_path) as conn:
        stats = {}
        for table in ("sources", "source_posts", "activities", "schedule_events", "student_activities"):
            stats[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        stats["activities_by_component"] = _rows_to_dicts(
            conn.execute(
                "SELECT COALESCE(substr(criterion_code, 1, 6), 'CHUA_GAN') AS component, COUNT(*) AS n "
                "FROM activities GROUP BY component ORDER BY component"
            ).fetchall()
        )
        return stats
