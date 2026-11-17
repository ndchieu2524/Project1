// Kiểm thử popup.js: tự điền MSSV/học kỳ, chọn cơ sở mặc định, xuất gói Schema 2 hợp lệ
// Chạy: node scan_sync_payload.js
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(ROOT, 'chrome_plugin/popup.html'), 'utf8');
const popupJs = fs.readFileSync(path.join(ROOT, 'chrome_plugin/popup.js'), 'utf8');
const realRows = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures_sync_real.json'), 'utf8')).timetable;

const dom = new JSDOM(html, { url: 'chrome-extension://test/popup.html', runScripts: 'outside-only', pretendToBeVisual: true });
const w = dom.window;
const store = {};
const errors = [];

w.addEventListener('error', (e) => errors.push(String(e.message)));
w.chrome = {
  runtime: { getManifest: () => ({ version: '1.0.0' }), lastError: null, onMessage: { addListener() {} } },
  storage: { session: {
    get: () => Promise.resolve(store),
    set: (o) => { Object.assign(store, o); return Promise.resolve(); },
    remove: () => { Object.keys(store).forEach((k) => delete store[k]); return Promise.resolve(); },
  } },
  tabs: {
    query: () => Promise.resolve([{ id: 1, url: 'https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp' }]),
    sendMessage: () => Promise.resolve({
      type: 'SDRS_SCAN_RESULT', ok: true, scanned_at: new Date().toISOString(),
      payload: {
        section: 'TIMETABLE',
        data: { timetable: realRows, semester: 'HK1_2026_2027', student_id: '25127302', page_title: 'Kết quả ĐKHP' },
        notes: ['Bảng "Các môn đã đăng ký" (CTĐB): 7 buổi học'],
        warnings: [],
      },
    }),
  },
  scripting: { executeScript: () => Promise.resolve() },
};
w.eval(popupJs);

let pass = 0; let fail = 0;
const check = (cond, label) => {
  if (cond) { pass += 1; console.log('  ✅ ' + label); } else { fail += 1; console.log('  ❌ ' + label); }
};

setTimeout(() => {
  const d = w.document;
  d.getElementById('scanBtn').click();
  setTimeout(() => {
    console.log('=== POPUP SAU KHI QUÉT TKB ===');
    check(d.getElementById('studentId').value === '25127302', 'tự điền MSSV từ portal');
    check(d.getElementById('semester').value === 'HK1_2026_2027', 'tự điền học kỳ đã chuẩn hoá');
    check(d.getElementById('statTimetable').textContent === '7', `thống kê TKB = 7 (${d.getElementById('statTimetable').textContent})`);

    // chọn cơ sở mặc định
    const sel = d.getElementById('defaultCampus');
    check(!!sel, 'có ô "Cơ sở mặc định"');
    sel.value = 'NVC';
    sel.dispatchEvent(new w.Event('change', { bubbles: true }));

    let payload = null;
    try { payload = JSON.parse(d.getElementById('jsonPreview').textContent); } catch (e) {}
    console.log('\n=== GÓI JSON SAU KHI CHỌN CƠ SỞ NVC ===');
    check(!!payload, 'preview là JSON hợp lệ');
    if (payload) {
      check(payload.sync_source === 'HCMUS_CHROME_EXTENSION_V1', 'sync_source đúng Schema 2');
      check(payload.timetable.length === 7, `7 dòng TKB (${payload.timetable.length})`);
      check(payload.timetable.every((r) => r.campus === 'NVC'), 'mọi dòng được gán cơ sở NVC');
      check(payload.student_profile.current_total_score === null,
        'KHÔNG gửi 0 giả khi chưa quét DRL (tránh ghi đè điểm)');
      check(payload.student_profile.student_id === '25127302' && payload.student_profile.semester === 'HK1_2026_2027',
        'hồ sơ có MSSV + học kỳ');
    }
    check(errors.length === 0, `không có lỗi runtime (${errors.join('; ') || 'sạch'})`);

    console.log(`\nKẾT QUẢ: ${pass} đạt / ${fail} lỗi`);
    process.exit(fail ? 1 : 0);
  }, 250);
}, 100);
