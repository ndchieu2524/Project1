"""Smart DRL Assistant – HCMUS (MVP).

Gói lõi của ứng dụng Streamlit gồm các module:
    config      – hằng số cấu hình & nhãn nghiệp vụ
    database    – khởi tạo / thao tác SQLite (smart_drl_mvp.db)
    seed_data   – khung tiêu chí theo quy chế + tập kiểm thử ML (không tự nạp)
    nlp_engine  – bộ bóc tách Regex/Heuristic nội bộ (luôn chạy offline)
    ai_engine   – gọi Gemini/OpenAI (Structured JSON) + fallback nội bộ
    ml_benchmark– TF-IDF + Classifier vs. Baseline từ khoá (Scikit-learn)
    pathway     – đồ thị NetworkX tối ưu lộ trình hoạt động
    crawler     – thu thập TỰ ĐỘNG từ cổng công khai HCMUS (API + HTML)
    ui_*        – 7 tab giao diện Streamlit
"""

__version__ = "2.7.0-PREDICTED-PROGRESS"
__app_name__ = "Smart DRL Assistant HCMUS"
