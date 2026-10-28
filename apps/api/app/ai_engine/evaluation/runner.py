"""RAG Evaluation Runner orchestrating data retrieval, generation, and Ragas scoring."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.ai_engine.evaluation.adapters import GeminiRagasEmbeddings, GeminiRagasLLM
from app.ai_engine.evaluation.metrics import get_ragas_metrics
from app.ai_engine.evaluation.reporter import EvaluationReport, EvaluationSampleResult
from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.75,
    "context_recall": 0.75,
}


class RAGEvaluationRunner:
    """Runner orchestrating evaluation runs with rate limit control, checkpointing, and metric scoring."""

    def __init__(
        self,
        llm: GeminiRagasLLM | None = None,
        embeddings: GeminiRagasEmbeddings | None = None,
        thresholds: dict[str, float] | None = None,
        max_concurrency: int = 2,
        cache_path: Path | None = None,
    ) -> None:
        self.llm = llm or GeminiRagasLLM()
        self.embeddings = embeddings or GeminiRagasEmbeddings()
        self.thresholds = thresholds or DEFAULT_THRESHOLDS.copy()
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.cache_path = cache_path or (settings.PROJECT_ROOT / "apps" / "api" / "data" / "evaluation" / ".eval_cache.json")
        self.metrics = get_ragas_metrics(llm=self.llm, embeddings=self.embeddings)
        self.genai_client = genai.Client(api_key=self.llm.api_key)

    def _load_cache(self) -> dict[str, dict[str, float]]:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Could not read eval cache: %s", exc)
        return {}

    def _save_cache(self, cache: dict[str, dict[str, float]]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)
        except Exception as exc:
            logger.warning("Could not write eval cache: %s", exc)

    async def _evaluate_single_sample(
        self,
        item: dict[str, Any],
        cache: dict[str, dict[str, float]],
    ) -> EvaluationSampleResult:
        user_input = item.get("user_input", "")
        reference = item.get("reference", "")
        retrieved_contexts = item.get("retrieved_contexts", [])
        response = item.get("response", "")

        # Safe fallback for empty contexts
        if not retrieved_contexts:
            retrieved_contexts = [""]

        # If response is missing, generate using Gemini directly
        if not response:
            prompt = (
                f"You are a helpful tutor. Based on the following contexts, answer the question accurately:\n\n"
                f"Contexts:\n" + "\n---\n".join(retrieved_contexts) + "\n\n"
                f"Question: {user_input}\nAnswer:"
            )
            res = await self.genai_client.aio.models.generate_content(
                model=self.llm.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0),
            )
            response = res.text or ""

        cache_key = f"{user_input}___{response[:60]}"
        if cache_key in cache:
            logger.info("Using cached evaluation scores for: %s", user_input[:40])
            scores = cache[cache_key]
        else:
            async with self.semaphore:
                row = {
                    "user_input": user_input,
                    "response": response,
                    "retrieved_contexts": retrieved_contexts,
                    "reference": reference,
                }
                scores: dict[str, float] = {}
                for m_name, metric in self.metrics.items():
                    try:
                        raw_score = await metric._ascore(row, callbacks=None)
                        if isinstance(raw_score, (float, int)) and not (isinstance(raw_score, float) and raw_score != raw_score):
                            scores[m_name] = float(raw_score)
                        else:
                            scores[m_name] = 0.0
                    except Exception as err:
                        logger.error("Error evaluating %s on query '%s': %s", m_name, user_input, err)
                        scores[m_name] = 0.0

                cache[cache_key] = scores
                self._save_cache(cache)

        return EvaluationSampleResult(
            user_input=user_input,
            response=response,
            reference=reference,
            retrieved_contexts=retrieved_contexts,
            scores=scores,
        )

    async def run(
        self,
        dataset: list[dict[str, Any]],
        title: str = "RAG Pipeline Benchmark",
    ) -> EvaluationReport:
        """Executes evaluation across all samples in dataset."""
        cache = self._load_cache()
        sample_results: list[EvaluationSampleResult] = []

        for item in dataset:
            res = await self._evaluate_single_sample(item, cache)
            sample_results.append(res)

        # Compute averages
        metric_sums: dict[str, float] = {k: 0.0 for k in self.metrics}
        sample_count = len(sample_results)

        for res in sample_results:
            for m_name in self.metrics:
                metric_sums[m_name] += res.scores.get(m_name, 0.0)

        average_scores = {
            m_name: (metric_sums[m_name] / sample_count) if sample_count > 0 else 0.0
            for m_name in self.metrics
        }

        # Check threshold passing
        passed = all(
            average_scores.get(m_name, 0.0) >= self.thresholds.get(m_name, 0.0)
            for m_name in self.thresholds
        )

        return EvaluationReport(
            title=title,
            model_name=self.llm.model_name,
            sample_count=sample_count,
            average_scores=average_scores,
            thresholds=self.thresholds,
            passed=passed,
            samples=sample_results,
        )
