"""Pytest Quality Gate for RAG pipeline evaluation."""

import json
from pathlib import Path
import pytest

from app.ai_engine.evaluation.adapters import GeminiRagasEmbeddings, GeminiRagasLLM
from app.ai_engine.evaluation.runner import RAGEvaluationRunner
from app.core.config import settings

EVAL_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"


@pytest.mark.asyncio
async def test_rag_quality_gate():
    """Asserts that the RAG pipeline achieves the minimum acceptable quality thresholds."""
    if not settings.GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured. Skipping RAG benchmark quality gate.")

    dataset_path = EVAL_DATA_DIR / "golden_dataset.json"
    assert dataset_path.exists(), f"Golden dataset missing at {dataset_path}"

    with open(dataset_path, encoding="utf-8") as f:
        dataset = json.load(f)

    assert len(dataset) >= 3, "Golden dataset must contain at least 3 samples."

    llm = GeminiRagasLLM(model_name=settings.GEMINI_MODEL or "gemini-3.5-flash-lite")
    embeddings = GeminiRagasEmbeddings()
    runner = RAGEvaluationRunner(llm=llm, embeddings=embeddings)

    report = await runner.run(dataset=dataset, title="CI RAG Quality Gate")

    # Verify each threshold
    for metric_name, thresh in report.thresholds.items():
        actual_score = report.average_scores.get(metric_name, 0.0)
        assert actual_score >= thresh, (
            f"RAG Quality Gate Failed for '{metric_name}': "
            f"Achieved {actual_score:.4f}, required >= {thresh:.2f}."
        )

    assert report.passed is True, "Overall RAG Quality Gate report status must be PASSED."
