"""RAG Evaluation module for AI Learning Platform."""

from app.ai_engine.evaluation.adapters import GeminiRagasEmbeddings, GeminiRagasLLM
from app.ai_engine.evaluation.metrics import get_ragas_metrics
from app.ai_engine.evaluation.reporter import EvaluationReport, generate_markdown_report
from app.ai_engine.evaluation.runner import RAGEvaluationRunner

__all__ = [
    "GeminiRagasLLM",
    "GeminiRagasEmbeddings",
    "get_ragas_metrics",
    "EvaluationReport",
    "generate_markdown_report",
    "RAGEvaluationRunner",
]
