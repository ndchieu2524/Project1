/**
 * Smart DRL Assistant – HCMUS Sync · Popup logic
 *
 * Luồng hoạt động
 *   1. Popup kiểm tra tab đang mở có thuộc 2 cổng hỗ trợ hay không.
 *   2. Bấm “Quét trang” → gửi message SDRS_SCAN tới content.js → nhận dữ liệu
 *      (thời khóa biểu hoặc điểm rèn luyện) và lưu vào chrome.storage.session.
 *   3. Gói dữ liệu được ghép từ 2 lần quét (TKB + ĐRL) thành đúng Schema 2 và
 *      xuất file hcmus_sync.json / copy clipboard.
 *   4. Không còn chế độ tạo gói DEMO: gói xuất ra luôn là dữ liệu quét thật
 *      từ cổng trường. Nếu quét không ra dữ liệu, báo lỗi để sửa bộ đọc DOM.
 *
 * BẢO MẬT: mọi xử lý diễn ra cục bộ trong trình duyệt. Không có fetch() ra
 * server ngoài, không lưu mật khẩu, không đọc cookie.
 */
"use strict";

const SUPPORTED_HOSTS = {
  "portal.ctdb.hcmus.edu.vn": "TIMETABLE",
  "hcmus.drl.vn": "DRL",
};

const STORAGE_KEY = "sdrs_draft_payload";
const BADGE_DEFAULT = { text: "Rỗng", cls: "badge badge-off" };

// ---------------------------------------------------------------------------
// Tham chiếu DOM
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const els = {
  pageStatus: $("pageStatus"),
  urlBox: $("urlBox"),
  scanBtn: $("scanBtn"),
  clearBtn: $("clearBtn"),
  scanResult: $("scanResult"),
  notesList: $("notesList"),
  payloadBadge: $("payloadBadge"),
  statTimetable: $("statTimetable"),
  statCriteria: $("statCriteria"),
  statTotal: $("statTotal"),
  statSemester: $("statSemester"),
  studentId: $("studentId"),
  semester: $("semester"),
  defaultCampus: $("defaultCampus"),
  jsonPreview: $("jsonPreview"),
  exportBtn: $("exportBtn"),
  copyBtn: $("copyBtn"),
  exportMsg: $("exportMsg"),
};

// ---------------------------------------------------------------------------
// Trạng thái nháp (được khôi phục từ chrome.storage.session)
// ---------------------------------------------------------------------------
let draft = {
  timetable: [],          // [{course_code, course_name, day_of_week, start_time, end_time, room, campus}]
  drl_progress: [],       // [{criterion_code, name, current_score, max_score, mandatory}]
  current_total_score: null,
  total_max: null,
  semesterDetected: "",
  studentIdDetected: "",
  isDemo: false,
  lastScannedAt: "",
  notes: [],
};

// ---------------------------------------------------------------------------
// Tiện ích UI
// ---------------------------------------------------------------------------
function setStatus(el, message, kind = "idle") {
  el.className = `status status-${kind}`;
  el.textContent = message;
}

function setNotes(notes) {
  els.notesList.innerHTML = "";
  (notes || []).slice(0, 8).forEach((note) => {
    const li = document.createElement("li");
    li.textContent = note;
    els.notesList.appendChild(li);
  });
}

function refreshStats() {
  els.statTimetable.textContent = String(draft.timetable.length);
  els.statCriteria.textContent = String(draft.drl_progress.length);
  els.statTotal.textContent = draft.current_total_score === null
    ? "—"
    : `${draft.current_total_score}${draft.total_max ? "/" + draft.total_max : ""}`;
  els.statSemester.textContent = draft.semesterDetected || "—";

  const hasData = draft.timetable.length || draft.drl_progress.length
    || draft.current_total_score !== null;
  if (draft.isDemo) {
    els.payloadBadge.textContent = "DEMO";
    els.payloadBadge.className = "badge badge-demo";
  } else if (hasData) {
    els.payloadBadge.textContent = "Sẵn sàng";
    els.payloadBadge.className = "badge badge-ok";
  } else {
    els.payloadBadge.textContent = BADGE_DEFAULT.text;
    els.payloadBadge.className = BADGE_DEFAULT.cls;
  }

  els.jsonPreview.textContent = hasData
    ? JSON.stringify(buildPayload(), null, 2)
    : "(chưa có dữ liệu)";
}

async function persistDraft() {
  try {
    await chrome.storage.session.set({ [STORAGE_KEY]: draft });
  } catch (error) {
    // chrome.storage.session có thể không khả dụng ở một số bản → bỏ qua an toàn
    console.warn("Không lưu được draft:", error);
  }
}

async function restoreDraft() {
  try {
    const stored = await chrome.storage.session.get(STORAGE_KEY);
    if (stored && stored[STORAGE_KEY]) {
      draft = { ...draft, ...stored[STORAGE_KEY] };
    }
  } catch (error) {
    console.warn("Không khôi phục được draft:", error);
  }
  // Điền lại ô nhập từ draft (nếu người dùng đã nhập trước đó)
  if (draft.studentIdDetected && !els.studentId.value) els.studentId.value = draft.studentIdDetected;
  if (draft.semesterDetected && !els.semester.value) els.semester.value = draft.semesterDetected;
  if (draft.defaultCampus && els.defaultCampus) els.defaultCampus.value = draft.defaultCampus;
}

// ---------------------------------------------------------------------------
// Xây gói JSON theo Schema 2
// ---------------------------------------------------------------------------
function normalizeSemester(raw) {
  const text = (raw || "").trim();
  if (!text) return "";
  // "HK1 2026-2027" → "HK1_2026_2027"
  const m = text.match(/HK\s*(\d)\s*[-_/]?\s*(\d{4})\s*[-–/]\s*(\d{4})/i);
  if (m) return `HK${m[1]}_${m[2]}_${m[3]}`;
  return text.replace(/\s+/g, "_");
}

function buildPayload() {
  const studentId = (els.studentId.value || draft.studentIdDetected || "").trim();
  const semester = normalizeSemester(els.semester.value || draft.semesterDetected || "");
  const hasDetailed = draft.drl_progress.length > 0;
  // Chỉ gửi điểm khi THỰC SỰ đọc được từ trang DRL hoặc có tiêu chí chi tiết.
  // Tuyệt đối không gửi 0 giả khi người dùng mới chỉ quét thời khóa biểu,
  // vì phía Web App sẽ hiểu là "điểm hiện tại = 0" và ghi đè dữ liệu cũ.
  let total = null;
  if (draft.current_total_score !== null && draft.current_total_score !== undefined) {
    total = draft.current_total_score;
  } else if (hasDetailed) {
    total = draft.drl_progress.reduce((sum, row) => sum + (Number(row.current_score) || 0), 0);
  }

  const payload = {
    sync_source: "HCMUS_CHROME_EXTENSION_V1",
    synced_at: new Date().toISOString(),
    student_profile: {
      student_id: studentId,
      semester: semester,
      current_total_score: total,
      score_type: draft.isDemo
        ? "OFFICIAL_SYNCED"
        : (hasDetailed ? "OFFICIAL_SYNCED" : "SELF_DECLARED"),
      has_detailed_criteria: hasDetailed,
    },
    drl_progress: draft.drl_progress.map((row) => ({
      criterion_code: row.criterion_code,
      name: row.name || row.criterion_code,
      current_score: row.current_score,
      max_score: row.max_score,
      mandatory: Boolean(row.mandatory),
    })),
    timetable: draft.timetable.map((row) => ({
      course_code: row.course_code,
      course_name: row.course_name,
      day_of_week: row.day_of_week,
      start_time: row.start_time,
      end_time: row.end_time,
      room: row.room || "",
      campus: row.campus || (els.defaultCampus ? els.defaultCampus.value : "") || "",
    })),
    extraction_meta: {
      extension_version: chrome.runtime.getManifest().version,
      total_max: draft.total_max,
      last_scanned_at: draft.lastScannedAt,
      score_included: total !== null,
      notes: draft.notes,
    },
  };

  if (draft.isDemo) {
    payload.is_demo = true;
    payload.demo_note = "[DEMO] Gói dữ liệu mẫu do Chrome Extension tạo – KHÔNG phải dữ liệu thật "
      + "từ cổng trường. Dùng để kiểm thử luồng tích hợp.";
  }
  return payload;
}

function validatePayload(payload) {
  const errors = [];
  if (payload.student_profile.current_total_score === null) {
    // Không phải lỗi: gói chỉ chứa thời khóa biểu. Web App sẽ giữ nguyên điểm cũ.
    // (Cảnh báo hiển thị riêng, không chặn xuất gói.)
  }
  if (!payload.student_profile.student_id) errors.push("Chưa nhập MSSV.");
  if (!payload.student_profile.semester) errors.push("Chưa nhập học kỳ (VD: HK1_2026_2027).");
  if (!payload.timetable.length && !payload.drl_progress.length
      && payload.student_profile.current_total_score === null) {
    errors.push("Gói dữ liệu rỗng – hãy mở cổng trường và bấm Quét trang.");
  }
  payload.timetable.forEach((row, idx) => {
    ["course_code", "day_of_week", "start_time", "end_time"].forEach((key) => {
      if (!row[key]) errors.push(`timetable[${idx}] thiếu '${key}'.`);
    });
  });
  return errors;
}

// ---------------------------------------------------------------------------
// Nút 1: Quét trang hiện tại
// ---------------------------------------------------------------------------
async function scanCurrentTab() {
  els.scanBtn.disabled = true;
  setStatus(els.scanResult, "Đang quét DOM của trang…", "idle");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) throw new Error("Không xác định được tab hiện tại.");

    const host = tab.url ? new URL(tab.url).hostname : "";
    if (!SUPPORTED_HOSTS[host]) {
      throw new Error(
        `Trang hiện tại (${host || "không rõ"}) không được hỗ trợ. `
        + "Hãy mở portal.ctdb.hcmus.edu.vn hoặc hcmus.drl.vn sau khi đăng nhập.",
      );
    }

    // Thử gửi message tới content script; nếu chưa inject → inject thủ công
    let response;
    try {
      response = await chrome.tabs.sendMessage(tab.id, { type: "SDRS_SCAN" });
    } catch (_err) {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      response = await chrome.tabs.sendMessage(tab.id, { type: "SDRS_SCAN" });
    }

    if (!response || response.type !== "SDRS_SCAN_RESULT") {
      throw new Error("Content script không phản hồi. Hãy tải lại trang rồi thử lại.");
    }
    if (!response.ok) throw new Error(response.error || "Quét thất bại.");

    const { section, data, notes, warnings } = response.payload;
    draft.lastScannedAt = response.scanned_at;

    if (section === "TIMETABLE") {
      // Tự điền thông tin sinh viên/học kỳ đọc được từ portal (chỉ điền khi ô còn trống)
      if (data.student_id && !els.studentId.value) {
        els.studentId.value = data.student_id;
        draft.studentIdDetected = data.student_id;
      }
      if (data.semester) {
        draft.semesterDetected = data.semester;
        if (!els.semester.value) els.semester.value = normalizeSemester(data.semester);
      }
      const rows = data.timetable || [];
      if (rows.length) {
        draft.timetable = rows;
        draft.isDemo = false;
        const extra = [];
        if (data.student_id) extra.push(`MSSV ${data.student_id}`);
        if (data.semester) extra.push(data.semester);
        setStatus(els.scanResult,
          `✅ Đã đọc ${rows.length} buổi học từ Thời khóa biểu CTĐB`
          + (extra.length ? ` (${extra.join(", ")})` : "") + ".", "ok");
      } else {
        setStatus(els.scanResult,
          "⚠️ Không đọc được bảng thời khóa biểu. Hãy mở đúng trang TKB rồi quét lại.", "warn");
      }
    } else if (section === "DRL") {
      if (data.student_id && !els.studentId.value) {
        els.studentId.value = data.student_id;
        draft.studentIdDetected = data.student_id;
      }
      if (data.semester) {
        draft.semesterDetected = data.semester;
        if (!els.semester.value) els.semester.value = normalizeSemester(data.semester);
      }
      if (data.current_total_score !== null && data.current_total_score !== undefined) {
        draft.current_total_score = data.current_total_score;
        draft.total_max = data.total_max;
      }
      if (data.criteria && data.criteria.length) {
        draft.drl_progress = data.criteria.filter((row) => row.criterion_code);
      }
      draft.isDemo = false;
      const bits = [];
      if (draft.current_total_score !== null) bits.push(`tổng ${draft.current_total_score}`);
      if (draft.drl_progress.length) bits.push(`${draft.drl_progress.length} tiêu chí`);
      setStatus(els.scanResult,
        bits.length ? `✅ Đã đọc ${bits.join(" + ")} từ hcmus.drl.vn.`
          : "⚠️ Không tìm thấy điểm/tiêu chí – hãy mở trang Điểm rèn luyện rồi quét lại.",
        bits.length ? "ok" : "warn");
    } else {
      setStatus(els.scanResult,
        "⚠️ Trang không thuộc 2 cổng hỗ trợ. Mở portal.ctdb.hcmus.edu.vn hoặc hcmus.drl.vn.", "warn");
    }

    draft.notes = [...(draft.notes || []), ...(notes || []), ...(warnings || [])].slice(-12);
    setNotes(draft.notes);
    if (warnings && warnings.length) {
      setStatus(els.scanResult, `⚠️ ${warnings[0]}`, "warn");
    }
  } catch (error) {
    setStatus(els.scanResult, `❌ ${error.message || error}`, "err");
  } finally {
    els.scanBtn.disabled = false;
    await persistDraft();
    refreshStats();
  }
}

// ---------------------------------------------------------------------------
// Nút 2: Xuất file JSON
// ---------------------------------------------------------------------------
async function exportJson() {
  const payload = buildPayload();
  const errors = validatePayload(payload);
  if (errors.length) {
    setStatus(els.exportMsg, `❌ ${errors.slice(0, 3).join(" ")}`, "err");
    return;
  }
  const json = JSON.stringify(payload, null, 2);
  const filename = "hcmus_sync.json";
  const blob = new Blob([json], { type: "application/json" });

  // Cách 1 (ưu tiên): chrome.downloads với data URL – không phụ thuộc object URL
  try {
    const dataUrl = `data:application/json;charset=utf-8,${encodeURIComponent(json)}`;
    await chrome.downloads.download({ url: dataUrl, filename, saveAs: true });
    setStatus(els.exportMsg,
      `✅ Đã xuất ${filename}. Mở Web App → Tab 1 → tải file này lên.`, "ok");
    return;
  } catch (errorDownload) {
    // Cách 2: object URL + thẻ <a download>
    try {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 8000);
      setStatus(els.exportMsg, `✅ Đã tạo ${filename} (tải qua trình duyệt).`, "ok");
      return;
    } catch (errorAnchor) {
      // Cách 3: luôn còn đường lui – copy JSON vào clipboard
      await copyJson();
      setStatus(els.exportMsg,
        "⚠️ Không tải được file trực tiếp. Đã tự động copy JSON vào clipboard – "
        + "hãy dán vào Tab 1 của Web App.", "warn");
    }
  }
}

// ---------------------------------------------------------------------------
// Nút 3: Copy JSON
// ---------------------------------------------------------------------------
async function copyJson() {
  const payload = buildPayload();
  const errors = validatePayload(payload);
  if (errors.length) {
    setStatus(els.exportMsg, `❌ ${errors.slice(0, 3).join(" ")}`, "err");
    return;
  }
  const json = JSON.stringify(payload, null, 2);
  try {
    await navigator.clipboard.writeText(json);
    setStatus(els.exportMsg, "✅ Đã copy JSON vào clipboard. Dán vào Tab 1 của Web App.", "ok");
  } catch (error) {
    const textarea = document.createElement("textarea");
    textarea.value = json;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    setStatus(els.exportMsg, "✅ Đã copy JSON (phương thức dự phòng).", "ok");
  }
}

// ---------------------------------------------------------------------------
// Nút 5: Xoá dữ liệu tạm
// ---------------------------------------------------------------------------
async function clearDraft() {
  draft = {
    timetable: [], drl_progress: [], current_total_score: null, total_max: null,
    semesterDetected: "", studentIdDetected: "", isDemo: false, lastScannedAt: "", notes: [],
  };
  els.studentId.value = "";
  els.semester.value = "";
  setNotes([]);
  setStatus(els.scanResult, "Đã xoá dữ liệu tạm trong phiên popup này.", "idle");
  setStatus(els.exportMsg, "", "idle");
  try {
    await chrome.storage.session.remove(STORAGE_KEY);
  } catch (_error) { /* bỏ qua */ }
  refreshStats();
}

// ---------------------------------------------------------------------------
// Khởi động popup
// ---------------------------------------------------------------------------
async function detectActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const host = tab?.url ? new URL(tab.url).hostname : "";
    els.urlBox.textContent = tab?.url || "";
    if (SUPPORTED_HOSTS[host] === "TIMETABLE") {
      setStatus(els.pageStatus, "🕒 Đang ở cổng Thời khóa biểu CTĐB – sẵn sàng quét.", "ok");
    } else if (SUPPORTED_HOSTS[host] === "DRL") {
      setStatus(els.pageStatus, "🏅 Đang ở cổng Điểm rèn luyện hcmus.drl.vn – sẵn sàng quét.", "ok");
    } else {
      setStatus(els.pageStatus,
        "ℹ️ Tab hiện tại không phải cổng HCMUS được hỗ trợ. Mở portal.ctdb.hcmus.edu.vn "
        + "hoặc hcmus.drl.vn rồi bấm Quét trang.", "warn");
    }
  } catch (error) {
    setStatus(els.pageStatus, `Không đọc được tab: ${error.message || error}`, "err");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  await restoreDraft();
  await detectActiveTab();
  refreshStats();

  els.scanBtn.addEventListener("click", scanCurrentTab);
  els.clearBtn.addEventListener("click", clearDraft);
  els.exportBtn.addEventListener("click", exportJson);
  els.copyBtn.addEventListener("click", copyJson);

  // Cập nhật preview khi người dùng sửa MSSV / học kỳ
  els.studentId.addEventListener("input", () => {
    els.jsonPreview.textContent = JSON.stringify(buildPayload(), null, 2);
  });
  els.defaultCampus.addEventListener("change", () => {
    draft.defaultCampus = els.defaultCampus.value;
    els.jsonPreview.textContent = JSON.stringify(buildPayload(), null, 2);
    persistDraft();
    refreshStats();
  });
  els.semester.addEventListener("input", () => {
    els.jsonPreview.textContent = JSON.stringify(buildPayload(), null, 2);
  });
});
