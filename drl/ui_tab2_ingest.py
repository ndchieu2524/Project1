"""TAB 2 – Thu thập & Bóc tách Bài đăng OSA HCMUS (MVP Core).

Hỗ trợ đủ 4 phương thức nạp dữ liệu hợp lệ theo đề bài:
    (a) Dán URL + nội dung bài đăng công khai từ OSA
    (b) Nhập hàng loạt qua CSV/Excel
    (c) Tải ảnh poster để trích xuất văn bản (OCR qua Gemini Vision; nếu chưa có
        API Key → hướng dẫn dán văn bản thủ công, KHÔNG giả vờ đã OCR)

Mỗi bài đăng đều được lưu kèm: source_url, external_post_id, published_at,
collected_at, content_hash, fetch_method. Theo chủ trương MVP, dữ liệu trùng
lặp được PHÉP ghi vào DB (chỉ lưu hash để nâng cấp chống trùng sau này).
"""
from __future__ import annotations

import itertools
import re

import pandas as pd
import streamlit as st

from . import config, database, event_details, nlp_engine, score_estimate
from . import ui_common as ui
from .ai_engine import analyze_post_with_ai


# ---------------------------------------------------------------------------
# Lưu 1 bài đăng đã phân tích
# ---------------------------------------------------------------------------
def _save_report(raw_text: str, url: str, fetch_method: str, report: dict,
                 published_at: str | None = None,
                 external_post_id: str | None = None) -> tuple[int, int]:
    """Ghi SourcePost + Activity. Trả về (post_id, activity_id)."""
    source_id = database.ensure_default_source()
    meta = report.get("extraction_meta") or {}
    post_id = database.insert_source_post(
        source_id=source_id,
        raw_text=raw_text,
        url=url or config.OSA_FACEBOOK_URL,
        fetch_method=fetch_method,
        external_post_id=external_post_id,
        published_at=published_at,
        relevance_label=report["relevance_label"],
        rejection_reason=meta.get("rejection_reason"),
    )
    act = report["activity"]
    flags = report["missing_flags"]
    activity_id = database.insert_activity({
        "source_post_id": post_id,
        "parent_activity_id": None,
        "title": act.get("title") or "Bài đăng chưa có tiêu đề",
        "description": raw_text[:1200],
        "organizer": act.get("organizer"),
        "location": act.get("location"),
        "campus": act.get("campus"),
        "start_time": act.get("start_time"),
        "end_time": act.get("end_time"),
        "registration_deadline": act.get("registration_deadline"),
        # Điểm hoạt động = ƯỚC LƯỢNG dạng khoảng 3–5đ (xem drl/score_estimate.py)
        **score_estimate.estimate_fields(act),
        "criterion_code": act.get("criterion_code"),
        "relevance_label": report["relevance_label"],
        "verification_status": report["drl_assessment"].get("status", config.VERIFY_NONE),
        "is_missing_time": int(bool(flags.get("is_missing_time"))),
        "is_missing_location": int(bool(flags.get("is_missing_location"))),
        "is_missing_content": int(bool(flags.get("is_missing_content"))),
        # Mọi hoạt động đều có ước lượng điểm → không còn khái niệm "thiếu điểm"
        "is_missing_score": 0,
        "ai_explanation": (
            f"{report['drl_assessment'].get('reason', '')}\n\n"
            f"**Vì sao nhãn này?** {report['relevance_reason']}"
        ),
        "ai_source": (report.get("meta") or {}).get("ai_source"),
    })
    database.save_ai_analysis(post_id, (report.get("meta") or {}).get("ai_source", "LOCAL"),
                              report)
    database.update_post_label(post_id, report["relevance_label"],
                               meta.get("rejection_reason"))
    database.touch_source(source_id)
    return post_id, activity_id


_REPORT_RENDER_COUNTER = itertools.count(1)


def _est_range(act: dict) -> tuple:
    """Khoảng ước lượng điểm của hoạt động (điểm luôn là ước lượng, không chắc chắn)."""
    est = score_estimate.estimate_for_activity(act)
    return est["min"], est["max"]


def _render_report(report: dict, raw_text: str, url: str, *,
                   allow_link: bool = True, key_prefix: str | None = None) -> None:
    """Hiển thị báo cáo JSON Schema 1 + bảng tóm tắt 4 nhóm thông tin."""
    act = report["activity"]
    flags = report["missing_flags"]
    meta = report.get("extraction_meta") or {}
    ai_meta = report.get("meta") or {}

    st.markdown(
        f"### {nlp_engine.POST_TYPE_LABELS.get(report['post_type'], report['post_type'])} "
        f"&nbsp; {ui.label_badge(report['relevance_label'])}",
        unsafe_allow_html=True,
    )
    st.write(report["relevance_reason"])
    if ai_meta.get("ai_error"):
        ui.note_box(f"Nguồn phân tích: **{ai_meta.get('ai_source')}** · Lỗi AI: {ai_meta['ai_error']}")
    else:
        ui.note_box(f"Nguồn phân tích: **{ai_meta.get('ai_source', 'LOCAL_NLP')}**")

    info_rows = [
        ("1️⃣ Thời gian diễn ra", f"{act.get('start_time') or '—'} → {act.get('end_time') or '—'}",
         flags.get("is_missing_time")),
        ("1️⃣ Hạn đăng ký", act.get("registration_deadline") or "—", False),
        ("2️⃣ Địa điểm / Cơ sở",
         f"{act.get('location') or '—'} ({config.CAMPUS_LABELS.get(act.get('campus'), 'chưa rõ cơ sở')})",
         flags.get("is_missing_location")),
        ("3️⃣ Nội dung", act.get("title") or "—", flags.get("is_missing_content")),
        ("3️⃣ Đơn vị tổ chức", act.get("organizer") or "—", False),
        ("4️⃣ Điểm ĐRL kỳ vọng",
         f"~{score_estimate.format_range(*_est_range(act))} (ước lượng)",
         False),
        ("4️⃣ Mã tiêu chí dự kiến", act.get("criterion_code") or "—", False),
    ]
    df = pd.DataFrame(info_rows, columns=["Nhóm thông tin", "Giá trị trích xuất", "Trạng thái"])
    # Dùng CHỮ + emoji thay vì tô nền màu: tô màu bằng pandas Styler dễ cho ra
    # chữ trắng trên nền hồng (không đọc được) khi theme tối.
    df["Trạng thái"] = df["Trạng thái"].apply(lambda v: "⚠️ Còn thiếu" if v else "✅ Đã có")
    st.dataframe(df, width="stretch", hide_index=True, height=280)

    if meta.get("assumptions"):
        st.caption("Giả định đã dùng (minh bạch, cần xác minh): " + "; ".join(meta["assumptions"]))
    if meta.get("warnings"):
        ui.warn_box(" · ".join(meta["warnings"]))
    if meta.get("score_evidence"):
        st.caption(f"Trích dẫn căn cứ điểm: “{meta['score_evidence']}”")

    with st.expander("🧾 JSON Schema 1 – đầu ra chuẩn của AI/NLP Post Analyzer"):
        clean = {k: v for k, v in report.items() if k != "meta"}
        st.json(clean, expanded=2)

    # Khoá widget phải duy nhất kể cả khi cùng một báo cáo được hiển thị ở 2 nơi
    render_id = key_prefix or f"r{next(_REPORT_RENDER_COUNTER)}"
    downloads_l, downloads_r = st.columns(2)
    with downloads_l:
        ui.download_json_button({k: v for k, v in report.items() if k != "meta"},
                                "analysis_report.json", "⬇️ Tải báo cáo JSON",
                                f"dl_report_{render_id}")
    with downloads_r:
        st.download_button("⬇️ Tải bài đăng gốc (.txt)", data=raw_text.encode("utf-8"),
                           file_name="osa_post.txt", mime="text/plain",
                           key=f"dl_raw_{render_id}")

    if allow_link:
        existing = database.get_activities()
        suggestion = nlp_engine.suggest_parent_activity(raw_text, existing.to_dict("records"))
        if suggestion:
            st.info(
                f"🔗 Bài này có dấu hiệu là **{suggestion['post_type_label']}** của sự kiện gốc "
                f"**#{suggestion['activity_id']} – {suggestion['title'][:80]}** "
                f"(độ tin cậy {suggestion['confidence']:.0%}). "
                "Sau khi lưu, vào Tab 3 để gắn liên kết `parent_activity_id`."
            )


# ---------------------------------------------------------------------------
# (c) OCR ảnh poster
# ---------------------------------------------------------------------------
def _gemini_vision_ocr(image_bytes: bytes, mime_type: str, api_key: str,
                       model: str = "gemini-2.5-flash") -> tuple[str | None, str]:
    """OCR poster qua Gemini Vision. Trả về (text, source_label)."""
    import base64

    prompt = (
        "Trích xuất TOÀN BỘ văn bản hiển thị trên poster này (giữ nguyên tiếng Việt, "
        "kể cả emoji, thời gian, địa điểm, điểm rèn luyện nếu có). "
        "Chỉ trả về JSON: {\"text\": \"...\"}"
    )
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        gm = genai.GenerativeModel(model, generation_config={"response_mime_type": "application/json"})
        resp = gm.generate_content([
            {"mime_type": mime_type, "data": image_bytes},
            prompt,
        ])
        import json as _json
        data = _json.loads(re.sub(r"^```(?:json)?|```$", "", resp.text.strip(), flags=re.MULTILINE))
        return data.get("text"), "Gemini Vision OCR"
    except Exception:  # noqa: BLE001
        pass
    try:
        import json as _json
        import urllib.request

        b64 = base64.b64encode(image_bytes).decode("ascii")
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
               f"?key={api_key}")
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": mime_type, "data": b64}},
                {"text": prompt},
            ]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        req = urllib.request.Request(url, data=_json.dumps(payload).encode(),
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as resp:  # nosec
            data = _json.loads(resp.read().decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE))
        return parsed.get("text"), "Gemini Vision OCR (REST)"
    except Exception as exc:  # noqa: BLE001
        return None, f"OCR thất bại: {type(exc).__name__}: {exc}"


def _render_ocr_block() -> None:
    st.markdown("#### 📷 Tải ảnh poster để trích xuất văn bản")
    provider = st.session_state.get("ai_provider", "LOCAL")
    api_key = st.session_state.get("ai_key", "")
    if provider != "GEMINI" or not api_key:
        ui.warn_box(
            "OCR poster hiện dùng **Gemini Vision** – bạn chưa cấu hình Gemini API Key ở sidebar. "
            "Hai lựa chọn hợp lệ: (1) nhập Gemini API Key ở sidebar rồi quay lại đây; "
            "(2) sao chép văn bản trên poster và dán vào ô bên dưới. "
            "Hệ thống **không giả vờ** đã OCR khi chưa có engine thật."
        )
    image = st.file_uploader("Ảnh poster (JPG/PNG)", type=["jpg", "jpeg", "png"],
                             key="poster_upload")
    ocr_text = ""
    if image is not None:
        st.image(image, caption="Poster đã tải lên", width=340)
        if st.button("🔍 Trích xuất văn bản từ ảnh", key="ocr_btn",
                     disabled=(provider != "GEMINI" or not api_key)):
            with st.spinner("Đang OCR poster qua Gemini Vision…"):
                text, source = _gemini_vision_ocr(
                    image.getvalue(), image.type or "image/jpeg", api_key,
                    st.session_state.get("ai_model") or "gemini-2.5-flash",
                )
            if text:
                st.session_state["ocr_text"] = text
                st.success(f"OCR thành công bằng {source}. Kiểm tra lại văn bản trước khi phân tích.")
            else:
                st.error(source)
    ocr_text = st.text_area("Văn bản trích xuất được (có thể chỉnh sửa trước khi phân tích)",
                            value=st.session_state.get("ocr_text", ""), height=150,
                            key="ocr_text_edit")
    if ocr_text.strip():
        if st.button("🧠 Phân tích & Lưu Database (từ poster)", type="primary", key="ocr_analyze"):
            _analyze_and_store(ocr_text, config.OSA_FACEBOOK_URL, "IMAGE_OCR",
                               published_at=None, external_post_id=None, show_summary=True)


def _analyze_and_store(raw_text: str, url: str, fetch_method: str,
                       published_at=None, external_post_id=None,
                       show_summary: bool = False) -> None:
    provider, api_key, model = ui.ai_settings_from_session()
    with st.spinner("Đang bóc tách 4 nhóm thông tin & phân loại 2 bước…"):
        report = analyze_post_with_ai(
            raw_text, url=url, criteria_catalog=ui.criteria_records(),
            provider=provider, api_key=api_key, model=model,
        )
    st.session_state["last_report"] = report
    st.session_state["last_raw_text"] = raw_text
    st.session_state["last_url"] = url
    post_id, activity_id = _save_report(raw_text, url, fetch_method, report,
                                        published_at=published_at,
                                        external_post_id=external_post_id)
    database.log_action("ANALYZE_POST", {
        "post_id": post_id, "activity_id": activity_id,
        "label": report["relevance_label"],
        "fetch_method": fetch_method, "ai_source": (report.get("meta") or {}).get("ai_source"),
    })
    if show_summary:
        st.success(
            f"Đã lưu bài đăng #{post_id} / hoạt động #{activity_id} – nhãn "
            f"**{report['relevance_label']}**."
        )


# ---------------------------------------------------------------------------
# (b) Nhập hàng loạt CSV/Excel
# ---------------------------------------------------------------------------
CSV_TEMPLATE_COLUMNS = ["url", "content", "published_at", "external_post_id"]


def _bulk_import(df: pd.DataFrame, url_col: str, content_col: str,
                 published_col: str | None, ext_id_col: str | None) -> None:
    provider, api_key, model = ui.ai_settings_from_session()
    total = len(df)
    progress = st.progress(0.0, text="Đang phân tích…")
    counts: dict[str, int] = {}
    errors = 0
    for idx, row in enumerate(df.to_dict("records")):
        raw = str(row.get(content_col) or "").strip()
        if len(raw) < 10:
            errors += 1
            continue
        try:
            report = analyze_post_with_ai(
                raw, url=str(row.get(url_col) or config.OSA_FACEBOOK_URL),
                criteria_catalog=ui.criteria_records(),
                provider=provider, api_key=api_key, model=model,
            )
            _save_report(
                raw,
                str(row.get(url_col) or config.OSA_FACEBOOK_URL),
                "CSV_EXCEL_IMPORT",
                report,
                published_at=(str(row.get(published_col)) if published_col and row.get(published_col) else None),
                external_post_id=(str(row.get(ext_id_col)) if ext_id_col and row.get(ext_id_col) else None),
            )
            counts[report["relevance_label"]] = counts.get(report["relevance_label"], 0) + 1
        except Exception:  # noqa: BLE001
            errors += 1
        progress.progress(min(1.0, (idx + 1) / max(1, total)),
                          text=f"Đang phân tích {idx + 1}/{total}…")
    progress.empty()
    database.log_action("BULK_IMPORT", {"rows": total, "errors": errors, "counts": counts})
    st.success(f"Đã xử lý {total - errors}/{total} dòng. Kết quả phân loại: {counts or '—'}")
    if errors:
        st.warning(f"{errors} dòng bị bỏ qua (nội dung < 10 ký tự hoặc lỗi xử lý).")


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def render() -> None:
    ui.hero(
        "📥 Thu thập & Bóc tách Bài đăng OSA HCMUS",
        "Nguồn mặc định: https://www.facebook.com/osa.hcmus · 4 phương thức nạp hợp lệ · "
        "tự động bật cờ cảnh báo khi thiếu Thời gian / Địa điểm / Nội dung / Điểm ĐRL.",
    )

    provider, api_key, _ = ui.ai_settings_from_session()
    if provider == "LOCAL" or not api_key:
        ui.note_box(
            "Đang chạy **bộ phân tích NLP nội bộ (Regex/Heuristic)** – hoạt động 100% offline. "
            "Muốn dùng Gemini/OpenAI (Structured JSON), cấu hình API Key ở sidebar trái."
        )
    else:
        ui.note_box(f"Đang ưu tiên **{provider}** cho bóc tách; nếu API lỗi sẽ tự fallback về NLP nội bộ.")

    tab_a, tab_b, tab_c = st.tabs([
        "🅐 Dán URL + nội dung bài đăng",
        "🅑 Nhập hàng loạt CSV/Excel",
        "🅒 Tải ảnh poster (OCR)",
    ])


    # ---------------- (a) Dán URL + nội dung ----------------
    with tab_a:
        col1, col2 = st.columns([1, 1.6])
        with col1:
            url = st.text_input("URL bài đăng OSA (công khai)",
                                value=config.OSA_FACEBOOK_URL,
                                help="Ví dụ: https://www.facebook.com/osa.hcmus/posts/123456")
            published_at = st.text_input("Thời điểm đăng (tuỳ chọn, ISO 8601)",
                                         placeholder="2026-11-10T09:00:00+07:00")
            external_post_id = st.text_input("external_post_id (tuỳ chọn)",
                                             placeholder="1234567890")
            st.caption(
                "Extension không vượt CAPTCHA, không tự đăng nhập – bạn chỉ cần sao chép nội dung "
                "bài đăng công khai hoặc dùng file Excel xuất từ công cụ của Ban Tổ chức."
            )
        with col2:
            raw_text = st.text_area(
                "Nội dung bài đăng", height=290,
                placeholder=(
                    "Dán nguyên văn bài đăng vào đây. Ví dụ:\n\n"
                    "THÔNG BÁO TỔ CHỨC WORKSHOP KỸ NĂNG\n"
                    "2. Thời gian: 14g00, ngày 18/11/2026\n"
                    "3. Địa điểm: Giảng đường 1, cơ sở Nguyễn Văn Cừ\n"
                    "4. Báo cáo viên: TS. Nguyễn Văn A\n"
                    "Sinh viên đăng ký trước ngày 15/11/2026."
                ),
            )
        btn_col1, btn_col2 = st.columns([1, 1])
        analyze_clicked = btn_col1.button("🚀 Phân tích & Lưu Database", type="primary",
                                         key="analyze_single",
                                         disabled=len(raw_text.strip()) < 10)
        preview_clicked = btn_col2.button("👁️ Chỉ phân tích (không lưu)", key="preview_single",
                                          disabled=len(raw_text.strip()) < 10)

        if preview_clicked:
            with st.spinner("Đang bóc tách…"):
                report = analyze_post_with_ai(
                    raw_text, url=url, criteria_catalog=ui.criteria_records(),
                    provider=provider, api_key=api_key, model=ui.ai_settings_from_session()[2],
                )
            _render_report(report, raw_text, url)
        if analyze_clicked:
            _analyze_and_store(raw_text, url, "MANUAL_PASTE",
                               published_at=published_at or None,
                               external_post_id=external_post_id or None)
            report = st.session_state.get("last_report")
            if report:
                _render_report(report, raw_text, url, key_prefix="saved")
            st.toast("Đã lưu vào SQLite. Xem tại Tab 3.", icon="✅")

    # ---------------- (b) CSV / Excel ----------------
    with tab_b:
        ui.note_box(
            "File cần có cột nội dung bài đăng (ví dụ: `content` hoặc `raw_text`) và có thể có "
            "`url`, `published_at`, `external_post_id`. Dòng thiếu nội dung sẽ bị bỏ qua."
        )
        template_df = pd.DataFrame([
            {"url": "https://www.facebook.com/osa.hcmus/posts/001",
             "content": "VD: Thông báo hội thảo… (điền nội dung bài đăng công khai ở đây)",
             "published_at": "2026-11-10T09:00:00+07:00", "external_post_id": "001"},
        ])
        ui.download_csv_button(template_df, "osa_posts_template.csv",
                               "⬇️ Tải file CSV mẫu", "dl_csv_tpl")
        uploaded = st.file_uploader("Tải file CSV hoặc Excel", type=["csv", "xlsx", "xls"],
                                    key="bulk_upload")
        if uploaded is not None:
            try:
                if uploaded.name.lower().endswith((".xlsx", ".xls")):
                    df = pd.read_excel(uploaded)
                else:
                    df = pd.read_csv(uploaded)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Không đọc được file: {exc}")
                df = pd.DataFrame()
            if not df.empty:
                st.write(f"Đã đọc **{len(df)} dòng**, {len(df.columns)} cột: {list(df.columns)}")
                st.dataframe(df.head(8), width="stretch", height=230)
                cols = list(df.columns)
                default_content = next((c for c in cols if c.lower() in
                                        ("content", "raw_text", "noi_dung", "text", "content_text")),
                                       cols[0])
                content_col = st.selectbox("Cột chứa NỘI DUNG bài đăng", cols,
                                           index=cols.index(default_content))
                url_col = st.selectbox("Cột URL", cols, index=cols.index("url") if "url" in cols else 0)
                optional_cols = ["(không có)"] + cols
                published_col = st.selectbox(
                    "Cột thời điểm đăng", optional_cols,
                    index=optional_cols.index("published_at") if "published_at" in cols else 0)
                ext_id_col = st.selectbox(
                    "Cột external_post_id", optional_cols,
                    index=optional_cols.index("external_post_id") if "external_post_id" in cols else 0)
                if st.button("🚀 Phân tích & Lưu toàn bộ", type="primary", key="bulk_run"):
                    _bulk_import(
                        df, url_col, content_col,
                        None if published_col == "(không có)" else published_col,
                        None if ext_id_col == "(không có)" else ext_id_col,
                    )

    # ---------------- (c) Ảnh poster ----------------
    with tab_c:
        _render_ocr_block()

