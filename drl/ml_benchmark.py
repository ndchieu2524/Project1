"""Module Học máy & Đánh giá (theo yêu cầu của Giảng viên).

Hai phương pháp được so sánh trên CÙNG một tập dữ liệu chuẩn (ground truth):

1. **Baseline – Keyword/Rule đơn giản** (``BaselineKeywordClassifier``):
   Đếm từ khoá theo từng nhãn (không học trọng số), dự đoán nhãn có điểm
   từ khoá cao nhất. Đây là cách "đếm từ khoá" mà bất kỳ nhóm nào cũng có thể
   viết trong 30 phút – dùng làm mốc so sánh.

2. **Mô hình đề xuất – TF-IDF + Logistic Regression** (``build_ml_pipeline``):
   Kết hợp đặc trưng văn bản TF-IDF (word 1-2 gram + char 3-5 gram chịu lỗi gõ
   không dấu) với ĐẶC TRƯNG CẤU TRÚC bài đăng (có ngày/giờ?, có địa điểm?, có
   câu nêu điểm ĐRL?, độ dài, số dòng…) thông qua ``FeatureUnion``.

Quy trình đánh giá chuẩn:
- Chia stratified train/test (mặc định 70/30, random_state cố định = 42).
- Báo cáo Accuracy, Precision/Recall/F1 (macro & weighted), Confusion Matrix.
- Bổ sung đánh giá bằng Stratified K-Fold Cross-Validation (tuỳ chọn) để giảm
  phụ thuộc vào một lần chia dữ liệu.
- Xuất bảng so sánh + biểu đồ (``matplotlib``) để đưa vào báo cáo.

LƯU Ý TRUNG THỰC KHOA HỌC (được ghi rõ trên giao diện Tab 6):
- Tập Benchmark 28 mẫu là dữ liệu [DEMO] mô phỏng văn phong OSA HCMUS.
- Bộ bóc tách Heuristic trong ``nlp_engine`` được phát triển CÙNG tập dữ liệu
  này, nên con số của nó mang tính "luật đã tinh chỉnh" chứ không phải khả năng
  tổng quát hoá. Vì vậy báo cáo chỉ so sánh Baseline ↔ ML trên tập test hoàn
  toàn không dùng để huấn luyện, và nêu rõ giới hạn khi mở rộng dữ liệu thật.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import numpy as np

from . import config, nlp_engine

LABELS = [
    config.LABEL_NOT_RELEVANT,
    config.LABEL_INSUFFICIENT,
    config.LABEL_EVENT_CANDIDATE,
    config.LABEL_POTENTIAL,
]

# ---------------------------------------------------------------------------
# 1. Baseline: phân loại bằng đếm từ khoá đơn giản
# ---------------------------------------------------------------------------
BASELINE_KEYWORDS: dict[str, list[str]] = {
    config.LABEL_NOT_RELEVANT: [
        "chuc mung", "tuyen dung", "thuc tap sinh", "viec lam", "uu dai",
        "giam gia", "khuyen mai", "hoc phi", "cong no", "lich nghi", "nghi le",
        "quang cao", "ban hang", "nha tai tro", "dat giai", "thanh tich",
        "chuc mung nam moi", "sinh nhat",
    ],
    config.LABEL_INSUFFICIENT: [
        "se thong bao sau", "thong bao sau", "cap nhat sau", "chua co lich",
        "du kien", "se cong bo", "chua xac dinh", "dang cap nhat", "chua ro",
    ],
    config.LABEL_EVENT_CANDIDATE: [
        "hoi thao", "workshop", "seminar", "toa dam", "cuoc thi", "talkshow",
        "tham quan", "ngay hoi", "tap huan", "giao luu", "clb", "cau lac bo",
        "giai bong", "dem nhac", "tham gia", "dang ky",
    ],
    config.LABEL_POTENTIAL: [
        "diem ren luyen", "diem rl", "drl", "cong 5 diem", "cong 4 diem",
        "cong 3 diem", "cong 10 diem", "diem ren luyen", "cong diem",
        "diem ren luyen", "drl",
    ],
}


class BaselineKeywordClassifier:
    """Baseline có học: đếm từ khoá trên tập train để chọn trọng số ±1.

    Mỗi từ khoá nhận trọng số = log-odds thô (P(kw|label) / P(kw|khác)) từ tập
    TRAIN, sau đó điểm của mỗi nhãn = tổng trọng số các từ khoá xuất hiện.
    Đây vẫn là phương pháp "túi từ khoá" – không học ngữ cảnh, không dùng
    thứ tự từ, không kết hợp đặc trưng cấu trúc.
    """

    def __init__(self):
        self.weights_: dict[str, dict[str, float]] = {}
        self.prior_: dict[str, float] = {}
        self.classes_: list[str] = []

    def fit(self, texts: list[str], labels: list[str]):
        self.classes_ = sorted(set(labels))
        n = len(texts)
        norms = [nlp_engine.strip_accents(t) for t in texts]
        # Xác suất tiên nghiệm của từng nhãn
        for label in self.classes_:
            self.prior_[label] = (labels.count(label) + 1) / (n + len(self.classes_))
        # log-odds của từ khoá
        for label in self.classes_:
            weights: dict[str, float] = {}
            for kw in BASELINE_KEYWORDS.get(label, []):
                kw_norm = nlp_engine.strip_accents(kw)
                n_kw_pos = sum(1 for t, y in zip(norms, labels) if y == label and kw_norm in t)
                n_kw_neg = sum(1 for t, y in zip(norms, labels) if y != label and kw_norm in t)
                if n_kw_pos == 0 and n_kw_neg == 0:
                    continue
                weights[kw_norm] = float(np.log((n_kw_pos + 0.5) / (n_kw_neg + 0.5)))
            self.weights_[label] = weights
        return self

    def predict(self, texts: list[str]) -> list[str]:
        preds = []
        for text in texts:
            norm = nlp_engine.strip_accents(text)
            scores = {}
            for label in self.classes_:
                score = np.log(self.prior_.get(label, 1 / len(self.classes_)))
                for kw, w in self.weights_.get(label, {}).items():
                    if kw in norm:
                        score += w
                scores[label] = score
            best = max(scores.items(), key=lambda kv: kv[1])[0]
            preds.append(best)
        return preds

    def predict_one(self, text: str) -> str:
        return self.predict([text])[0]


# ---------------------------------------------------------------------------
# 2. Mô hình đề xuất: TF-IDF + đặc trưng cấu trúc + LogisticRegression
# ---------------------------------------------------------------------------
STRUCTURAL_FEATURES = [
    "has_date",
    "has_time",
    "has_deadline_kw",
    "has_location",
    "has_score_mention",
    "has_registration",
    "has_negative_kw",
    "has_activity_kw",
    "has_drl_mention",
    "has_range_time",
    "n_chars_log",
    "n_lines_log",
    "n_digits",
    "has_organizer",
    "has_online",
    "has_campus",
]

_DATE_FEATURE_RE = re.compile(r"\d{1,2}\s*[/.]\s*\d{1,2}")
_TIME_FEATURE_RE = re.compile(r"\d{1,2}\s*[h:]\s*\d{0,2}")
_RANGE_RE = re.compile(r"\d{1,2}\s*[h:]\s*\d{2}\s*[-–]\s*\d{1,2}\s*[h:]")


def structural_features(texts: Iterable[str]) -> np.ndarray:  # type: ignore[valid-type]
    """Vector đặc trưng cấu trúc (dense) cho mỗi bài đăng."""
    rows = []
    for text in texts:
        norm = nlp_engine.strip_accents(text or "")
        n_chars = max(1, len(norm))
        rows.append([
            1.0 if _DATE_FEATURE_RE.search(norm) else 0.0,
            1.0 if _TIME_FEATURE_RE.search(norm) else 0.0,
            1.0 if re.search(r"han (chot|cuoi|dang ky|nop)|truoc ngay|deadline", norm) else 0.0,
            1.0 if re.search(r"dia diem|hoi truong|phong|co so|san |linh trung|nguyen van cu|online", norm) else 0.0,
            1.0 if re.search(r"(cong|duoc cong|nhan duoc|huong)\s*\+?\s*\d{1,2}\s*(diem|d)\b|\+\s*\d{1,2}\s*diem", norm) else 0.0,
            1.0 if re.search(r"dang ky|dang ki|form|link dang ky", norm) else 0.0,
            1.0 if any(k in norm for k in ("chuc mung", "tuyen dung", "giam gia", "khuyen mai", "hoc phi", "lich nghi")) else 0.0,
            1.0 if any(k in norm for k in ("hoat dong", "chuong trinh", "cuoc thi", "hoi thao", "workshop", "tham gia")) else 0.0,
            1.0 if re.search(r"diem ren luyen|diem rl|drl|ren luyen", norm) else 0.0,
            1.0 if _RANGE_RE.search(norm) else 0.0,
            float(np.log1p(n_chars)),
            float(np.log1p(len([l for l in (text or '').splitlines() if l.strip()]))),
            sum(ch.isdigit() for ch in norm) / 10.0,
            1.0 if re.search(r"doan khoa|doan truong|trung tam|ban to chuc|phong cong tac|clb", norm) else 0.0,
            1.0 if re.search(r"\bonline\b|truc tuyen|zoom|google meet", norm) else 0.0,
            1.0 if re.search(r"linh trung|nguyen van cu", norm) else 0.0,
        ])
    return np.asarray(rows, dtype=float)


def build_ml_pipeline(random_state: int = 42):
    """Pipeline: TF-IDF (word + char) ∪ đặc trưng cấu trúc → LogisticRegression."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import FeatureUnion, Pipeline
    from sklearn.preprocessing import FunctionTransformer

    word_tfidf = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        lowercase=True,
        strip_accents=None,   # dùng đặc trưng char_wb bên dưới cho tiếng Việt
    )
    char_tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=1,
        sublinear_tf=True,
        lowercase=True,
    )
    union = FeatureUnion([
        ("word_tfidf", word_tfidf),
        ("char_tfidf", char_tfidf),
        ("structural", FunctionTransformer(structural_features, validate=False)),
    ])
    clf = LogisticRegression(
        max_iter=2000,
        C=4.0,
        class_weight="balanced",
        random_state=random_state,
    )
    return Pipeline([("features", union), ("clf", clf)])


def build_ml_pipeline_with_split(random_state: int = 42):
    """Trả về (pipeline, chiến lược eval) – giữ API rõ ràng cho UI/test."""
    return build_ml_pipeline(random_state), "stratified_holdout"


# ---------------------------------------------------------------------------
# 3. Đánh giá
# ---------------------------------------------------------------------------
@dataclass
class BenchmarkResult:
    labels: list[str]
    y_test: list[str]
    ml_pred: list[str]
    baseline_pred: list[str]
    metrics_ml: dict
    metrics_baseline: dict
    report_ml: str
    report_baseline: str
    confusion_ml: np.ndarray
    confusion_baseline: np.ndarray
    n_train: int
    n_test: int
    cv_scores: Optional[dict] = None
    top_features: dict = field(default_factory=dict)
    ml_model: Any = None
    baseline_model: Any = None
    dataset: list[dict] = field(default_factory=list)


def _metrics(y_true, y_pred) -> dict:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "precision_weighted": float(precision_score(y_true, y_pred, average="weighted", zero_division=0)),
        "recall_weighted": float(recall_score(y_true, y_pred, average="weighted", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


def _feature_names(model) -> np.ndarray:
    """Tên đặc trưng của FeatureUnion (ghép thủ công vì FunctionTransformer
    không có get_feature_names_out khi đầu vào là numpy array)."""
    union = model.named_steps["features"]
    parts: list[str] = []
    for name, transformer in union.transformer_list:
        if name == "structural":
            parts.extend([f"struct:{f}" for f in STRUCTURAL_FEATURES])
        else:
            parts.extend([f"{name}:{f}" for f in transformer.get_feature_names_out()])
    return np.asarray(parts, dtype=object)


def _top_features(model, labels: list[str], k: int = 6) -> dict:
    """Lấy các token có trọng số dương cao nhất của LogisticRegression."""
    try:
        names = _feature_names(model)
        coef = model.named_steps["clf"].coef_
        classes = list(model.named_steps["clf"].classes_)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[tuple[str, float]]] = {}
    for idx, cls in enumerate(classes):
        row = coef[idx] if coef.shape[0] > 1 else coef[0]
        order = np.argsort(row)[::-1][:k]
        out[cls] = [(str(names[i]), float(row[i])) for i in order]
    return out


def run_benchmark(dataset: Optional[list[dict]] = None, test_size: float = 0.3,
                  random_state: int = 42, run_cv: bool = False,
                  n_splits: int = 3) -> BenchmarkResult:
    """Chạy so sánh Baseline vs ML trên tập dữ liệu (mặc định: Benchmark [DEMO])."""
    from sklearn.metrics import confusion_matrix
    from sklearn.metrics import classification_report
    from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

    from .seed_data import BENCHMARK_DATASET

    data = dataset or BENCHMARK_DATASET
    texts = [row["text"] for row in data]
    labels = [row["label"] for row in data]
    present = sorted(set(labels))

    # Số mẫu mỗi lớp nhỏ → đảm bảo test set giữ được lớp
    min_class_count = min(labels.count(lbl) for lbl in present)
    if min_class_count * test_size < 1:
        test_size = max(0.3, (1.0 / min_class_count) + 0.01)
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=test_size, random_state=random_state,
        stratify=labels if min_class_count >= 2 else None,
    )

    ml_model = build_ml_pipeline(random_state).fit(X_train, y_train)
    baseline_model = BaselineKeywordClassifier().fit(X_train, y_train)
    ml_pred = list(ml_model.predict(X_test))
    baseline_pred = baseline_model.predict(X_test)

    labels_ordered = [lbl for lbl in LABELS if lbl in present]
    conf_ml = confusion_matrix(y_test, ml_pred, labels=labels_ordered)
    conf_base = confusion_matrix(y_test, baseline_pred, labels=labels_ordered)

    cv_scores = None
    if run_cv:
        n_splits_eff = min(n_splits, min_class_count)
        if n_splits_eff >= 2:
            skf = StratifiedKFold(n_splits=n_splits_eff, shuffle=True, random_state=random_state)
            scores = cross_val_score(build_ml_pipeline(random_state), texts, labels,
                                     cv=skf, scoring="f1_macro")
            cv_scores = {
                "splits": n_splits_eff,
                "f1_macro_scores": [float(s) for s in scores],
                "f1_macro_mean": float(scores.mean()),
                "f1_macro_std": float(scores.std()),
            }

    return BenchmarkResult(
        labels=labels_ordered,
        y_test=list(y_test),
        ml_pred=ml_pred,
        baseline_pred=baseline_pred,
        metrics_ml=_metrics(y_test, ml_pred),
        metrics_baseline=_metrics(y_test, baseline_pred),
        report_ml=classification_report(y_test, ml_pred, zero_division=0, digits=3),
        report_baseline=classification_report(y_test, baseline_pred, zero_division=0, digits=3),
        confusion_ml=conf_ml,
        confusion_baseline=conf_base,
        n_train=len(X_train),
        n_test=len(X_test),
        cv_scores=cv_scores,
        top_features=_top_features(ml_model, labels_ordered),
        ml_model=ml_model,
        baseline_model=baseline_model,
        dataset=data,
    )


def comparison_dataframe(result: BenchmarkResult):
    """Bảng so sánh gọn để hiển thị trên Streamlit."""
    import pandas as pd

    rows = []
    for name, metrics in [
        ("Baseline – Đếm từ khoá", result.metrics_baseline),
        ("Đề xuất – TF-IDF + LogisticRegression", result.metrics_ml),
    ]:
        rows.append({
            "Mô hình": name,
            "Accuracy": round(metrics["accuracy"], 3),
            "Precision (macro)": round(metrics["precision_macro"], 3),
            "Recall (macro)": round(metrics["recall_macro"], 3),
            "F1-Score (macro)": round(metrics["f1_macro"], 3),
            "F1-Score (weighted)": round(metrics["f1_weighted"], 3),
        })
    df = pd.DataFrame(rows)
    delta = df.iloc[1, 1:].astype(float) - df.iloc[0, 1:].astype(float)
    df.loc[len(df)] = ["Chênh lệch (ML − Baseline)"] + [round(float(v), 3) for v in delta]
    return df


def plot_confusion(result: BenchmarkResult, which: str = "ml"):
    """Vẽ Confusion Matrix bằng matplotlib, trả về Figure."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matrix = result.confusion_ml if which == "ml" else result.confusion_baseline
    title = ("Confusion Matrix – Mô hình đề xuất (TF-IDF + LogisticRegression)"
             if which == "ml" else "Confusion Matrix – Baseline (Đếm từ khoá)")
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    im = ax.imshow(matrix, cmap="Blues")
    ax.set_xticks(range(len(result.labels)))
    ax.set_yticks(range(len(result.labels)))
    short = [lbl.replace("_", "\n") for lbl in result.labels]
    ax.set_xticklabels(short, fontsize=8)
    ax.set_yticklabels(short, fontsize=8)
    ax.set_xlabel("Nhãn dự đoán", fontsize=9)
    ax.set_ylabel("Nhãn thực tế (ground truth)", fontsize=9)
    ax.set_title(title, fontsize=10)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() / 2 else "black", fontsize=11)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return fig


def plot_metric_bars(result: BenchmarkResult):
    """Biểu đồ cột so sánh Accuracy / Precision / Recall / F1 giữa 2 phương pháp."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    metric_keys = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]
    metric_names = ["Accuracy", "Precision", "Recall", "F1-Score"]
    base_vals = [result.metrics_baseline[k] for k in metric_keys]
    ml_vals = [result.metrics_ml[k] for k in metric_keys]
    x = np.arange(len(metric_names))
    width = 0.36
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    bars1 = ax.bar(x - width / 2, base_vals, width, label="Baseline (Keyword)", color="#94a3b8")
    bars2 = ax.bar(x + width / 2, ml_vals, width, label="Đề xuất (TF-IDF + LR)", color="#2563eb")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_names)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Điểm số (0–1)")
    ax.set_title("So sánh hiệu năng: Baseline vs Mô hình Học máy", fontsize=11)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    for bars in (bars1, bars2):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f"{height:.2f}", xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 2), textcoords="offset points", ha="center", fontsize=7.5)
    fig.tight_layout()
    return fig


def predict_with_ml(model, text: str) -> dict:
    """Dự đoán nhãn cho 1 bài đăng bằng mô hình đã huấn luyện (tư vấn, không thay thế luật)."""
    try:
        proba = model.predict_proba([text])[0]
        classes = list(model.named_steps["clf"].classes_)
        best_idx = int(np.argmax(proba))
        return {
            "label": classes[best_idx],
            "confidence": float(proba[best_idx]),
            "probabilities": {cls: float(p) for cls, p in zip(classes, proba)},
        }
    except Exception as exc:  # noqa: BLE001
        return {"label": None, "confidence": 0.0, "error": str(exc), "probabilities": {}}
