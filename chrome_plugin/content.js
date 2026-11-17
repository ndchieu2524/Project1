/**
 * Smart DRL Assistant – HCMUS Sync · Content Script (Manifest V3)
 *
 * NHIỆM VỤ
 *   Chạy trên đúng 2 tên miền được khai báo trong manifest:
 *     - https://portal.ctdb.hcmus.edu.vn/*  → trích xuất THỜI KHÓA BIỂU
 *     - https://hcmus.drl.vn/*              → trích xuất TIẾN ĐỘ ĐIỂM RÈN LUYỆN
 *
 * NGUYÊN TẮC BẢO MẬT (bắt buộc)
 *   1. KHÔNG đọc/ghi mật khẩu, cookie phiên, hay token của cổng trường.
 *   2. KHÔNG tự động đăng nhập, KHÔNG vượt CAPTCHA, KHÔNG gửi dữ liệu ra ngoài
 *      ngoại trừ việc trả kết quả cho popup của chính extension (thông điệp nội bộ).
 *   3. Chỉ ĐỌC DOM của trang mà sinh viên đã tự đăng nhập và đang mở.
 *   4. Mọi dữ liệu trả về được gắn nhãn nguồn để Web App biết đây là bản trích
 *      xuất từ đâu (portal / drl) – không có dữ liệu mẫu.
 *
 * GIAO THỨC VỚI POPUP
 *   popup.js gửi:  { type: "SDRS_SCAN" }
 *   content.js trả: { type: "SDRS_SCAN_RESULT", payload: { section, data, notes, warnings } }
 *   section ∈ "TIMETABLE" | "DRL" | "UNKNOWN"
 */
(() => {
  "use strict";

  if (window.__SDRS_CONTENT_LOADED__) return;      // tránh inject 2 lần
  window.__SDRS_CONTENT_LOADED__ = true;

  // -------------------------------------------------------------------------
  // Tiện ích
  // -------------------------------------------------------------------------
  const norm = (s) => (s || "").replace(/\s+/g, " ").trim();
  const isVisible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

  function textOf(el) {
    return norm(el ? el.innerText || el.textContent : "");
  }

  /** Text của ô bảng: giữ xuống dòng (khác textOf) để tách tên môn / giờ / phòng. */
  function cellText(el) {
    if (!el) return "";
    // innerText chỉ có khi trình duyệt đã layout (jsdom/trình duyệt headless có thể không có)
    let raw = "";
    try { raw = typeof el.innerText === "string" ? el.innerText : ""; } catch (_e) { raw = ""; }
    if (!raw) {
      // Fallback: chèn "\n" tại ranh giới <br> và block element
      const clone = el.cloneNode(true);
      clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
      clone.querySelectorAll("div,p,tr,li").forEach((node) => node.append("\n"));
      raw = clone.textContent || "";
    }
    return raw
      .replace(/\r/g, "")
      .split("\n")
      .map((line) => line.replace(/[ \t\u00a0]+/g, " ").trim())
      .filter(Boolean)
      .join("\n");
  }

  function collectTables() {
    return Array.from(document.querySelectorAll("table")).filter(isVisible);
  }

  /** Đọc bảng thành ma trận chuỗi, xử lý rowspan/colspan để không lệch cột. */
  function readTableAsMatrix(table) {
    const rows = Array.from(table.querySelectorAll("tr"));
    const matrix = [];
    const pending = {}; // colIndex -> {text, remaining}
    rows.forEach((tr) => {
      const line = [];
      let col = 0;
      const cells = Array.from(tr.children).filter((c) => /^(TD|TH)$/i.test(c.tagName));
      const pushCell = (text) => {
        while (pending[col] && pending[col].remaining > 0) {
          line[col] = pending[col].text;
          pending[col].remaining -= 1;
          if (pending[col].remaining === 0) delete pending[col];
          col += 1;
        }
        line[col] = text;
        col += 1;
      };
      cells.forEach((cell) => {
        const text = cellText(cell);
        const rowspan = Math.max(1, parseInt(cell.getAttribute("rowspan") || "1", 10));
        const colspan = Math.max(1, parseInt(cell.getAttribute("colspan") || "1", 10));
        while (pending[col] && pending[col].remaining > 0) {
          line[col] = pending[col].text;
          pending[col].remaining -= 1;
          if (pending[col].remaining === 0) delete pending[col];
          col += 1;
        }
        for (let i = 0; i < colspan; i += 1) {
          pushCell(text);
          if (rowspan > 1) pending[col - 1] = { text, remaining: rowspan - 1 };
        }
      });
      while (pending[col] && pending[col].remaining > 0) {
        line[col] = pending[col].text;
        pending[col].remaining -= 1;
        if (pending[col].remaining === 0) delete pending[col];
        col += 1;
      }
      // Chuẩn hoá khoảng trắng theo từng dòng nhưng GIỮ xuống dòng để
      // các bộ trích xuất phía sau tách được tên môn / giờ / phòng.
      matrix.push(line.map((v) => String(v || "")
        .split("\n")
        .map((part) => part.replace(/[ \t\u00a0]+/g, " ").trim())
        .filter(Boolean)
        .join("\n")));
    });
    return matrix;
  }

  // -------------------------------------------------------------------------
  // Chuẩn hoá ngày / giờ / cơ sở
  // -------------------------------------------------------------------------
  const DAY_MAP = [
    [/^(thứ\s*2|thu\s*2|mon(day)?|t2)$/i, "Monday"],
    [/^(thứ\s*3|thu\s*3|tue(sday)?|t3)$/i, "Tuesday"],
    [/^(thứ\s*4|thu\s*4|wed(nesday)?|t4)$/i, "Wednesday"],
    [/^(thứ\s*5|thu\s*5|thu(rsday)?|t5)$/i, "Thursday"],
    [/^(thứ\s*6|thu\s*6|fri(day)?|t6)$/i, "Friday"],
    [/^(thứ\s*7|thu\s*7|sat(urday)?|t7)$/i, "Saturday"],
    [/^(chủ\s*nhật|chu\s*nhat|sun(day)?|cn)$/i, "Sunday"],
  ];

  function normalizeDay(raw) {
    const s = norm(raw);
    for (const [re, val] of DAY_MAP) if (re.test(s)) return val;
    // "Thứ Hai" viết chữ
    const words = { hai: "Monday", ba: "Tuesday", bốn: "Wednesday", tu: "Wednesday",
                    năm: "Thursday", nam: "Thursday", sáu: "Friday", sau: "Friday",
                    bảy: "Saturday", bay: "Saturday" };
    const m = s.toLowerCase().match(/thứ\s*([a-zà-ỹ]+)/i);
    if (m && words[m[1]]) return words[m[1]];
    return "";
  }

  function normalizeTime(raw) {
    const s = norm(raw);
    const m = s.match(/(\d{1,2})\s*[:hH.]\s*(\d{2})?/);
    if (!m) return "";
    let h = parseInt(m[1], 10);
    const mn = m[2] ? parseInt(m[2], 10) : 0;
    if (h > 23 || mn > 59) return "";
    return String(h).padStart(2, "0") + ":" + String(mn).padStart(2, "0");
  }

  function guessCampus(locationText) {
    const low = (locationText || "").toLowerCase();
    if (/linh\s*trung/.test(low)) return "Linh Trung";
    if (/nguyễn\s*văn\s*cừ|nguyen\s*van\s*cu|\bnvc\b|q\.?\s*5|quận\s*5/.test(low)) return "NVC";
    if (/online|trực\s*tuyến|truc\s*tuyen|zoom|meet|teams/.test(low)) return "Online";
    return "";
  }

  // -------------------------------------------------------------------------
  // 1) TRÍCH XUẤT THỜI KHÓA BIỂU (portal.ctdb.hcmus.edu.vn)
  // -------------------------------------------------------------------------
  const COURSE_HEADERS = {
    code: /mã\s*(môn|hp|học\s*phần)|course\s*code|mã\s*lớp/i,
    name: /tên\s*(môn|hp|học\s*phần)|course\s*name|tên\s*lớp/i,
    day: /thứ|ngày\s*trong\s*tuần|day/i,
    start: /tiết\s*bắt\s*đầu|giờ\s*bắt\s*đầu|bắt\s*đầu|start/i,
    end: /tiết\s*kết\s*thúc|giờ\s*kết\s*thúc|kết\s*thúc|end/i,
    room: /phòng|room|địa\s*điểm/i,
    campus: /cơ\s*sở|campus|khu/i,
    shift: /tiết|ca\s*học|buổi|giờ\s*học/i,
  };

  function mapHeader(headerText) {
    for (const key of Object.keys(COURSE_HEADERS)) {
      if (COURSE_HEADERS[key].test(headerText)) return key;
    }
    return null;
  }

  /** Bảng dạng cột: dòng đầu là tiêu đề cột. */
  // -----------------------------------------------------------------------
  // ĐỊNH DẠNG THẬT CỦA CỔNG CTĐB (đã kiểm chứng trên portal.ctdb.hcmus.edu.vn):
  //   Bảng "CÁC MÔN ĐÃ ĐĂNG KÝ" gồm các cột:
  //   # | Mã MH | Tên MH | TC | Lớp HP | Học kỳ | T.A | H.L | Lịch LT | Lịch TH | G.Viên LT | G.Viên TH | G.Viên TH2
  //   Ô "Lịch LT" gộp nhiều dòng, mỗi dòng 1 buổi, ví dụ:
  //        T3 07:30-11:10  (E402)
  //        T6 07:30-09:30  (152)
  //   → 1 môn có thể có NHIỀU buổi/tuần ⇒ phải tách thành nhiều dòng thời khóa biểu.
  // -----------------------------------------------------------------------

  /** Tách ô "Lịch LT"/"Lịch TH" thành danh sách buổi học.
   *
   * Định dạng thực tế (đã đối chiếu ảnh chụp cổng CTĐB):
   *   "T3 07:30-11:10\n(E402)"   → Thứ 3, 07:30-11:10, phòng E402
   *   "T2 07:30-11:10"           → Thứ 2, 07:30-11:10, không rõ phòng
   *   "T5 13:30-15:30\n(E307)"   → Thứ 5 (buổi chiều)
   */
  function parseScheduleCell(rawCell) {
    const cell = String(rawCell || "").replace(/\r/g, "").trim();
    if (!cell) return [];

    const sessions = [];
    const blocks = cell.split("\n").map((x) => x.trim()).filter(Boolean);

    let pendingDay = "";
    let pendingTime = null;

    const flush = () => {
      if (!pendingDay || !pendingTime) return;
      const day = normalizeDay(pendingDay);
      const start = normalizeTime(pendingTime[1]);
      const end = normalizeTime(pendingTime[2]);
      if (day && start && end) {
        sessions.push({
          day_of_week: day,
          start_time: start,
          end_time: end,
          room: "",
          raw: norm(`${pendingDay} ${pendingTime[1]}-${pendingTime[2]}`),
        });
      }
      pendingDay = "";
      pendingTime = null;
    };

    for (const block of blocks) {
      const dayMatch = block.match(/^(T[2-7]|CN|Thứ\s*[2-7]|Chủ\s*nhật)/i);
      const timeMatch = block.match(
        /(\d{1,2}\s*[:hH.]\s*\d{2})\s*[-–~]\s*(\d{1,2}\s*[:hH.]\s*\d{2})/,
      );

      if (dayMatch) {
        flush();  // chốt buổi trước
        pendingDay = dayMatch[1];
        pendingTime = timeMatch;
        // Phòng có thể nằm ngay trên CÙNG dòng: "T3 07:30-11:10 (E402)"
        if (timeMatch) {
          const leftover = block.slice(timeMatch.index + timeMatch[0].length);
          const roomMatch = leftover.match(/\(?\s*([A-Za-z0-9.\-]{2,15})\s*\)?/);
          if (roomMatch) {
            const day = normalizeDay(pendingDay);
            const start = normalizeTime(pendingTime[1]);
            const end = normalizeTime(pendingTime[2]);
            if (day && start && end) {
              sessions.push({
                day_of_week: day, start_time: start, end_time: end,
                room: norm(roomMatch[1]), raw: norm(block),
              });
            }
            pendingDay = ""; pendingTime = null;
          }
        }
        continue;
      }

      // Dòng tiếp theo sau buổi học: thường chỉ chứa phòng "(E402)" hoặc "152"
      if (pendingTime) {
        const roomMatch = block.match(/^\(?\s*([A-Za-z0-9.\-]{2,15})\s*\)?$/);
        if (roomMatch) {
          const day = normalizeDay(pendingDay);
          const start = normalizeTime(pendingTime[1]);
          const end = normalizeTime(pendingTime[2]);
          if (day && start && end) {
            sessions.push({
              day_of_week: day, start_time: start, end_time: end,
              room: norm(roomMatch[1]), raw: norm(block),
            });
          }
          pendingDay = ""; pendingTime = null;
        }
      }
    }
    flush();
    return sessions;
  }

  /** Bảng "CÁC MÔN ĐÃ ĐĂNG KÝ" của CTĐB → danh sách dòng thời khóa biểu. */
  function extractFromCtbdRegisteredTable(matrix) {
    if (matrix.length < 2) return [];
    // Tìm dòng tiêu đề có "Mã MH" và cột "Lịch"
    let headerIdx = -1;
    let colCode = -1;
    let colName = -1;
    let colCredits = -1;
    let colClass = -1;
    let scheduleCols = [];

    for (let r = 0; r < Math.min(4, matrix.length); r += 1) {
      matrix[r].forEach((cell, idx) => {
        const c = norm(cell);
        if (/^mã\s*mh|mã\s*môn/i.test(c)) colCode = idx;
        else if (/^tên\s*mh|tên\s*môn/i.test(c)) colName = idx;
        else if (/^tc$|tín\s*chỉ/i.test(c)) colCredits = idx;
        else if (/^lớp\s*hp|lớp\s*học\s*phần/i.test(c)) colClass = idx;
        else if (/^lịch\s*(lt|th|lt-th)/i.test(c)) scheduleCols.push(idx);
      });
      if (colCode >= 0 && colName >= 0 && scheduleCols.length) { headerIdx = r; break; }
    }
    if (headerIdx < 0 || colCode < 0) return [];

    const out = [];
    for (let r = headerIdx + 1; r < matrix.length; r += 1) {
      const row = matrix[r];
      const code = norm(row[colCode] || "");
      const name = norm(row[colName] || "");
      if (!code || !name || /^mã\s*mh/i.test(code)) continue;
      // Bỏ dòng tổng kết / ghi chú
      if (/tổng|ghi\s*chú|tổng\s*cộng/i.test(code + " " + name)) continue;

      const sessions = [];
      scheduleCols.forEach((col) => {
        const cell = row[col] || "";
        if (cell) sessions.push(...parseScheduleCell(cell));
      });
      // Nếu không tách được buổi nào trong ô "Lịch" → bỏ qua (không bịa lịch)
      if (!sessions.length) continue;

      sessions.forEach((session) => {
        out.push({
          course_code: code,
          course_name: name,
          day_of_week: session.day_of_week,
          start_time: session.start_time,
          end_time: session.end_time,
          room: session.room,
          campus: guessCampus(session.room) || "",
          credits: colCredits >= 0 ? norm(row[colCredits] || "") : "",
          class_code: colClass >= 0 ? norm(row[colClass] || "") : "",
          raw_schedule: session.raw,
          synced_from: "CHROME_EXTENSION_PORTAL_CTDB_REGISTERED",
        });
      });
    }
    return out;
  }

  function extractTimetableFromHeaderTable(matrix) {
    if (!matrix.length) return [];
    for (let headerIdx = 0; headerIdx < Math.min(3, matrix.length); headerIdx += 1) {
      const header = matrix[headerIdx];
      const map = {};
      header.forEach((cell, idx) => {
        const key = mapHeader(cell);
        if (key && map[key] === undefined) map[key] = idx;
      });
      const hasCourse = map.code !== undefined || map.name !== undefined;
      const hasTime = (map.start !== undefined) || (map.shift !== undefined) || (map.day !== undefined);
      if (!hasCourse || !hasTime) continue;

      const rows = [];
      for (let r = headerIdx + 1; r < matrix.length; r += 1) {
        const row = matrix[r];
        const get = (key) => (map[key] !== undefined ? norm(row[map[key]] || "") : "");
        let code = get("code");
        let name = get("name");
        const day = normalizeDay(get("day"));
        let start = normalizeTime(get("start"));
        let end = normalizeTime(get("end"));
        // Cột "Tiết" dạng "1-3" hoặc "Tiết 1-3" → quy đổi tiết sang giờ chuẩn HCMUS
        const shiftRaw = get("shift");
        if ((!start || !end) && /\d/.test(shiftRaw)) {
          const range = parseShiftRange(shiftRaw);
          if (range) {
            start = start || range.start;
            end = end || range.end;
          }
        }
        // Cột "Tiết bắt đầu" / "Tiết kết thúc" ghi số tiết (vd 1 và 4) → quy đổi sang giờ
        const startRaw = get("start");
        const endRaw = get("end");
        if (!start || !end) {
          const startPeriod = startRaw.match(/^\s*(\d{1,2})\s*$/);
          const endPeriod = endRaw.match(/^\s*(\d{1,2})\s*$/);
          if (startPeriod && PERIOD_TIMES[parseInt(startPeriod[1], 10)]) {
            start = start || PERIOD_TIMES[parseInt(startPeriod[1], 10)][0];
          }
          if (endPeriod && PERIOD_TIMES[parseInt(endPeriod[1], 10)]) {
            end = end || PERIOD_TIMES[parseInt(endPeriod[1], 10)][1];
          }
          // "Tiết 1-4" trong cùng 1 ô
          if (!start || !end) {
            const combined = parseShiftRange(`${startRaw} ${endRaw}`);
            if (combined) {
              start = start || combined.start;
              end = end || combined.end;
            }
          }
        }
        const room = get("room");
        const campus = guessCampus(get("campus") || room || name);
        if (!code && !name) continue;
        if (!code) code = name.slice(0, 12);
        rows.push({
          course_code: code,
          course_name: name || code,
          day_of_week: day || "",
          start_time: start,
          end_time: end,
          room,
          campus,
          synced_from: "CHROME_EXTENSION_PORTAL_CTDB",
        });
      }
      const usable = rows.filter((r) => r.course_code && r.start_time && r.end_time && r.course_code !== r.course_name);
      if (usable.length) return usable;
    }
    return [];
  }

  /** Bảng thời khóa biểu dạng "lưới": cột = thứ, ô = môn + giờ + phòng. */
  function extractTimetableFromGridTable(matrix) {
    if (matrix.length < 2) return [];
    const headerHeader = matrix[0];
    const dayColumns = {};
    headerHeader.forEach((cell, idx) => {
      const day = normalizeDay(cell);
      if (day) dayColumns[idx] = day;
    });
    if (!Object.keys(dayColumns).length) return [];

    const rows = [];
    for (let r = 1; r < matrix.length; r += 1) {
      const row = matrix[r];
      for (const colStr of Object.keys(dayColumns)) {
        const cell = row[parseInt(colStr, 10)];
        if (!cell || cell.length < 6) continue;
        // Ô chứa xuống dòng thật (tên môn / giờ / phòng) → ưu tiên dòng đầu làm tên môn
        const firstLine = cell.split("\n").map((x) => norm(x)).filter(Boolean)[0] || "";
        const codeMatch = cell.match(/\b[A-Z]{2,5}\d{4,6}\b/);
        const times = cell.match(/(\d{1,2}\s*[:hH.]\s*\d{2})\s*[-–~]\s*(\d{1,2}\s*[:hH.]\s*\d{2})/);
        if (!codeMatch && !times) continue;
        // Lấy dòng chứa mã môn làm tên môn, bỏ mã và giờ/phòng để tên sạch
        const cellLines = String(cell).split(/\n|\s{2,}|,\s*/)
          .map((x) => norm(x))
          .filter((x) => x && !/^(phòng|p\.|giờ|thời\s*gian)/i.test(x) && !/\d{1,2}[:h]\d{2}/.test(x));
        const titleLine = (codeMatch && firstLine.includes(codeMatch[0]) ? firstLine : "")
          || cellLines.find((line) => codeMatch && line.includes(codeMatch[0]))
          || (firstLine && !/\d{1,2}[:h]\d{2}/.test(firstLine) ? firstLine : "")
          || cellLines[0] || norm(cell).slice(0, 80);
        const cleanName = norm(
          codeMatch ? titleLine.replace(codeMatch[0], "").replace(/^[-–:.\s]+/, "") : titleLine,
        ) || (codeMatch ? codeMatch[0] : norm(cell).slice(0, 40));
        rows.push({
          course_code: codeMatch ? codeMatch[0] : cell.slice(0, 12),
          course_name: cleanName.slice(0, 120),
          day_of_week: dayColumns[colStr],
          start_time: times ? normalizeTime(times[1]) : "",
          end_time: times ? normalizeTime(times[2]) : "",
          room: (cell.match(/[A-Z]\d{2,3}[A-Z]?/g) || [""]).pop(),
          campus: guessCampus(cell),
          synced_from: "CHROME_EXTENSION_PORTAL_CTDB_GRID",
        });
      }
    }
    return rows.filter((r) => r.start_time && r.end_time);
  }

  /** Quy đổi "Tiết 1-3" của HCMUS sang giờ. Bảng tiết chuẩn (buổi sáng/chiều). */
  const PERIOD_TIMES = {
    1: ["07:30", "08:20"], 2: ["08:20", "09:10"], 3: ["09:10", "10:00"],
    4: ["10:00", "10:50"], 5: ["10:50", "11:40"],
    6: ["13:30", "14:20"], 7: ["14:20", "15:10"], 8: ["15:10", "16:00"],
    9: ["16:00", "16:50"], 10: ["16:50", "17:40"],
    11: ["17:40", "18:30"], 12: ["18:30", "19:20"],
  };

  function parseShiftRange(raw) {
    const text = norm(raw);
    const range = text.match(/(\d{1,2})\s*[-–~]\s*(\d{1,2})/);
    if (range) {
      const from = parseInt(range[1], 10);
      const to = parseInt(range[2], 10);
      if (!PERIOD_TIMES[from] || !PERIOD_TIMES[to]) return null;
      return { start: PERIOD_TIMES[from][0], end: PERIOD_TIMES[to][1] };
    }
    // Cột "Tiết" chỉ ghi MỘT số duy nhất (vd "3") → coi là 1 tiết
    const single = text.match(/^\s*(\d{1,2})\s*$/);
    if (single) {
      const period = parseInt(single[1], 10);
      if (PERIOD_TIMES[period]) return { start: PERIOD_TIMES[period][0], end: PERIOD_TIMES[period][1] };
    }
    return null;
  }

  function extractTimetable() {
    const tables = collectTables();
    const notes = [];
    let rows = [];
    for (const table of tables) {
      const matrix = readTableAsMatrix(table);
      // 1) Định dạng thật của CTĐB: bảng "CÁC MÔN ĐÃ ĐĂNG KÝ" (ô Lịch LT gộp)
      const byRegistered = extractFromCtbdRegisteredTable(matrix);
      if (byRegistered.length) {
        rows = rows.concat(byRegistered);
        notes.push(`Bảng "Các môn đã đăng ký" (CTĐB): ${byRegistered.length} buổi học.`);
        continue;
      }
      // 2) Bảng có tiêu đề cột ngày/giờ riêng
      const byHeader = extractTimetableFromHeaderTable(matrix);
      if (byHeader.length) {
        rows = rows.concat(byHeader);
        notes.push(`Bảng có tiêu đề cột: ${byHeader.length} môn.`);
        continue;
      }
      const byGrid = extractTimetableFromGridTable(matrix);
      if (byGrid.length) {
        rows = rows.concat(byGrid);
        notes.push(`Bảng lưới thứ: ${byGrid.length} môn.`);
      }
    }
    if (!rows.length) {
      // Fallback: quét text của các khối "course card"
      const cards = Array.from(document.querySelectorAll(
        "[class*='mon-hoc'], [class*='course'], [class*='lich'], .card, .subject"));
      cards.slice(0, 60).forEach((card) => {
        const text = textOf(card);
        const codeMatch = text.match(/\b[A-Z]{2,5}\d{4,6}\b/);
        const times = text.match(/(\d{1,2}\s*[:hH.]\s*\d{2})\s*[-–~]\s*(\d{1,2}\s*[:hH.]\s*\d{2})/);
        const day = normalizeDay((text.match(/thứ\s*\d|chủ\s*nhật/i) || [""])[0]);
        if (!codeMatch || !times || !day) return;
        rows.push({
          course_code: codeMatch[0],
          course_name: text.slice(0, 120),
          day_of_week: day,
          start_time: normalizeTime(times[1]),
          end_time: normalizeTime(times[2]),
          room: (text.match(/[A-Z]\d{2,3}[A-Z]?/g) || [""]).pop(),
          campus: guessCampus(text),
          synced_from: "CHROME_EXTENSION_PORTAL_CTDB_CARD",
        });
      });
      if (rows.length) notes.push(`Quét thẻ môn học: ${rows.length} mục.`);
    }
    return { rows, notes };
  }

  // -------------------------------------------------------------------------
  // 2) TRÍCH XUẤT ĐIỂM RÈN LUYỆN (hcmus.drl.vn)
  // -------------------------------------------------------------------------
  const SCORE_LABEL_RE = /(tổng\s*điểm|điểm\s*rèn\s*luyện|điểm\s*hiện\s*tại|tổng\s*cộng|điểm\s*đạt)/i;
  const SEMESTER_RE = /(HK\s*\d\s*[-_/]?\s*\d{4}\s*[-_/]\s*\d{4}|Học\s*kỳ\s*\d[^\n]{0,20}\d{4}\s*[-–]\s*\d{4})/i;
  const CRITERION_CODE_RE = /\b(TC[_\s.-]?\d+(?:\.\d+)?)\b/i;

  /** Chuẩn hoá mọi cách viết học kỳ về "HK1_2026_2027". */
  function normalizeSemester(raw) {
    const s = norm(raw);
    if (!s) return "";
    const m = s.match(/(HK|Học\s*kỳ|HKII?|HKI{1,2}|III?)?\s*([123])?\s*[-_/\s]?\s*(20\d{2})\s*[-_–]\s*(20\d{2})/i);
    if (m) {
      const rawTerm = (m[1] || "").toLowerCase();
      let term = m[2] || "";
      if (!term) {
        if (/iii/.test(rawTerm)) term = "3";
        else if (/ii$/.test(rawTerm)) term = "2";
        else term = "1";
      }
      return `HK${term}_${m[3]}_${m[4]}`;
    }
    const m2 = s.match(/(HK|Học\s*kỳ)\s*([123])?\s*[-_/\s]?\s*(20\d{2})/i);
    if (m2) return `HK${m2[2] || "1"}_${m2[3]}`;
    return "";
  }

  function detectSemester() {
    const bodyText = textOf(document.body).slice(0, 20000);
    const m = bodyText.match(SEMESTER_RE);
    if (m) {
      const normalized = normalizeSemester(m[0]);
      if (normalized) return normalized;
    }
    // Dự phòng: quét <option>/<select> như trang CTĐB
    const portalSemester = detectPortalSemester();
    return portalSemester || "";
  }

  function detectStudentId() {
    const bodyText = textOf(document.body);
    const m = bodyText.match(/(?:MSSV|mã\s*số\s*sinh\s*viên)[:\s]*([0-9]{6,12})/i)
      || bodyText.match(/\b(\d{8})\b/);
    return m ? m[1] : "";
  }

  function parseScoreMatch(text) {
    // Ưu tiên dạng "61/100" hoặc "61 / 100"
    const withMax = text.match(/(\d{1,3}(?:[.,]\d)?)\s*\/\s*(\d{1,3})/);
    if (withMax) {
      return {
        score: parseFloat(withMax[1].replace(",", ".")),
        max: parseFloat(withMax[2]),
      };
    }
    // Dạng "Tổng điểm: 61 điểm" – yêu cầu số đứng sau nhãn điểm, KHÔNG lấy số trong "HK1 2026-2027"
    const labeled = text.match(
      /(?:tổng\s*điểm|điểm\s*(?:rèn\s*luyện|hiện\s*tại|đạt|tổng))[^\d]{0,18}(\d{1,3}(?:[.,]\d)?)/i,
    );
    if (labeled) {
      return { score: parseFloat(labeled[1].replace(",", ".")), max: null };
    }
    return null;
  }

  function extractTotalScore() {
    const SKIP_TAGS = new Set(["H1", "H2", "H3", "H4", "H5", "H6", "A"]);
    const candidates = Array.from(document.querySelectorAll(
      "div, span, p, td, th, strong, b, label, li"));
    const found = [];
    for (const el of candidates) {
      if (!isVisible(el) || el.children.length > 2) continue;
      if (SKIP_TAGS.has(el.tagName)) continue;
      const text = textOf(el);
      if (!text || text.length > 140) continue;
      if (!SCORE_LABEL_RE.test(text)) continue;
      const parsed = parseScoreMatch(text);
      if (!parsed) continue;
      if (!(parsed.score >= 0 && parsed.score <= 150)) continue;
      if (parsed.max !== null && parsed.max !== 0) {
        // Điểm phải nằm trong [0, max] (chịu sai số làm tròn)
        if (parsed.score > parsed.max + 0.5) continue;
        // Ưu tiên tuyệt đối: có dạng x/max
        return { score: parsed.score, max: parsed.max, evidence: text };
      }
      found.push({ score: parsed.score, max: null, evidence: text });
    }
    if (found.length) {
      // Không có dạng x/max → lấy giá trị đầu tiên hợp lệ (đã lọc theo nhãn "tổng điểm")
      const best = found[0];
      return { score: best.score, max: null, evidence: best.evidence };
    }
    const gauge = document.querySelector("[role='progressbar'], [aria-valuenow]");
    if (gauge) {
      const value = parseFloat(gauge.getAttribute("aria-valuenow"));
      const max = parseFloat(gauge.getAttribute("aria-valuemax") || "");
      if (!Number.isNaN(value)) {
        return { score: value, max: Number.isNaN(max) ? null : max, evidence: "aria-valuenow" };
      }
    }
    return null;
  }

  /**
   * Đọc danh mục tiêu chí ĐRL từ trang hcmus.drl.vn.
   *
   * CẤU TRÚC THẬT của trang (đối chiếu ảnh chụp 2026-11-16):
   *   | ⌄ | 1 | Trách nhiệm chấp hành pháp luật và nội quy, quy chế của nhà trường | Bắt đầu | Kết thúc | 0 |
   *
   * Tức là: số thứ tự (1..5), tên tiêu chí, nút "Bắt đầu"/"Kết thúc", và điểm (0).
   * KHÔNG có cột "mã tiêu chí" dạng TC_1.1, KHÔNG có cột "điểm tối đa".
   *
   * Bản cũ chỉ tìm mã TC_* nên trả về RỖNG → app báo "chưa có bảng điểm theo từng
   * tiêu chí" dù người dùng đã quét đúng trang. Nay nhận diện thêm cấu trúc số
   * thứ tự và trả mã dạng TC_1 … TC_5 (khớp khung quy chế).
   */
  function extractCriteriaRows() {
    const rows = [];
    const tables = collectTables();

    const pickNumber = (value) => {
      const m = norm(value).match(/(\d{1,3}(?:[.,]\d)?)/);
      return m ? parseFloat(m[1].replace(",", ".")) : null;
    };
    // Cột "trạng thái" — không phải điểm
    const isStatusCell = (v) => /bắt\s*đầu|kết\s*thúc|đang\s*thực\s*hiện|hoàn\s*thành/i.test(v || "");

    for (const table of tables) {
      const matrix = readTableAsMatrix(table);
      if (matrix.length < 2) continue;
      const header = matrix[0];
      const looksLikeHeader = header.some((c) => /tiêu\s*chí|nội\s*dung|mục|điểm/i.test(c));

      // --- Kiểu A: có mã tiêu chí TC_* (một số trang/kỳ hiển thị như vậy) ---
      const hasCodeStyle = matrix.slice(1).some((r) => r.some((c) => CRITERION_CODE_RE.test(c)));
      if (hasCodeStyle) {
        const colCode = header.findIndex((c) => /mã|code/i.test(c));
        const colName = header.findIndex((c, i) => i !== colCode
          && /tên|nội\s*dung|diễn\s*giải|tiêu\s*chí/i.test(c));
        const colMax = header.findIndex((c) => /tối\s*đa|max|thang\s*điểm/i.test(c));
        const colScore = header.findIndex((c, i) => i !== colMax
          && /điểm\s*(hiện|đạt|tự)|hiện\s*có|đã\s*đạt|score|tự\s*đánh\s*giá/i.test(c));
        for (let r = 1; r < matrix.length; r += 1) {
          const row = matrix[r];
          let code = colCode >= 0 ? row[colCode] : (row.find((c) => CRITERION_CODE_RE.test(c)) || "");
          const codeMatch = (code || "").match(CRITERION_CODE_RE);
          if (!codeMatch) continue;
          code = codeMatch[1].replace(/[\s.-]+/g, "_").toUpperCase();
          const current = colScore >= 0 ? pickNumber(row[colScore]) : pickNumber(row.join(" "));
          const max = colMax >= 0 ? pickNumber(row[colMax]) : null;
          const nameValue = colName >= 0 ? norm(row[colName]) : "";
          rows.push({
            criterion_code: code,
            name: nameValue && nameValue.toUpperCase() !== code ? nameValue : "",
            current_score: current,
            max_score: max,
            mandatory: false,
          });
        }
        if (rows.length) return rows;
      }

      // --- Kiểu B: số thứ tự 1..5 như trang thật ---
      // Không cần header: nhận dòng nào có 1 ô là số 1..9 VÀ 1 ô là câu mô tả dài.
      const body = looksLikeHeader ? matrix.slice(1) : matrix;
      for (const row of body) {
        if (!Array.isArray(row) || !row.length) continue;

        // số thứ tự: ô đầu tiên khớp đúng /^\d{1,2}$/
        let idxPos = -1;
        let orderNo = null;
        for (let i = 0; i < row.length; i += 1) {
          const cell = norm(row[i]);
          if (/^\d{1,2}$/.test(cell)) {
            idxPos = i;
            orderNo = parseInt(cell, 10);
            break;
          }
        }
        if (idxPos < 0 || orderNo == null || orderNo < 1 || orderNo > 20) continue;

        // tên tiêu chí: ô dài nhất, không phải số, không phải trạng thái
        let nameCell = "";
        let namePos = -1;
        for (let i = 0; i < row.length; i += 1) {
          if (i === idxPos) continue;
          const cell = norm(row[i]);
          if (!cell || /^\d+([.,]\d+)?$/.test(cell) || isStatusCell(cell)) continue;
          if (cell.length > nameCell.length) { nameCell = cell; namePos = i; }
        }
        if (nameCell.length < 12) continue;   // quá ngắn → không phải tên tiêu chí

        // điểm hiện có: ô số cuối cùng sau tên tiêu chí, bỏ qua ô trạng thái
        let current = null;
        for (let i = row.length - 1; i > namePos; i -= 1) {
          const cell = norm(row[i]);
          if (!cell || isStatusCell(cell)) continue;
          if (/^\d{1,3}([.,]\d+)?$/.test(cell)) {
            current = parseFloat(cell.replace(",", "."));
            break;
          }
        }

        rows.push({
          criterion_code: `TC_${orderNo}`,
          name: nameCell,
          current_score: current,
          max_score: null,       // trang không hiển thị điểm tối đa
          mandatory: false,
        });
      }
      if (rows.length) break;
    }
    return rows;
  }

  function extractDrl() {
    const notes = [];
    const warnings = [];
    const total = extractTotalScore();
    const criteria = extractCriteriaRows();
    const semester = detectSemester();
    const studentId = detectStudentId();

    if (total) notes.push(`Tổng điểm đọc được: ${total.score}${total.max ? "/" + total.max : ""}.`);
    if (criteria.length) notes.push(`Bảng tiêu chí: ${criteria.length} dòng.`);
    if (!total && !criteria.length) {
      warnings.push("Không tìm thấy tổng điểm lẫn bảng tiêu chí trên trang. Hãy mở đúng trang "
        + "“Điểm rèn luyện” sau khi đăng nhập rồi bấm Quét trang ở popup.");
    }
    if (total && !total.max) {
      warnings.push("Trang không hiển thị điểm tối đa → hệ thống để trống, không tự suy diễn thang 100.");
    }
    return {
      student_id: studentId,
      semester: semester,
      current_total_score: total ? total.score : null,
      total_max: total ? total.max : null,
      criteria,
      evidence: total ? total.evidence : "",
      notes,
      warnings,
    };
  }

  // -------------------------------------------------------------------------
  // Router: quyết định trích xuất gì theo tên miền
  // -------------------------------------------------------------------------
  function detectSection() {
    const host = location.hostname;
    const path = location.pathname.toLowerCase();
    const bodyText = textOf(document.body).toLowerCase();

    if (host === "portal.ctdb.hcmus.edu.vn") {
      // Trang thời khóa biểu / kết quả đăng ký học phần đều chứa bảng môn đã đăng ký
      const isTimetablePage = /thoi-khoa-bieu|ket-qua-dkhp|lich-hoc|dang-ky-hoc-phan|tkb/.test(path)
        || /các\s*môn\s*đã\s*đăng\s*ký|lịch\s*lt|thời\s*khóa\s*biểu/.test(bodyText);
      return isTimetablePage || collectTables().length ? "TIMETABLE" : "TIMETABLE";
    }
    if (host === "hcmus.drl.vn") {
      return "DRL";
    }
    return "UNKNOWN";
  }

  /** Lấy học kỳ đang chọn ở portal (select "HK1 2026-2027"). */
  function detectPortalSemester() {
    const select = document.querySelector("select");
    if (select) {
      const opt = select.options[select.selectedIndex];
      const text = norm(opt ? opt.textContent : "");
      const m = text.match(/HK\s*(\d)\s*[-_/]?\s*(\d{4})\s*[-–/]\s*(\d{4})/i);
      if (m) return `HK${m[1]}_${m[2]}_${m[3]}`;
    }
    const page = textOf(document.body).match(/HK\s*\d\s*[-–]\s*\d{4}\s*[-–]\s*\d{4}/i);
    if (page) return page[0].replace(/\s+/g, "_").replace(/[-–]/g, "_");
    return "";
  }

  /** Lấy MSSV từ khối thông tin "Sinh Viên / Đăng Ký Học Phần" hoặc "25127302 - ĐỖ TIẾN DŨNG". */
  function detectPortalStudentId() {
    const body = textOf(document.body);
    const labeled = body.match(/(?:MSSV|mã\s*số\s*sinh\s*viên)\s*[:\s]*([0-9]{6,12})/i);
    if (labeled) return labeled[1];
    // Định dạng "25127302 - HỌ TÊN" (kèm MSSV 8 số ở đầu cụm)
    const m = body.match(/\b(\d{8})\s*[-–]\s*([A-ZÀ-Ỹ][^\n\-–]{2,40})/);
    if (m) return m[1];
    const any8 = body.match(/\b(\d{8})\b/);
    return any8 ? any8[1] : "";
  }

  function scanPage() {
    const section = detectSection();
    if (section === "TIMETABLE") {
      const { rows, notes } = extractTimetable();
      const semester = detectPortalSemester();
      const studentId = detectPortalStudentId();
      if (semester) notes.push(`Học kỳ đang chọn: ${semester}.`);
      if (studentId) notes.push(`MSSV nhận diện: ${studentId}.`);
      return {
        section,
        data: {
          timetable: rows,
          semester,
          student_id: studentId,
          page_title: document.title,
        },
        notes,
        warnings: rows.length ? [] : [
          "Không đọc được bảng thời khóa biểu. Hãy mở trang “Kết quả ĐKHP” hoặc “Thời khóa biểu” "
          + "sau khi đăng nhập, rồi bấm Quét trang lần nữa.",
        ],
      };
    }
    if (section === "DRL") {
      const drl = extractDrl();
      return { section, data: drl, notes: drl.notes, warnings: drl.warnings };
    }
    return {
      section: "UNKNOWN",
      data: {},
      notes: [],
      warnings: ["Trang hiện tại không thuộc 2 cổng được hỗ trợ "
        + "(portal.ctdb.hcmus.edu.vn hoặc hcmus.drl.vn)."],
    };
  }

  // -------------------------------------------------------------------------
  // Lắng nghe yêu cầu từ popup
  // -------------------------------------------------------------------------
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "SDRS_SCAN") return undefined;
    try {
      const result = scanPage();
      sendResponse({
        type: "SDRS_SCAN_RESULT",
        ok: true,
        url: location.href,
        scanned_at: new Date().toISOString(),
        payload: result,
      });
    } catch (error) {
      sendResponse({
        type: "SDRS_SCAN_RESULT",
        ok: false,
        url: location.href,
        error: String(error && error.message ? error.message : error),
      });
    }
    return true; // giữ kênh mở cho sendResponse bất đồng bộ
  });

  // Thông báo nhỏ cho người dùng biết extension đã sẵn sàng trên trang này
  const badge = document.createElement("div");
  badge.textContent = "🎓 Smart DRL Sync đã sẵn sàng – bấm biểu tượng extension để quét";
  badge.style.cssText = [
    "position:fixed", "right:16px", "bottom:16px", "z-index:2147483647",
    "background:#0b2a5b", "color:#fff", "font:12px/1.4 system-ui,sans-serif",
    "padding:8px 12px", "border-radius:10px", "box-shadow:0 4px 14px rgba(0,0,0,.25)",
    "opacity:0", "transition:opacity .25s ease", "pointer-events:none", "max-width:340px",
  ].join(";");
  document.addEventListener("DOMContentLoaded", () => {
    document.body.appendChild(badge);
    requestAnimationFrame(() => { badge.style.opacity = "1"; });
    setTimeout(() => { badge.style.opacity = "0"; }, 5000);
  });
})();
