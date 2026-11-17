"""Tầng AI: gọi Gemini / OpenAI với Structured JSON Outputs + fallback nội bộ.

Nguyên tắc an toàn của module:

1. KHÔNG BAO GIỜ phụ thuộc API để ứng dụng chạy: nếu chưa nhập API Key, hoặc
   mạng lỗi, hoặc trả về JSON không hợp lệ → tự động dùng báo cáo của
   ``nlp_engine`` (Regex/Heuristic offline).
2. AI KHÔNG ĐƯỢC tự nâng nhãn lên ``VERIFIED_DRL``: mọi kết quả AI trả về
   ``VERIFIED_DRL`` đều bị hạ xuống ``POTENTIAL_DRL`` kèm cảnh báo, vì xác minh
   chính thức phải do Admin duyệt hoặc có trích dẫn quy chế từ hcmus.drl.vn.
3. Mã tiêu chí AI trả về phải tồn tại trong DRLCriteria; nếu không → bỏ (None).
4. Cờ ``is_missing_*`` luôn được TÍNH LẠI trên dữ liệu cuối cùng để không lệch
   với nội dung hiển thị.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from . import config
from . import nlp_engine

SYSTEM_PROMPT = """Bạn là chuyên gia phân tích thông báo hoạt động sinh viên của Trường Đại học Khoa học Tự nhiên – ĐHQG TP.HCM (HCMUS).
Nhiệm vụ: đọc một bài đăng fanpage OSA HCMUS và trích xuất thông tin theo ĐÚNG JSON schema được yêu cầu.

QUY TẮC BẮT BUỘC:
1. TUYỆT ĐỐI KHÔNG bịa thông tin không có trong bài đăng. Nếu không có → để null.
2. expected_score CHỈ lấy khi bài đăng nêu rõ điểm ĐRL cụ thể của hoạt động (vd "+5 điểm rèn luyện").
   Nếu bài chỉ nhắc "theo quy chế" chung → expected_score = null.
3. criterion_code CHỈ chọn trong danh sách mã tiêu chí được cung cấp.
4. relevance_label chỉ được là một trong: NOT_RELEVANT, INSUFFICIENT_INFO, EVENT_CANDIDATE, POTENTIAL_DRL.
   KHÔNG được trả VERIFIED_DRL (việc xác minh thuộc về Admin/quy chế).
5. Thời gian định dạng "YYYY-MM-DD HH:MM". Nếu bài chỉ có ngày → dùng 00:00 và ghi rõ trong assumptions.
6. Nếu bài là nhắc hạn / đổi lịch / công bố kết quả, đặt post_type tương ứng.
7. Chỉ trả về JSON hợp lệ, không kèm markdown, không giải thích ngoài JSON."""

USER_TEMPLATE = """Hãy phân tích bài đăng OSA HCMUS sau và trả về JSON đúng schema.

DANH MỤC TIÊU CHÍ ĐRL HIỆN HÀNH (chỉ được chọn mã trong đây):
{catalog}

BÀI ĐĂNG (URL: {url}):
\"\"\"
{raw_text}
\"\"\"

BẢN NHÁP DO BỘ PHÂN TÍCH NỘI BỘ (Regex/Heuristic) TẠO RA (hãy kiểm tra, sửa nếu sai, KHÔNG bịa thêm):
{draft_json}

JSON SCHEMA BẮT BUỘC:
{{
  "post_type": "event_announcement|deadline_reminder|schedule_change|result_announcement|recruitment|promotion|administrative|other",
  "relevance_label": "NOT_RELEVANT|INSUFFICIENT_INFO|EVENT_CANDIDATE|POTENTIAL_DRL",
  "relevance_reason": "giải thích ngắn gọn bằng tiếng Việt",
  "is_student_participation_possible": true/false,
  "activity": {{
    "title": "string hoặc null",
    "organizer": "string hoặc null",
    "location": "string hoặc null",
    "campus": "NVC|Linh Trung|Online|null",
    "start_time": "YYYY-MM-DD HH:MM hoặc null",
    "end_time": "YYYY-MM-DD HH:MM hoặc null",
    "registration_deadline": "YYYY-MM-DD HH:MM hoặc null",
    "expected_score": number hoặc null,
    "criterion_code": "mã trong danh mục hoặc null"
  }},
  "missing_flags": {{
    "is_missing_time": bool, "is_missing_location": bool,
    "is_missing_content": bool, "is_missing_score": bool
  }},
  "drl_assessment": {{
    "status": "UNVERIFIED|NEEDS_HUMAN_REVIEW",
    "rule_citations": ["trích dẫn quy chế nếu có trong danh mục"],
    "reason": "string"
  }},
  "assumptions": ["các giả định đã dùng, nếu có"]
}}"""


# ---------------------------------------------------------------------------
# Gọi API
# ---------------------------------------------------------------------------
def _http_post_json(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    """POST JSON không phụ thuộc thư viện ngoài (urllib) – dùng làm fallback."""
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - endpoint cố định
        return json.loads(resp.read().decode("utf-8"))


def call_gemini(prompt: str, api_key: str, model: str = "gemini-2.5-flash") -> tuple[str, str]:
    """Gọi Gemini. Thử SDK google-generativeai → google-genai → REST.

    Trả về (text, provider_label). Raise RuntimeError nếu thất bại hoàn toàn.
    """
    errors: list[str] = []

    # Cách 1: SDK google-generativeai (đúng lệnh pip trong đề bài)
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)  # SDK cũ đã deprecated
            import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)
        gm = genai.GenerativeModel(
            model_name=model,
            system_instruction=SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        resp = gm.generate_content(prompt)
        return resp.text, f"Gemini SDK ({model})"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"google-generativeai: {exc}")

    # Cách 2: SDK mới google-genai
    try:
        from google import genai as new_genai  # type: ignore

        client = new_genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
            config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        return resp.text, f"Gemini SDK mới ({model})"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"google-genai: {exc}")

    # Cách 3: REST trực tiếp
    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
        }
        data = _http_post_json(url, payload, {})
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text, f"Gemini REST ({model})"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"REST: {exc}")

    raise RuntimeError("Không gọi được Gemini. Chi tiết: " + " | ".join(errors[-2:]))


def call_openai(prompt: str, api_key: str, model: str = "gpt-4o-mini") -> tuple[str, str]:
    """Gọi OpenAI Chat Completions với JSON mode. Fallback REST nếu thiếu SDK."""
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(**payload)
        return resp.choices[0].message.content or "", f"OpenAI SDK ({model})"
    except Exception as exc_sdk:  # noqa: BLE001
        try:
            data = _http_post_json(
                "https://api.openai.com/v1/chat/completions",
                payload,
                {"Authorization": f"Bearer {api_key}"},
            )
            text = data["choices"][0]["message"]["content"]
            return text, f"OpenAI REST ({model})"
        except Exception as exc_rest:  # noqa: BLE001
            raise RuntimeError(
                f"Không gọi được OpenAI. SDK: {exc_sdk} | REST: {exc_rest}"
            ) from exc_rest


# ---------------------------------------------------------------------------
# Hợp nhất & kiểm duyệt JSON của AI
# ---------------------------------------------------------------------------
_DATETIME_FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                     "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"]


def _parse_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return None


def _parse_score(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= score <= 30:
        return score
    return None


def sanitize_ai_report(report: dict, local_report: dict,
                       criteria_catalog: Optional[list[dict]] = None) -> tuple[dict, list[str]]:
    """Ép báo cáo AI về đúng miền giá trị an toàn. Trả về (report, warnings)."""
    warnings: list[str] = []
    if not isinstance(report, dict):
        return local_report, ["AI trả về không phải JSON object → dùng bản nội bộ."]

    valid_codes = {str(c.get("code")) for c in (criteria_catalog or [])}
    out = json.loads(json.dumps(local_report))  # deep copy

    # --- các trường cơ bản ---
    if report.get("post_type") in nlp_engine.POST_TYPE_LABELS:
        out["post_type"] = report["post_type"]

    label = report.get("relevance_label")
    if label == config.LABEL_VERIFIED:
        warnings.append("AI cố tự xác minh VERIFIED_DRL → đã hạ xuống POTENTIAL_DRL (chỉ Admin/quy chế được xác minh).")
        label = config.LABEL_POTENTIAL
    if label in config.RELEVANCE_LABELS:
        out["relevance_label"] = label
    elif label is not None:
        warnings.append(f"Nhãn AI trả về không hợp lệ ({label}) → giữ nhãn nội bộ.")

    if isinstance(report.get("relevance_reason"), str) and report["relevance_reason"].strip():
        out["relevance_reason"] = report["relevance_reason"].strip()[:800]
    if isinstance(report.get("is_student_participation_possible"), bool):
        out["is_student_participation_possible"] = report["is_student_participation_possible"]

    # --- activity ---
    src_act = report.get("activity") or {}
    act = out["activity"]
    for key in ("title", "organizer", "location"):
        value = src_act.get(key)
        if isinstance(value, str) and value.strip() and value.strip().lower() not in {"null", "none"}:
            act[key] = value.strip()[:250]
    campus = src_act.get("campus")
    if campus in config.CAMPUSES:
        act["campus"] = campus
    for key in ("start_time", "end_time", "registration_deadline"):
        parsed = _parse_datetime(src_act.get(key))
        if parsed:
            act[key] = parsed
    score = _parse_score(src_act.get("expected_score"))
    if score is not None:
        act["expected_score"] = score
    code = src_act.get("criterion_code")
    if isinstance(code, str) and code.strip():
        code = code.strip()
        if valid_codes and code not in valid_codes:
            warnings.append(f"Mã tiêu chí '{code}' AI trả về không có trong DRLCriteria → bỏ.")
        else:
            act["criterion_code"] = code

    # --- drl assessment ---
    assess = report.get("drl_assessment") or {}
    citations = [c for c in (assess.get("rule_citations") or []) if isinstance(c, str)]
    if citations:
        out["drl_assessment"]["rule_citations"] = citations[:3]
    if isinstance(assess.get("reason"), str) and assess["reason"].strip():
        out["drl_assessment"]["reason"] = assess["reason"].strip()[:600]
    ai_status = assess.get("status")
    if ai_status in {config.VERIFY_NONE, config.VERIFY_NEEDS_REVIEW}:
        out["drl_assessment"]["status"] = ai_status

    # --- assumptions ---
    extra_assumptions = [a for a in (report.get("assumptions") or []) if isinstance(a, str)]
    merged = list(dict.fromkeys(out.get("extraction_meta", {}).get("assumptions", []) + extra_assumptions))
    out.setdefault("extraction_meta", {})["assumptions"] = merged[:8]

    # --- TÍNH LẠI cờ thiếu dữ liệu trên dữ liệu cuối cùng ---
    flags = {
        "is_missing_time": not (act.get("start_time") or act.get("registration_deadline")),
        "is_missing_location": not act.get("location"),
        "is_missing_content": len((act.get("title") or "").strip()) < 12,
        "is_missing_score": act.get("expected_score") is None and not act.get("criterion_code"),
    }
    out["missing_flags"] = flags
    if any(flags.values()) and out["relevance_label"] in {
        config.LABEL_POTENTIAL, config.LABEL_EVENT_CANDIDATE, config.LABEL_VERIFIED
    }:
        out["relevance_label"] = config.LABEL_INSUFFICIENT
        out["relevance_reason"] = (
            "Dữ liệu sau phân tích vẫn thiếu thông tin trọng tâm → chuyển INSUFFICIENT_INFO."
        )
    return out, warnings


# ---------------------------------------------------------------------------
# API công khai
# ---------------------------------------------------------------------------
def analyze_post_with_ai(
    raw_text: str,
    url: str = "",
    criteria_catalog: Optional[list[dict]] = None,
    provider: str = "LOCAL",
    api_key: str = "",
    model: str = "",
    use_local_when_no_key: bool = True,
) -> dict[str, Any]:
    """Phân tích bài đăng, ưu tiên AI nếu có key, luôn có fallback nội bộ.

    Trả về dict gồm báo cáo Schema 1 + ``meta`` (ai_source, ai_error).
    """
    local_report = nlp_engine.analyze_post(raw_text, url=url, criteria_catalog=criteria_catalog)
    meta = {"ai_source": "LOCAL_NLP (Regex/Heuristic)", "ai_error": None, "ai_warnings": []}

    if provider == "LOCAL" or not api_key:
        if not use_local_when_no_key:
            meta["ai_error"] = "Chưa cấu hình API Key."
        return {**local_report, "meta": meta}

    catalog_str = "\n".join(
        f"- {c.get('code')}: {c.get('name')} (tối đa {c.get('max_score')}đ, "
        f"bắt buộc={'Có' if c.get('mandatory') else 'Không'})"
        for c in (criteria_catalog or [])
    ) or "- (chưa có danh mục)"
    draft_json = json.dumps(
        {k: local_report[k] for k in ("post_type", "relevance_label", "activity", "missing_flags")},
        ensure_ascii=False, indent=2,
    )
    prompt = USER_TEMPLATE.format(
        catalog=catalog_str, url=url or "(không có)", raw_text=raw_text[:6000], draft_json=draft_json
    )

    try:
        if provider == "GEMINI":
            text, label = call_gemini(prompt, api_key, model or "gemini-2.5-flash")
        elif provider == "OPENAI":
            text, label = call_openai(prompt, api_key, model or "gpt-4o-mini")
        else:
            raise RuntimeError(f"Provider không hỗ trợ: {provider}")
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        sanitized, warnings = sanitize_ai_report(parsed, local_report, criteria_catalog)
        meta.update({"ai_source": f"{label} + kiểm duyệt Schema", "ai_warnings": warnings})
        return {**sanitized, "meta": meta}
    except Exception as exc:  # noqa: BLE001
        meta["ai_error"] = f"{type(exc).__name__}: {exc}"
        meta["ai_source"] = "LOCAL_NLP (fallback do lỗi AI)"
        return {**local_report, "meta": meta}


def test_connection(provider: str, api_key: str, model: str = "") -> tuple[bool, str]:
    """Kiểm tra kết nối API (dùng cho nút 'Kiểm tra kết nối' trong sidebar)."""
    if provider == "GEMINI":
        try:
            text, label = call_gemini("Trả lời đúng JSON: {\"ok\": true}", api_key,
                                      model or "gemini-2.5-flash")
            return True, f"Kết nối thành công qua {label}. Phản hồi mẫu: {text[:120]}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    if provider == "OPENAI":
        try:
            text, label = call_openai("Trả lời đúng JSON: {\"ok\": true}", api_key,
                                      model or "gpt-4o-mini")
            return True, f"Kết nối thành công qua {label}. Phản hồi mẫu: {text[:120]}"
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
    return False, "Provider không hợp lệ."


# ---------------------------------------------------------------------------
# Sinh lời giải thích lộ trình
# ---------------------------------------------------------------------------
def explain_route_locally(route: dict, profile: dict, criteria_df_records: list[dict]) -> str:
    """Sinh Route Explanation bằng template tiếng Việt (luôn dùng được, offline).

    Chỉ diễn giải các con số CÓ THẬT trong ``route`` – không thêm dữ kiện mới.
    """
    if not route or not route.get("activities"):
        return (
            "Hiện chưa đủ hoạt động hợp lệ (không trùng lịch học, đủ thông tin) để lập lộ trình. "
            "Hãy bổ sung bài đăng OSA mới hoặc xác minh thêm hoạt động trong Tab 3."
        )
    acts = route["activities"]
    target = float(profile.get("target_score") or 0)
    # None = chưa đồng bộ điểm → coi như 0 khi TÍNH lộ trình;
    # giao diện hiển thị "chưa đồng bộ" để không gây hiểu nhầm.
    current = float(profile.get("current_total_score") or 0)
    gain = float(route.get("total_expected_score") or 0)
    projected = current + gain
    lines = [
        f"**Lộ trình gồm {len(acts)} hoạt động**, mang lại tổng **{gain:g} điểm ĐRL dự kiến**.",
        f"Điểm hiện tại **{current:g}** → sau lộ trình **{min(projected, 100):g}/100** "
        f"(mục tiêu {target:g}). Khoảng cách còn lại: **{max(0, target - min(projected, 100)):g} điểm**.",
        "",
        "**Vì sao lộ trình này tối ưu?**",
    ]
    for idx, act in enumerate(acts, start=1):
        reasons = []
        if act.get("verification_status") in {config.VERIFY_ADMIN_APPROVED, config.VERIFY_RULE_CITED} or \
                act.get("relevance_label") == config.LABEL_VERIFIED:
            reasons.append("đã xác minh (cộng vào điểm Verified)")
        else:
            reasons.append("tiềm năng (chỉ cộng vào cột Potential, cần xác minh)")
        if act.get("criterion_code"):
            crit = next((c for c in criteria_df_records if c.get("code") == act["criterion_code"]), None)
            missing = route.get("criterion_missing", {}).get(act["criterion_code"], 0)
            crit_name = crit.get("name") if crit else act["criterion_code"]
            reasons.append(f"thuộc tiêu chí {act['criterion_code']} – {crit_name} (còn thiếu {missing:g} điểm)")
        if act.get("travel_note"):
            reasons.append(act["travel_note"])
        if act.get("gap_note"):
            reasons.append(act["gap_note"])
        lines.append(f"{idx}. **{act.get('title')}** – {act.get('expected_score', 0):g} điểm; " + "; ".join(reasons) + ".")
    lines.append("")
    lines.append(
        "Các hoạt động được nối bằng cạnh trong đồ thị NetworkX khi thời gian kết thúc + thời gian "
        "di chuyển giữa cơ sở không vượt quá thời gian bắt đầu của hoạt động kế tiếp, và toàn bộ "
        "chuỗi không trùng bất kỳ tiết học nào trong Thời khóa biểu CTĐB."
    )
    excluded = route.get("excluded_conflicts") or []
    if excluded:
        lines.append("")
        lines.append(f"Đã loại {len(excluded)} hoạt động trùng giờ học chính khóa khỏi đồ thị.")
    return "\n".join(lines)


def explain_route_with_ai(route: dict, profile: dict, criteria_records: list[dict],
                          provider: str = "LOCAL", api_key: str = "",
                          model: str = "") -> tuple[str, str]:
    """Trả về (lời giải thích, nguồn sinh). Fallback template nếu AI lỗi/không có key."""
    local_text = explain_route_locally(route, profile, criteria_records)
    if provider == "LOCAL" or not api_key or not route or not route.get("activities"):
        return local_text, "Template nội bộ (offline)"

    prompt = f"""Bạn là trợ lý tư vấn Điểm rèn luyện HCMUS. Hãy viết đoạn giải thích NGẮN GỌN (150-220 từ, tiếng Việt, có gạch đầu dòng) cho lộ trình hoạt động dưới đây.
CHỈ sử dụng đúng các số liệu trong JSON, KHÔNG bịa thêm hoạt động/điểm/con số mới. Nhấn mạnh:
- Vì sao chuỗi hoạt động này không trùng lịch học và khả thi về di chuyển giữa cơ sở;
- Hoạt động nào cộng vào điểm ĐÃ XÁC MINH, hoạt động nào chỉ là TIỀM NĂNG (cần xác minh);
- Khoảng cách điểm còn lại so với mục tiêu.

JSON LỘ TRÌNH:
{json.dumps(route, ensure_ascii=False, default=str)[:6000]}

JSON HỒ SƠ SINH VIÊN:
{json.dumps(profile, ensure_ascii=False, default=str)[:1500]}
"""
    try:
        if provider == "GEMINI":
            text, label = call_gemini(prompt, api_key, model or "gemini-2.5-flash")
        elif provider == "OPENAI":
            text, label = call_openai(prompt, api_key, model or "gpt-4o-mini")
        else:
            return local_text, "Template nội bộ (offline)"
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                text = parsed.get("explanation") or parsed.get("text") or json.dumps(parsed, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass
        if len(text.strip()) < 40:
            return local_text, "Template nội bộ (AI trả lời quá ngắn)"
        return text.strip(), f"{label} (Route Explanation)"
    except Exception:  # noqa: BLE001
        return local_text, "Template nội bộ (fallback do lỗi AI)"
