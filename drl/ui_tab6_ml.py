"""TAB 6 – Thực nghiệm & Đánh giá Mô hình Học máy (ML Benchmark cho Giảng viên)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config, ml_benchmark, seed_data
from . import ui_common as ui


@st.cache_data(show_spinner=False)
def _run_cached(test_size: float, random_state: int, run_cv: bool, n_splits: int):
    return ml_benchmark.run_benchmark(test_size=test_size, random_state=random_state,
                                      run_cv=run_cv, n_splits=n_splits)


def render() -> None:
    ui.hero(
        "🧪 Thực nghiệm & Đánh giá Mô hình Học máy",
        "Baseline đếm từ khoá vs TF-IDF + LogisticRegression (kèm đặc trưng cấu trúc) trên tập "
        "tập kiểm thử tổng hợp 28 mẫu – kèm Accuracy, Precision, Recall, F1 và Confusion Matrix.",
    )
    ui.warn_box(
        "**Minh bạch học thuật:** tập Benchmark 28 mẫu là dữ liệu TỔNG HỢP do nhóm tự soạn theo văn phong OSA HCMUS, không phải bài đăng thật, và không dùng để tính điểm rèn luyện. "
        "Bộ bóc tách Heuristic ở Tab 2 được phát triển CÙNG tập dữ liệu này – vì vậy báo cáo chỉ so sánh "
        "Baseline ↔ Mô hình ML trên tập test không dùng để huấn luyện. Khi có dữ liệu OSA thật, chỉ cần "
        "thay `BENCHMARK_DATASET` là chạy lại toàn bộ pipeline đánh giá."
    )

    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns(4)
    test_size = ctrl1.slider("Tỉ lệ tập test", 0.2, 0.4, 0.3, 0.05)
    random_state = ctrl2.number_input("random_state", 0, 999, 42, 1)
    run_cv = ctrl3.checkbox("Chạy thêm Cross-Validation", value=True)
    n_splits = ctrl4.number_input("Số fold CV", 2, 5, 3, 1, disabled=not run_cv)

    with st.spinner("Đang huấn luyện và đánh giá…"):
        result = _run_cached(float(test_size), int(random_state), bool(run_cv), int(n_splits))

    st.caption(
        f"Tập dữ liệu: **{len(result.dataset)} mẫu** / {len(result.labels)} nhãn · "
        f"Train **{result.n_train}** · Test **{result.n_test}** · Stratified split."
    )

    st.subheader("📊 Bảng so sánh độ đo")
    comparison = ml_benchmark.comparison_dataframe(result)
    metric_cols = ["Accuracy", "Precision (macro)", "Recall (macro)",
                   "F1-Score (macro)", "F1-Score (weighted)"]

    # Hiển thị số âm/dương bằng dấu mũi tên thay vì tô nền màu (an toàn với mọi theme)
    def _arrow(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value
        if number > 0:
            return f"▲ +{number:.3f}"
        if number < 0:
            return f"▼ {number:.3f}"
        return "＝ 0.000"

    shown = comparison.copy()
    for col in metric_cols:
        if col in shown.columns:
            shown[col] = shown[col].apply(_arrow)
    st.dataframe(shown, width="stretch", hide_index=True)
    st.caption("▲ mô hình đề xuất tốt hơn baseline · ▼ kém hơn · ＝ ngang nhau.")
    if result.cv_scores:
        cv = result.cv_scores
        st.caption(
            f"**Stratified {cv['splits']}-Fold CV (mô hình đề xuất):** F1-macro trung bình "
            f"**{cv['f1_macro_mean']:.3f}** ± {cv['f1_macro_std']:.3f} "
            f"(các fold: {', '.join(f'{s:.3f}' for s in cv['f1_macro_scores'])})"
        )

    st.subheader("📈 Biểu đồ so sánh")
    col1, col2 = st.columns(2)
    with col1:
        st.pyplot(ml_benchmark.plot_metric_bars(result), width="stretch")
    with col2:
        st.pyplot(ml_benchmark.plot_confusion(result, "ml"), width="stretch")

    st.markdown("**Confusion Matrix – Baseline (đếm từ khoá):**")
    base_col, _ = st.columns([1, 1])
    with base_col:
        st.pyplot(ml_benchmark.plot_confusion(result, "baseline"), width="stretch")

    st.divider()
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🧾 Classification Report – Mô hình đề xuất")
        st.code(result.report_ml, language="text")
    with col_r:
        st.subheader("🧾 Classification Report – Baseline")
        st.code(result.report_baseline, language="text")

    if result.top_features:
        st.subheader("🔎 Đặc trưng ảnh hưởng mạnh nhất tới từng nhãn (LogisticRegression)")
        rows = []
        for label, feats in result.top_features.items():
            rows.append({
                "Nhãn": label,
                "Top đặc trưng": ", ".join(f"{name} ({w:+.2f})" for name, w in feats),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.expander("📚 Tập dữ liệu Benchmark (ground truth) 28 mẫu"):
        ds = pd.DataFrame([
            {"STT": i, "Nhãn chuẩn": row["label"], "Bài đăng": row["text"]}
            for i, row in enumerate(seed_data.BENCHMARK_DATASET, start=1)
        ])
        st.dataframe(ds, width="stretch", hide_index=True, height=340)
        ui.download_csv_button(ds, "ml_benchmark_dataset.csv",
                               "⬇️ Tải tập Benchmark (CSV)", "dl_bench")
        st.caption("Phân bố nhãn: " + str(dict(ds['Nhãn chuẩn'].value_counts())))

    st.divider()
    st.subheader("🔮 Thử dự đoán một bài đăng bằng mô hình ML")
    sample_text = st.text_area(
        "Dán nội dung bài đăng cần dự đoán", height=140,
        placeholder="Dán một bài đăng thật (hoặc bài đã lưu ở tab Kho hoạt động) để xem mô "
                    "hình gán nhãn thế nào.",
        key="ml_predict_text",
    )
    if st.button("🎯 Dự đoán nhãn", key="ml_predict_btn", type="primary"):
        pred = ml_benchmark.predict_with_ml(result.ml_model, sample_text)
        if pred.get("label"):
            st.success(f"Mô hình dự đoán: **{pred['label']}** "
                       f"(độ tin cậy {pred['confidence']:.1%})")
            proba_df = pd.DataFrame(
                [{"Nhãn": k, "Xác suất": round(v, 3)} for k, v in
                 sorted(pred["probabilities"].items(), key=lambda kv: -kv[1])])
            st.dataframe(proba_df, width="stretch", hide_index=True)
            st.caption(
                "Đây chỉ là kết quả tham khảo của mô hình; nhãn lưu chính thức vào database vẫn "
                "do pipeline ở Tab 2 quyết định (kèm cờ thiếu dữ liệu và trạng thái xác minh)."
            )
        else:
            st.error(f"Không dự đoán được: {pred.get('error')}")

    with st.expander("🛠️ Ghi chú phương pháp luận (dùng khi báo cáo)"):
        st.markdown(
            """
- **Bài toán:** phân loại 4 nhãn `NOT_RELEVANT / INSUFFICIENT_INFO / EVENT_CANDIDATE / POTENTIAL_DRL`
  theo quy tắc 2 bước của đề tài. `VERIFIED_DRL` **không** nằm trong bài toán ML vì đây là kết luận
  của con người/quy chế, không phải suy luận văn bản.
- **Baseline:** `BaselineKeywordClassifier` – túi từ khoá theo nhãn, trọng số log-odds học từ tập train,
  cộng với xác suất tiên nghiệm. Không dùng ngữ cảnh, không dùng đặc trưng cấu trúc.
- **Mô hình đề xuất:** `FeatureUnion(word TF-IDF 1-2gram, char_wb TF-IDF 3-5gram, 16 đặc trưng
  cấu trúc)` → `LogisticRegression(class_weight='balanced')`.
- **Độ đo:** Accuracy, Precision/Recall/F1 (macro và weighted), Confusion Matrix,
  Stratified K-Fold CV (F1-macro).
- **Giới hạn cần nêu trong báo cáo:** 28 mẫu là quá ít để kết luận tổng quát; dữ liệu tổng hợp do nhóm
  biên soạn nên có thiên lệch văn phong; cần thu thập thêm bài đăng thật từ OSA (có sự đồng ý) và
  gán nhãn bởi 2 người độc lập (đo Cohen's Kappa) để tăng độ tin cậy.
            """
        )
