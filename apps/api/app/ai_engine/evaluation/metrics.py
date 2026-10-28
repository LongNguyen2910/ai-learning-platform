"""Ragas Metric initializers for RAG Triad using Gemini as Judge."""

from __future__ import annotations

import warnings

# Suppress Ragas v1.0 deprecation warnings during metric imports
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    from ragas.metrics import (
        AnswerRelevancy,
        Faithfulness,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.metrics.base import Metric

from app.ai_engine.evaluation.adapters import GeminiRagasEmbeddings, GeminiRagasLLM


def get_ragas_metrics(
    llm: GeminiRagasLLM | None = None,
    embeddings: GeminiRagasEmbeddings | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
) -> dict[str, Metric]:
    """Builds and returns the standard dictionary of Ragas metrics configured for Gemini.

    Returns:
        dict with keys: 'faithfulness', 'answer_relevancy', 'context_precision', 'context_recall'
    """
    eval_llm = llm or GeminiRagasLLM(api_key=api_key, model_name=model_name)
    eval_embeddings = embeddings or GeminiRagasEmbeddings(api_key=api_key)

    return {
        "faithfulness": Faithfulness(llm=eval_llm),
        "answer_relevancy": AnswerRelevancy(
            llm=eval_llm, embeddings=eval_embeddings, strictness=1
        ),
        "context_precision": LLMContextPrecisionWithReference(llm=eval_llm),
        "context_recall": LLMContextRecall(llm=eval_llm),
    }
