# Hướng dẫn sử dụng – Smart DRL Assistant HCMUS

Tài liệu này hướng dẫn **thao tác thực tế trên 8 tab** và kèm **kịch bản trình bày 7 phút**
trước giảng viên.

> ⚠️ **Bản `2.3.0-REALONLY` KHÔNG có dữ liệu mẫu.** Kho khởi động **rỗng**, mọi hoạt động đều
> được thu thập thật từ 4 cổng công khai của trường. Không còn nút nào tạo/khôi phục dữ liệu
> giả — kể cả khi database trống hay khi bấm nhầm.


Tài liệu này hướng dẫn **thao tác thực tế trên 8 tab** và kèm **kịch bản trình bày 7 phút**
để trình bày trước giảng viên.

> Không có số liệu mẫu: hoạt động đến từ 4 cổng công khai, thời khóa biểu và bảng điểm đến từ
> Chrome Extension khi bạn tự đăng nhập.

---

## 0. Chuẩn bị (1 phút)

1. `streamlit run app.py` → mở `http://localhost:8501`.
2. Lần đầu chạy: DB tự tạo **rỗng**. Mở **Tab 🌐 Thu thập TỰ ĐỘNG** và bấm
   **🚀 Bắt đầu thu thập** (app cũng tự thu thập ở lần mở đầu tiên).
3. (Tuỳ chọn) Sidebar → chọn **Gemini/OpenAI** + nhập API Key → **Kiểm tra kết nối**.
   Không có key vẫn chạy 100% bằng NLP nội bộ.

---

## Tab 1 – 📊 Dashboard & Đồng bộ Plugin

**Mục đích:** thấy ngay “tôi đang ở đâu so với mục tiêu” và nạp dữ liệu từ extension.

1. Bốn thẻ metric phía trên:
   - ① Điểm hiện tại đã có (vd 61)
   - ② Điểm từ hoạt động **đã xác minh** (vd +5)
   - ③ Điểm từ hoạt động **tiềm năng** (vd +5, chỉ tham khảo)
   - ④ Mục tiêu học kỳ (vd 90) + khoảng còn thiếu
2. Khu **Đồng bộ từ Chrome Extension**:
   - **Tải file `hcmus_sync.json`** hoặc **Dán chuỗi JSON** → bấm **📥 Áp dụng gói JSON vào hồ sơ**.
   - Hoặc quét bằng Chrome Extension rồi xuất `hcmus_sync.json` và tải lên.
   - Hệ thống ghi: tiêu chí + tên + điểm tối đa, hồ sơ, tiến độ từng tiêu chí, **toàn bộ thời
     khóa biểu**. Một gói chỉ áp dụng 1 lần/phiên (chống ghi lặp).
   - **An toàn dữ liệu:** gói **chỉ có thời khóa biểu** (bạn mới quét trang CTĐB, chưa quét
     `hcmus.drl.vn`) sẽ **không** ghi đè điểm rèn luyện và bảng tiêu chí đã đồng bộ trước đó —
     app giữ nguyên và hiện cảnh báo vàng. Ngược lại, gói có điểm mới sẽ cập nhật bình thường.
3. Nếu bạn **chỉ nhập tổng điểm** (không có bảng tiêu chí) → banner đỏ:
   > “Bạn mới nhập tổng điểm; hệ thống chưa biết tiêu chí nào còn thiếu…”
   (Đúng yêu cầu: **không chia điểm ngẫu nhiên** cho tiêu chí.)
4. Khu **Đặt mục tiêu học kỳ**: sửa mục tiêu / học kỳ / MSSV / họ tên / khoa → **Lưu mục tiêu**.
5. Bên dưới: bảng tiến độ từng tiêu chí, **Thời khóa biểu CTĐB đã đồng bộ**, tóm tắt lộ trình,
   và **Nhật ký thao tác (AuditLogs)**.

---

## Tab 2 – 📥 Thu thập & Bóc tách bài đăng OSA

Bốn tiểu tab tương ứng 4 phương thức nạp hợp lệ:

### 🅐 Dán URL + nội dung bài đăng
1. Nhập URL (mặc định `https://www.facebook.com/osa.hcmus`).
2. Dán nội dung bài đăng công khai vào ô lớn.
3. **🚀 Phân tích & Lưu Database** (hoặc **👁️ Chỉ phân tích** để xem trước).
4. Kết quả hiển thị:
   - Nhãn (`POTENTIAL_DRL`, `INSUFFICIENT_INFO`…) + lý do.
   - Bảng 4 nhóm thông tin: **Thời gian / Địa điểm / Nội dung / Điểm ĐRL**; ô nào thiếu sẽ đỏ.
   - Các **giả định** đã dùng (vd “không ghi giờ kết thúc → giả định 2 giờ”).
   - Trích dẫn câu nêu điểm (`score_evidence`).
   - **JSON Schema 1** đầy đủ + nút tải báo cáo.
   - Gợi ý **liên kết sự kiện gốc** nếu đây là bài nhắc hạn / đổi lịch / công bố kết quả.

### 🅑 Nhập hàng loạt CSV/Excel
1. Tải **file CSV mẫu** để xem cấu trúc (`url`, `content`, `published_at`, `external_post_id`).
2. Tải file lên → chọn đúng cột **nội dung** (và cột URL/hạn/ID nếu có).
3. **🚀 Phân tích & Lưu toàn bộ** → thanh tiến trình + tổng kết số nhãn.

### 🅒 Tải ảnh poster (OCR)
- Cần **Gemini API Key** ở sidebar. Ảnh → **🔍 Trích xuất văn bản từ ảnh** → sửa lại nếu cần →
  **🧠 Phân tích & Lưu Database**.
- Chưa có key: hệ thống nói rõ chưa OCR được và hướng dẫn dán văn bản (không giả vờ).

- Hoặc chọn 1 bài mẫu → **🔬 Phân tích bài mẫu đã chọn** để xem chi tiết bóc tách.

---

## Tab 3 – 🗂️ Kho hoạt động & cảnh báo dữ liệu khuyết

1. Chọn bộ lọc trạng thái: *Tất cả / Tiềm năng / Đã xác minh / Thiếu thông tin / Không liên quan /
   Chưa rõ quyền lợi ĐRL*.
2. Lọc thêm: từ khoá, tiêu chí, cơ sở, chỉ dòng thiếu dữ liệu, ẩn hoạt động đã diễn ra.
3. Bảng Pandas: **ô đỏ** = trường bị khuyết (Thời gian / Địa điểm / Nội dung / Điểm);
   cột **Nhãn** được tô màu theo trạng thái. Nút **Xuất CSV**.
4. Khu **✅ Duyệt & cập nhật hoạt động (Admin)**:
   - Chọn hoạt động → đổi **Nhãn**, **Trạng thái xác minh**, **Điểm ĐRL**, **Mã tiêu chí**.
   - **Ghi chú bắt buộc** khi chuyển sang `VERIFIED_DRL`; hệ thống tự đồng bộ trạng thái
     `ADMIN_APPROVED` để dữ liệu không tự mâu thuẫn.
   - **Gắn vào sự kiện gốc** (`parent_activity_id`) cho bài nhắc hạn/đổi lịch/kết quả.
5. Mở rộng **📄 Xem bài đăng gốc**: URL, `fetch_method`, `collected_at`, `content_hash`,
   cây liên kết sự kiện, cảnh báo nếu cùng `content_hash` xuất hiện nhiều lần (MVP cho phép trùng).

---

## Tab 4 – 🧭 Lộ trình ĐRL tối ưu (NetworkX)

1. Chỉnh **thời gian đệm** (0–60 phút), bật/tắt **ưu tiên hoạt động đã xác minh**,
   bật **cho phép hoạt động đã kết thúc** nếu muốn kiểm thử.
2. Xem 5 thẻ: tổng điểm lộ trình, phần **đã xác minh**, phần **tiềm năng**, dự phóng,
   và khoảng còn thiếu so với mục tiêu.
3. Danh sách hoạt động theo thứ tự thời gian (xanh = đã xác minh, vàng = tiềm năng), kèm
   **gợi ý di chuyển giữa cơ sở** và **hạn đăng ký còn bao nhiêu ngày**.
4. **✨ Sinh lời giải thích lộ trình** → đoạn giải thích (AI nếu có key, không thì template
   nội bộ); chỉ diễn giải số liệu thật của lộ trình.
5. Đồ thị **NetworkX DiGraph**: đỉnh = hoạt động hợp lệ, cạnh đỏ = thuộc lộ trình tối ưu.
6. Mở rộng **🔬 So sánh 2 phương pháp tối ưu**:
   - (a) `nx.dag_longest_path` – nhanh nhưng có thể **vượt trần tiêu chí**.
   - (b) **Quy hoạch động trên DAG** – tôn trọng `max_score` (kết quả chính).
7. Cột phải: **hoạt động bị loại** – trùng giờ học CTĐB (kèm tiết học trùng) và lý do dữ liệu.
8. Bên dưới: **Danh sách khám phá** – hoạt động `EVENT_CANDIDATE`/`INSUFFICIENT_INFO`.

---

## Tab 5 – 📜 Quản lý quy chế ĐRL

1. Thẻ tổng quan: số tiêu chí, tổng điểm tối đa (cảnh báo nếu ≠ 100), số tiêu chí bắt buộc.
2. Bảng danh mục: mã, tên, nhóm, điểm tối đa, bắt buộc, minh chứng, trích dẫn quy chế.
3. **Xem chi tiết** – kèm thanh tiến độ của bạn cho tiêu chí đó.
4. **Thêm tiêu chí** – kiểm tra trùng mã.
5. **Sửa / Xoá** – cẩn trọng: xoá tiêu chí đang có tiến độ sẽ để lại dữ liệu mồ côi.
6. **Nhập hàng loạt** CSV/Excel (có file mẫu) hoặc cập nhật từ gói `hcmus_sync.json` (Tab 1).
7. **📜 Nạp khung tiêu chí theo Quy chế ĐRL** khi muốn nạp lại khung chuẩn.

---

## Tab 6 – 🧪 Thực nghiệm & Đánh giá mô hình ML

1. Chỉnh **tỉ lệ test**, **random_state**, bật/tắt **Cross-Validation**, số fold.
2. Bảng so sánh **Baseline đếm từ khoá** vs **TF-IDF + LogisticRegression** kèm dòng
   **Chênh lệch**; thêm chỉ số **F1-macro trung bình ± độ lệch chuẩn** của CV.
3. Biểu đồ cột so sánh 4 độ đo + **2 Confusion Matrix** (đề xuất & baseline).
4. **Classification Report** chi tiết từng nhãn cho cả 2 phương pháp.
5. Bảng **đặc trưng ảnh hưởng mạnh nhất** của từng nhãn (giải thích mô hình).
6. **Tải tập Benchmark CSV** (để nộp kèm báo cáo).
7. **Thử dự đoán một bài đăng** – dán văn bản → xem nhãn + xác suất từng nhãn.
8. Mở rộng **Ghi chú phương pháp luận** – dùng trực tiếp khi viết báo cáo.

---

## 🎬 Kịch bản trình bày 7 phút trước giảng viên

| Thời lượng | Thao tác | Điểm nhấn cần nói |
|---|---|---|
| 0:00–0:30 | Mở app, chỉ sidebar | Chạy offline 100%, không cần API key; cam kết không lưu mật khẩu |
| 0:30–1:30 | Tab 1 | 4 thẻ điểm tách bạch Hiện tại / Verified / Potential / Mục tiêu; banner khi thiếu điểm chi tiết |
| 1:30–2:30 | Tab 1 → tải `hcmus_sync.json` đã quét từ extension | Đồng bộ TKB + bảng điểm thật; bảng TKB cập nhật ngay |
| 2:30–4:00 | Tab 2 → dán 1 bài mới (vd “Lễ ra quân Mùa hè xanh”) | Bóc tách 4 nhóm, cờ thiếu, giả định minh bạch, JSON Schema 1 |
| 4:00–5:00 | Tab 3 → lọc “Bài thiếu thông tin” | Ô đỏ trực quan; duyệt chuyển VERIFIED có ghi chú bắt buộc |
| 5:00–6:00 | Tab 4 | Đồ thị NetworkX, loại hoạt động trùng tiết Vật lý đại cương, di chuyển NVC→Linh Trung 45 phút, trần tiêu chí |
| 6:00–7:00 | Tab 6 | Bảng Baseline vs ML + confusion matrix + CV; nêu rõ giới hạn 36 mẫu |

**Câu hỏi giảng viên hay hỏi – trả lời sẵn:**
- *“Sao biết điểm đó đúng?”* → Chỉ `VERIFIED_DRL` mới cộng vào điểm xác minh; AI bị chặn không
  được tự phong VERIFIED; Admin phải ghi chú căn cứ.
- *“Dữ liệu trùng thì sao?”* → MVP cho phép trùng theo chỉ đạo; `content_hash` SHA-256 đã lưu
  sẵn để nâng cấp chống trùng bằng blocking + MinHash ở giai đoạn sau.
- *“Sao không dùng Graph API?”* → Fanpage không cấp quyền; 4 phương thức nạp thay thế hợp lệ.
- *“Vì sao kết quả ML cao?”* → Tập kiểm thử nhỏ & cùng nguồn biên soạn; đã nêu giới hạn và
  kế hoạch mở rộng dữ liệu thật + Cohen's Kappa.

---

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Extension không quét được | Mở đúng trang (Kết quả ĐKHP / Điểm rèn luyện) sau khi đăng nhập; **Reload extension** ở `chrome://extensions`; tải lại trang; nếu vẫn lỗi dùng **Tab 2** dán nội dung |
| Quét ra 0 buổi học | Chrome vẫn giữ bản extension cũ trong bộ nhớ | Bấm **🔄 Reload** trên thẻ extension → tải lại trang portal → quét lại |
| Cột Cơ sở trống | Bảng CTĐB của trường không có cột cơ sở | Chọn **Cơ sở mặc định** trong popup trước khi xuất gói (app không tự bịa) |
| Bảng lộ trình trống | Kiểm tra Tab 3: hoạt động phải có nhãn `POTENTIAL_DRL`/`VERIFIED_DRL` và đủ start/end |
| “Không đọc được file JSON” | Phải là gói Schema 2 do extension xuất ra (`hcmus_sync.json`) |
| Muốn xoá sạch dữ liệu | Xoá file `data/smart_drl_mvp.db` rồi khởi động lại app (DB mới rỗng) |
| Đổi vị trí DB | Đặt biến môi trường `SMART_DRL_DB=/duong/dan/khac.db` |
