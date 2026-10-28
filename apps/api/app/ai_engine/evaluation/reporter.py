"""Reporter module for generating Markdown and JSON RAG evaluation reports."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from pydantic import BaseModel, Field


class EvaluationSampleResult(BaseModel):
    user_input: str
    response: str
    reference: str
    retrieved_contexts: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    title: str = "RAG Pipeline Benchmark Report"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    model_name: str
    sample_count: int
    average_scores: dict[str, float]
    thresholds: dict[str, float]
    passed: bool
    samples: list[EvaluationSampleResult] = Field(default_factory=list)


def generate_markdown_report(report: EvaluationReport) -> str:
    """Generates a clean, readable Markdown report from evaluation results."""
    status_badge = "✅ **PASSED (Quality Gate Met)**" if report.passed else "❌ **FAILED (Below Threshold)**"

    lines = [
        f"# {report.title}",
        "",
        f"- **Thời gian chạy:** `{report.timestamp}`",
        f"- **Mô hình Giám khảo (Judge LLM):** `{report.model_name}`",
        f"- **Số lượng mẫu kiểm thử:** `{report.sample_count}`",
        f"- **Trạng thái Quality Gate:** {status_badge}",
        "",
        "## 1. Bảng Điểm Trung Bình & Ngưỡng Chất Lượng",
        "",
        "| Chỉ Số Đánh Giá (Metric) | Điểm Đạt Được | Ngưỡng Tối Thiểu (Threshold) | Trạng Thái |",
        "| :--- | :---: | :---: | :---: |",
    ]

    metric_labels = {
        "faithfulness": "Faithfulness (Chống ảo giác)",
        "answer_relevancy": "Answer Relevancy (Đúng trọng tâm)",
        "context_precision": "Context Precision (Độ chuẩn xác tìm kiếm)",
        "context_recall": "Context Recall (Độ đầy đủ ngữ cảnh)",
    }

    for metric_key, label in metric_labels.items():
        score = report.average_scores.get(metric_key, 0.0)
        threshold = report.thresholds.get(metric_key, 0.0)
        passed = score >= threshold
        status = "✅ Đạt" if passed else "❌ Không đạt"
        lines.append(f"| {label} | `{score:.4f}` | `{threshold:.2f}` | {status} |")

    lines.extend([
        "",
        "## 2. Chi Tiết Các Mẫu Cần Cải Thiện (Worst Performing Samples)",
        "",
    ])

    # Find bottom samples sorted by average score across metrics
    def avg_score(s: EvaluationSampleResult) -> float:
        valid_scores = [v for v in s.scores.values() if v is not None and not (isinstance(v, float) and v != v)]
        return sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

    worst_samples = sorted(report.samples, key=avg_score)[:5]

    for idx, sample in enumerate(worst_samples, start=1):
        lines.append(f"### {idx}. Câu hỏi: {sample.user_input}")
        lines.append(f"- **Điểm số:** " + ", ".join([f"`{k}: {v:.2f}`" for k, v in sample.scores.items()]))
        lines.append(f"- **Đáp án chuẩn (Reference):** {sample.reference}")
        lines.append(f"- **Câu trả lời sinh ra (Response):** {sample.response}")
        lines.append("- **Đoạn trích tìm được (Retrieved Contexts):**")
        if sample.retrieved_contexts:
            for c_idx, ctx in enumerate(sample.retrieved_contexts[:3], 1):
                clean_ctx = ctx.replace("\n", " ").strip()
                lines.append(f"  {c_idx}. *{clean_ctx[:200]}...*")
        else:
            lines.append("  *(Không tìm thấy ngữ cảnh nào)*")
        lines.append("")

    return "\n".join(lines)


def save_report(report: EvaluationReport, output_dir: Path, base_name: str | None = None) -> tuple[Path, Path]:
    """Saves report as Markdown and JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = base_name or f"eval_report_{stamp}"

    md_path = output_dir / f"{name}.md"
    json_path = output_dir / f"{name}.json"

    md_content = generate_markdown_report(report)
    md_path.write_text(md_content, encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return md_path, json_path
