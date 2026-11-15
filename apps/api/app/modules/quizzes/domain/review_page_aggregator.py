from collections.abc import Sequence
from typing import Any

from app.modules.quizzes.domain.entities import DocumentReviewRecommendation


class ReviewPageAggregator:
    """Aggregates and deduplicates review page recommendations grouped by document (FR-21)."""

    @staticmethod
    def aggregate(
        questions_with_results: Sequence[dict[str, Any]],
        default_document_id: str | None = None,
        default_document_title: str = "Tài liệu học tập",
    ) -> list[DocumentReviewRecommendation]:
        """Collects target pages from incorrect questions, grouped by document.

        Args:
            questions_with_results: Sequence of dicts containing:
                - question_id: str
                - is_correct: bool
                - target_page: int | None
                - topic_tag: str | None
                - source_document_id: str | None
                - source_document_title: str | None
            default_document_id: Fallback document ID if question has none.
            default_document_title: Fallback document title.

        Returns:
            List of DocumentReviewRecommendation sorted by document title.
        """
        if not questions_with_results:
            return []

        doc_groups: dict[str | None, dict[str, Any]] = {}

        for item in questions_with_results:
            if item.get("is_correct"):
                continue

            try:
                raw_target_page = item.get("target_page")
                if raw_target_page is None:
                    continue
                page_num = int(raw_target_page)
                if page_num <= 0:
                    continue
            except (TypeError, ValueError):
                continue

            raw_doc_id = item.get("source_document_id") or default_document_id
            doc_id = str(raw_doc_id) if raw_doc_id is not None else None
            doc_title = (
                item.get("source_document_title")
                or default_document_title
                or "Tài liệu học tập"
            )

            if doc_id not in doc_groups:
                doc_groups[doc_id] = {
                    "document_id": doc_id,
                    "document_title": doc_title,
                    "pages": set(),
                    "topics": set(),
                }

            doc_groups[doc_id]["pages"].add(page_num)
            topic = (item.get("topic_tag") or "").strip()
            if topic:
                doc_groups[doc_id]["topics"].add(topic)

        results: list[DocumentReviewRecommendation] = []
        for group in doc_groups.values():
            sorted_pages = sorted(group["pages"])
            sorted_topics = sorted(group["topics"])
            results.append(
                DocumentReviewRecommendation(
                    document_id=group["document_id"],
                    document_title=group["document_title"],
                    pages=sorted_pages,
                    topics=sorted_topics,
                )
            )

        return sorted(results, key=lambda r: r.document_title)
