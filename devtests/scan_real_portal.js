// Kiểm thử content.js trên ĐÚNG bảng "CÁC MÔN ĐÃ ĐĂNG KÝ" của portal.ctdb.hcmus.edu.vn
// Chạy: node scan_real_portal.js   (cần: npm install trong thư mục devtests)
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const code = fs.readFileSync(path.join(ROOT, 'chrome_plugin/content.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'fixtures_real_ctdb.html'), 'utf8');

const dom = new JSDOM(html, {
  url: 'https://portal.ctdb.hcmus.edu.vn/sinh-vien/ket-qua-dkhp',
  runScripts: 'outside-only',
  pretendToBeVisual: true,
});
const w = dom.window;
let listener = null;
w.chrome = { runtime: { onMessage: { addListener: (fn) => { listener = fn; } } } };
Object.defineProperty(w.HTMLElement.prototype, 'offsetWidth', { get() { return 100; } });
w.eval(code);

let out = null;
listener({ type: 'SDRS_SCAN' }, {}, (r) => { out = r; });

const rows = out.payload.data.timetable;
const EXPECTED = [
  ['BAA00005', 'Tuesday', '07:30', '11:10', 'E402'],
  ['BAA00021', 'Monday', '07:30', '11:10', ''],
  ['CSC10008', 'Tuesday', '13:30', '17:10', 'B116'],
  ['CSC10014', 'Monday', '13:30', '17:10', 'C36'],
  ['CSC10014', 'Friday', '07:30', '09:30', '152'],
  ['MTH00006', 'Thursday', '07:30', '11:10', 'E308'],
  ['MTH00006', 'Thursday', '13:30', '15:30', 'E307'],
];

let pass = 0;
let fail = 0;
function check(cond, label) {
  if (cond) { pass += 1; console.log('  ✅ ' + label); }
  else { fail += 1; console.log('  ❌ ' + label); }
}

console.log('=== QUÉT BẢNG CTĐB THẬT ===');
check(out.payload.section === 'TIMETABLE', 'nhận diện đúng section TIMETABLE');
check(rows.length === 7, `tách đúng 7 buổi học (thực tế ${rows.length})`);
check(out.payload.data.semester === 'HK1_2026_2027', `học kỳ chuẩn hoá = HK1_2026_2027 (${out.payload.data.semester})`);
check(out.payload.data.student_id === '25127302', `MSSV = 25127302 (${out.payload.data.student_id})`);

EXPECTED.forEach(([code, day, start, end, room], i) => {
  const r = rows[i] || {};
  check(
    r.course_code === code && r.day_of_week === day && r.start_time === start
      && r.end_time === end && (r.room || '') === room,
    `${code} ${day} ${start}-${end} phòng=${room || '—'}  (nhận: ${r.course_code} ${r.day_of_week} ${r.start_time}-${r.end_time} phòng=${r.room || '—'})`,
  );
});

console.log(`\nKẾT QUẢ: ${pass} đạt / ${fail} lỗi`);
process.exit(fail ? 1 : 0);
