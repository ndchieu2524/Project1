// Chạy toàn bộ kiểm thử extension: node run_all.js
const { execFileSync } = require('child_process');
const path = require('path');

const tests = ['scan_real_portal.js', 'scan_sync_payload.js'];
let failed = 0;
for (const t of tests) {
  console.log('\n' + '='.repeat(70) + '\n▶ ' + t + '\n' + '='.repeat(70));
  try {
    execFileSync(process.execPath, [path.join(__dirname, t)], { stdio: 'inherit' });
  } catch (e) {
    failed += 1;
  }
}
console.log('\n' + (failed ? `❌ ${failed} bộ test lỗi` : '✅ Tất cả kiểm thử extension đều đạt'));
process.exit(failed ? 1 : 0);
