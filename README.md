# Project1 — Smart DRL Assistant

**Hệ thống hỗ trợ quản lý & tối ưu lộ trình Điểm rèn luyện (ĐRL) — Trường ĐH Khoa học Tự nhiên, ĐHQG-HCM**

- **Repository:** https://github.com/ndchieu2524/Project1
- **Môn học/Đồ án:** Course Project (GitHub Group Repository Report)

## 1. Thành viên nhóm & phân công

Mapping theo thứ tự bảng phân công (cần cả nhóm thống nhất lại nếu khác):

| MSSV | Họ tên | GitHub | Thành viên | Phụ trách |
|------|--------|--------|-----------|-----------|
| 25127330 | Nguyễn Đoàn Công Hiếu | [ndchieu2524](https://github.com/ndchieu2524) | TV1 | Kiến trúc hệ thống, Database & Tích hợp (`feat/core-database`) |
| 25127518 | Nguyễn Anh Quang Tiến | [naqtien2511-coder](https://github.com/naqtien2511-coder) | TV2 | Thu thập dữ liệu tự động — Web Crawler & RSS (`feat/web-crawler`) |
| 25127466 | Nguyễn Tiến Phúc | [nguyenphuc090520007-web](https://github.com/nguyenphuc090520007-web) | TV3 | Chrome Extension & đồng bộ dữ liệu cá nhân (`feat/chrome-extension`) |
| 25127302 | Đỗ Tiến Dũng | [25127302-dungdo](https://github.com/25127302-dungdo) | TV4 | NLP/AI & trích xuất thông tin (`feat/nlp-extraction`) |
| 25127043 | Võ Trần Nhật Hạ | [thecelestial-votrannhatha](https://github.com/thecelestial-votrannhatha) | TV5 | Lộ trình tối ưu & Giao diện UI/UX (`feat/pathway-ui`) |

## 2. Kiến trúc tổng thể

```
Chrome Extension (TV3) ─┐
                        ├─► drl/database.py (SQLite) ─► drl/pathway.py (TV5) ─► app.py (Streamlit, 6 tab)
Web Crawler (TV2) ──────┘          ▲                                                      ▲
                     drl/nlp_engine.py (TV4) ─────────────────────────────────────────────┘
                        drl/config.py · drl/seed_data.py — quy chế ĐRL & dữ liệu mẫu (TV1)
```

Luồng dữ liệu một chiều: *Nguồn → SourcePosts (raw) → NLP → Activities (chuẩn hóa) → Pathway → UI*. Mỗi thành viên sở hữu nhóm tệp riêng, hạn chế conflict trên `main`.

## 3. Cấu trúc thư mục

```
.
├── app.py                  # Điểm khởi động Streamlit, tích hợp 6 tab (TV1)
├── requirements.txt        # Dependencies runtime
├── requirements-dev.txt    # + pytest
├── run.bat / run.sh        # Khởi động 1 lệnh (Windows / Linux-macOS)
├── .gitignore              # Bỏ venv/, data/*.db, node_modules/ ...
├── data/                   # smart_drl.db (tự tạo khi chạy, KHÔNG commit)
├── drl/
│   ├── config.py           # TV1 — cấu hình + quy chế 5 Điều ĐRL chuẩn hóa
│   ├── database.py         # TV1 — lược đồ SQLite + content_hash khử trùng lặp
│   ├── seed_data.py        # TV1 — seed nguồn + hoạt động mẫu
│   ├── ui_sidebar.py       # TV1 — sidebar dùng chung
│   ├── ui_tab1_dashboard.py … ui_tab6_ml.py   # STUB — TV2/TV4/TV5 hoàn thiện
│   ├── crawler.py, ui_tab_crawler.py          # TV2 — (chưa có)
│   ├── nlp_engine.py, event_details.py, ai_engine.py, ml_benchmark.py  # TV4 — (chưa có)
│   └── pathway.py          # TV5 — (chưa có) thuật toán tối ưu (networkx)
├── chrome_plugin/          # TV3 — manifest.json, content.js, popup.js, popup.html
├── devtests/               # TV3 — scan_real_portal.js, run_all.js
└── tests/                  # TV5 — test_core.py
```

## 4. Cài đặt & chạy

```bash
# Windows
run.bat

# Linux / macOS
./run.sh
```

Hoặc thủ công:

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m drl.seed_data        # nạp dữ liệu mẫu
streamlit run app.py           # http://localhost:8501
```

Kiểm thử trước khi tạo PR (quy tắc merge của nhóm):

```bash
python -m pytest tests/test_core.py
```

## 5. Hiện trạng triển khai (cập nhật 2026-11-16)

| TV | Hạng mục | File | Trạng thái |
|----|----------|------|------------|
| TV1 | Lược đồ SQLite `sources`, `source_posts`, `activities` (+ `student_profile`, `schedule_events`, `student_activities`) | `drl/database.py` | ✅ Xong |
| TV1 | Khử trùng lặp bằng `content_hash` (SHA-256 trên text chuẩn hóa) | `drl/database.py` | ✅ Xong |
| TV1 | Chuẩn hóa quy chế 5 Điều (+ Điều 9 khuyến khích) ĐRL HCMUS + dữ liệu mẫu | `drl/config.py`, `drl/seed_data.py` | ✅ Xong |
| TV1 | Tích hợp 6 tab Streamlit (defensive import + placeholder) & đóng gói | `app.py`, `run.bat`, `run.sh` | ✅ Xong |
| TV2 | 5 adapter crawl (ctsv_api, hcmus_events, hcmus_posts, fit_news, fb_rss) | `drl/crawler.py`, `drl/ui_tab_crawler.py` | ⏳ Chờ |
| TV3 | Chrome Extension bóc tách DOM + devtests | `chrome_plugin/`, `devtests/` | ⏳ Chờ |
| TV4 | Bóc tách thời gian/địa điểm + phân loại tiêu chí ĐRL | `drl/nlp_engine.py` | ⏳ Chờ |
| TV5 | Thuật toán tối ưu lộ trình + UI 6 tab + unit test | `drl/pathway.py`, `drl/ui_tab*.py` | ⏳ Chờ |

## 6. Quy chế ĐRL HCMUS — nguồn chuẩn hóa

- **Văn bản:** Quyết định số **1124/QĐ-KHTN-CTSV** ngày 22/8/2016, Hiệu trưởng Trường ĐH KHTN, ĐHQG-HCM — *Quy chế đánh giá kết quả rèn luyện sinh viên hệ chính quy*.
- **6 nhóm tiêu chí** (`drl/config.py → DRL_COMPONENTS`): Điều 4 Học tập (20đ) · Điều 5 Nội quy (25đ) · Điều 6 Chính trị-Xã hội-VH-VN-TT (20đ) · Điều 7 Quan hệ cộng đồng (25đ) · Điều 8 Cán bộ lớp/đoàn thể (10đ) · Điều 9 Khuyến khích (20đ, tối đa 100đ).
- **Phân loại** (`classify_rating`): ≥90 Xuất sắc · ≥80 Tốt · ≥65 Khá · ≥50 Trung bình · ≥35 Yếu · <35 Kém.
- ⚠️ Cần TV1 đối chiếu lại với bản Quy chế đang hiệu lực của Phòng CTSV trước khi báo cáo chính thức; cập nhật một điểm duy nhất là `drl/config.py`.

## 7. Data Contract (đầu ra giữa các module)

- **Crawler/Extension → Database/NLP:** `dict` với các trường bắt buộc `title`, `content`, `url`, `published_at`, `organizer` (chuẩn `CrawledPost`).
- **NLP → Pathway:** thời gian chuẩn `YYYY-MM-DD HH:MM`; `criterion_code` phải thuộc `config.VALID_CRITERION_CODES` (ràng buộc trong `insert_activity`).

## 8. Git Workflow

- `main`: chỉ code ổn định. Mỗi TV làm nhánh riêng: `feat/core-database` · `feat/web-crawler` · `feat/chrome-extension` · `feat/nlp-extraction` · `feat/pathway-ui`.
- Không commit `venv/`, `data/*.db`, `node_modules/` (đã có `.gitignore`).
- Trước khi merge vào `main`: chạy `pytest tests/test_core.py`.
