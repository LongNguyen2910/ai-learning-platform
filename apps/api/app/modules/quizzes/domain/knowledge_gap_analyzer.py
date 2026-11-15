from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from app.modules.quizzes.domain.entities import (
    BloomTaxonomyBreakdown,
    GapSeverity,
    QuizAnalysisResult,
    TopicAnalysisItem,
)
from app.modules.quizzes.domain.review_page_aggregator import ReviewPageAggregator


class KnowledgeGapAnalyzer:
    """Domain service analyzing quiz results, topic knowledge gaps, and Bloom breakdown (FR-21)."""

    @classmethod
    def normalize_bloom_level(cls, raw: str | None) -> str:
        """Normalizes Bloom taxonomy level into remember, understand, or apply."""
        val = (raw or "").strip().lower()
        if "remember" in val:
            return "remember"
        if "understand" in val:
            return "understand"
        if "apply" in val or "analyze" in val or "eval" in val or "create" in val:
            return "apply"
        return "understand"

    @classmethod
    def analyze(
        cls,
        questions_with_results: Sequence[dict[str, Any]],
        default_document_id: str | None = None,
        default_document_title: str = "Tài liệu học tập",
    ) -> QuizAnalysisResult:
        """Analyzes a completed quiz attempt and produces knowledge gaps and review recommendations.

        Args:
            questions_with_results: Sequence of dicts:
                - question_id: str
                - is_correct: bool
                - bloom_level: str
                - topic_tag: str | None
                - target_page: int | None
                - source_document_id: str | None
                - source_document_title: str | None
            default_document_id: Quiz-level document ID.
            default_document_title: Quiz-level document title.

        Returns:
            QuizAnalysisResult with topic categorization, Bloom breakdown, and page targets.
        """
        if not questions_with_results:
            empty_breakdown = BloomTaxonomyBreakdown()
            return QuizAnalysisResult(
                score=0.0,
                total_questions=0,
                total_correct=0,
                total_incorrect=0,
                weak_topics=[],
                mastered_topics=[],
                review_recommendations=[],
                bloom_summary=empty_breakdown,
            )

        total_q = len(questions_with_results)
        total_correct = 0

        # Topic aggregation: topic_tag -> dict of stats
        topic_buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total": 0,
                "correct": 0,
                "incorrect": 0,
                "rem_total": 0,
                "rem_correct": 0,
                "und_total": 0,
                "und_correct": 0,
                "app_total": 0,
                "app_correct": 0,
                "incorrect_question_ids": [],
            }
        )

        # Global Bloom counters
        g_rem_tot = g_rem_cor = 0
        g_und_tot = g_und_cor = 0
        g_app_tot = g_app_cor = 0

        for item in questions_with_results:
            is_correct = bool(item.get("is_correct"))
            if is_correct:
                total_correct += 1

            raw_topic = item.get("topic_tag")
            topic_name = raw_topic.strip() if isinstance(raw_topic, str) and raw_topic.strip() else "Chủ đề chung"
            bloom_cat = cls.normalize_bloom_level(item.get("bloom_level"))
            q_id = str(item.get("question_id", ""))

            bucket = topic_buckets[topic_name]
            bucket["total"] += 1

            if is_correct:
                bucket["correct"] += 1
            else:
                bucket["incorrect"] += 1
                if q_id:
                    bucket["incorrect_question_ids"].append(q_id)

            if bloom_cat == "remember":
                g_rem_tot += 1
                bucket["rem_total"] += 1
                if is_correct:
                    g_rem_cor += 1
                    bucket["rem_correct"] += 1
            elif bloom_cat == "understand":
                g_und_tot += 1
                bucket["und_total"] += 1
                if is_correct:
                    g_und_cor += 1
                    bucket["und_correct"] += 1
            else:  # apply / analyze
                g_app_tot += 1
                bucket["app_total"] += 1
                if is_correct:
                    g_app_cor += 1
                    bucket["app_correct"] += 1

        total_incorrect = total_q - total_correct
        score = round((total_correct / total_q) * 100.0, 2) if total_q > 0 else 0.0

        weak_topics: list[TopicAnalysisItem] = []
        mastered_topics: list[TopicAnalysisItem] = []

        for topic_name, data in sorted(topic_buckets.items(), key=lambda x: x[0]):
            bloom_matrix = BloomTaxonomyBreakdown(
                remember_correct=data["rem_correct"],
                remember_total=data["rem_total"],
                understand_correct=data["und_correct"],
                understand_total=data["und_total"],
                apply_correct=data["app_correct"],
                apply_total=data["app_total"],
            )

            is_gap = data["incorrect"] > 0
            severity: GapSeverity | None = None

            if is_gap:
                rem_und_incorrect = (data["rem_total"] - data["rem_correct"]) + (
                    data["und_total"] - data["und_correct"]
                )
                if rem_und_incorrect > 0:
                    severity = GapSeverity.CRITICAL_FOUNDATION
                else:
                    severity = GapSeverity.APPLICATION_PRACTICE

                weak_topics.append(
                    TopicAnalysisItem(
                        topic_tag=topic_name,
                        is_gap=True,
                        severity=severity,
                        total_questions=data["total"],
                        correct_questions=data["correct"],
                        incorrect_questions=data["incorrect"],
                        bloom_matrix=bloom_matrix,
                        incorrect_question_ids=data["incorrect_question_ids"],
                    )
                )
            else:
                mastered_topics.append(
                    TopicAnalysisItem(
                        topic_tag=topic_name,
                        is_gap=False,
                        severity=None,
                        total_questions=data["total"],
                        correct_questions=data["correct"],
                        incorrect_questions=0,
                        bloom_matrix=bloom_matrix,
                        incorrect_question_ids=[],
                    )
                )

        review_recs = ReviewPageAggregator.aggregate(
            questions_with_results=questions_with_results,
            default_document_id=default_document_id,
            default_document_title=default_document_title,
        )

        bloom_summary = BloomTaxonomyBreakdown(
            remember_correct=g_rem_cor,
            remember_total=g_rem_tot,
            understand_correct=g_und_cor,
            understand_total=g_und_tot,
            apply_correct=g_app_cor,
            apply_total=g_app_tot,
        )

        return QuizAnalysisResult(
            score=score,
            total_questions=total_q,
            total_correct=total_correct,
            total_incorrect=total_incorrect,
            weak_topics=weak_topics,
            mastered_topics=mastered_topics,
            review_recommendations=review_recs,
            bloom_summary=bloom_summary,
        )
