import pytest

from app.modules.quizzes.domain.entities import GapSeverity
from app.modules.quizzes.domain.knowledge_gap_analyzer import KnowledgeGapAnalyzer
from app.modules.quizzes.domain.review_page_aggregator import ReviewPageAggregator


def test_empty_questions_analysis():
    result = KnowledgeGapAnalyzer.analyze([])
    assert result.score == 0.0
    assert result.total_questions == 0
    assert result.total_correct == 0
    assert result.total_incorrect == 0
    assert result.weak_topics == []
    assert result.mastered_topics == []
    assert result.review_recommendations == []


def test_all_correct_produces_only_mastered_topics():
    questions = [
        {
            "question_id": "q1",
            "is_correct": True,
            "bloom_level": "remember",
            "topic_tag": "Định lý Bayes",
            "target_page": 10,
        },
        {
            "question_id": "q2",
            "is_correct": True,
            "bloom_level": "apply",
            "topic_tag": "Định lý Bayes",
            "target_page": 11,
        },
    ]

    result = KnowledgeGapAnalyzer.analyze(questions)
    assert result.score == 100.0
    assert result.total_correct == 2
    assert result.total_incorrect == 0
    assert len(result.weak_topics) == 0
    assert len(result.mastered_topics) == 1

    mastered = result.mastered_topics[0]
    assert mastered.topic_tag == "Định lý Bayes"
    assert mastered.is_gap is False
    assert mastered.severity is None
    assert mastered.bloom_matrix.remember_correct == 1
    assert mastered.bloom_matrix.apply_correct == 1
    assert result.review_recommendations == []


def test_critical_foundation_gap_when_remember_or_understand_wrong():
    questions = [
        {
            "question_id": "q1",
            "is_correct": False,
            "bloom_level": "remember",
            "topic_tag": "Attention Mechanism",
            "target_page": 15,
            "source_document_id": "doc-1",
            "source_document_title": "Deep Learning Textbook",
        },
        {
            "question_id": "q2",
            "is_correct": True,
            "bloom_level": "apply",
            "topic_tag": "Attention Mechanism",
            "target_page": 17,
            "source_document_id": "doc-1",
            "source_document_title": "Deep Learning Textbook",
        },
    ]

    result = KnowledgeGapAnalyzer.analyze(questions)
    assert result.score == 50.0
    assert result.total_correct == 1
    assert result.total_incorrect == 1
    assert len(result.weak_topics) == 1
    assert len(result.mastered_topics) == 0

    gap = result.weak_topics[0]
    assert gap.topic_tag == "Attention Mechanism"
    assert gap.is_gap is True
    assert gap.severity == GapSeverity.CRITICAL_FOUNDATION
    assert gap.incorrect_question_ids == ["q1"]

    assert len(result.review_recommendations) == 1
    rec = result.review_recommendations[0]
    assert rec.document_id == "doc-1"
    assert rec.pages == [15]
    assert "Attention Mechanism" in rec.topics


def test_application_practice_gap_when_only_apply_wrong():
    questions = [
        {
            "question_id": "q1",
            "is_correct": True,
            "bloom_level": "remember",
            "topic_tag": "Transformer",
            "target_page": 5,
        },
        {
            "question_id": "q2",
            "is_correct": True,
            "bloom_level": "understand",
            "topic_tag": "Transformer",
            "target_page": 6,
        },
        {
            "question_id": "q3",
            "is_correct": False,
            "bloom_level": "apply",
            "topic_tag": "Transformer",
            "target_page": 8,
        },
    ]

    result = KnowledgeGapAnalyzer.analyze(questions)
    assert result.score == 66.67
    assert len(result.weak_topics) == 1

    gap = result.weak_topics[0]
    assert gap.topic_tag == "Transformer"
    assert gap.severity == GapSeverity.APPLICATION_PRACTICE
    assert gap.incorrect_question_ids == ["q3"]


def test_review_page_aggregator_deduplication_and_sorting():
    questions = [
        {
            "question_id": "q1",
            "is_correct": False,
            "target_page": 20,
            "topic_tag": "Calculus",
            "source_document_id": "doc-a",
            "source_document_title": "Math Book",
        },
        {
            "question_id": "q2",
            "is_correct": False,
            "target_page": 10,
            "topic_tag": "Limits",
            "source_document_id": "doc-a",
            "source_document_title": "Math Book",
        },
        {
            "question_id": "q3",
            "is_correct": False,
            "target_page": 20,  # Duplicate page
            "topic_tag": "Derivatives",
            "source_document_id": "doc-a",
            "source_document_title": "Math Book",
        },
        {
            "question_id": "q4",
            "is_correct": True,  # Correct should be ignored
            "target_page": 99,
            "source_document_id": "doc-a",
            "source_document_title": "Math Book",
        },
        {
            "question_id": "q5",
            "is_correct": False,
            "target_page": 42,
            "topic_tag": "Physics Laws",
            "source_document_id": "doc-b",
            "source_document_title": "Physics Book",
        },
    ]

    recs = ReviewPageAggregator.aggregate(questions)
    assert len(recs) == 2

    math_rec = next(r for r in recs if r.document_id == "doc-a")
    assert math_rec.pages == [10, 20]  # Deduplicated and sorted
    assert set(math_rec.topics) == {"Calculus", "Limits", "Derivatives"}

    phys_rec = next(r for r in recs if r.document_id == "doc-b")
    assert phys_rec.pages == [42]


def test_null_or_blank_topic_tag_fallback():
    questions = [
        {
            "question_id": "q1",
            "is_correct": False,
            "bloom_level": "understand",
            "topic_tag": None,
            "target_page": 12,
        },
        {
            "question_id": "q2",
            "is_correct": False,
            "bloom_level": "remember",
            "topic_tag": "   ",
            "target_page": 13,
        },
    ]

    result = KnowledgeGapAnalyzer.analyze(questions)
    assert len(result.weak_topics) == 1
    assert result.weak_topics[0].topic_tag == "Chủ đề chung"
    assert result.weak_topics[0].severity == GapSeverity.CRITICAL_FOUNDATION


def test_review_page_aggregator_resilience_to_invalid_pages_and_uuid_types():
    import uuid

    same_doc_uuid = uuid.uuid4()
    questions = [
        {
            "question_id": "q1",
            "is_correct": False,
            "target_page": "not-a-number",
            "source_document_id": same_doc_uuid,
            "source_document_title": "Doc Title",
        },
        {
            "question_id": "q2",
            "is_correct": False,
            "target_page": -5,
            "source_document_id": same_doc_uuid,
            "source_document_title": "Doc Title",
        },
        {
            "question_id": "q3",
            "is_correct": False,
            "target_page": "15",
            "source_document_id": str(same_doc_uuid),  # Passed as string
            "source_document_title": "Doc Title",
        },
        {
            "question_id": "q4",
            "is_correct": False,
            "target_page": 25,
            "source_document_id": same_doc_uuid,  # Passed as UUID
            "source_document_title": "Doc Title",
        },
    ]

    recs = ReviewPageAggregator.aggregate(questions)
    # Both UUID and str should merge into exactly 1 document recommendation
    assert len(recs) == 1
    rec = recs[0]
    assert rec.document_id == str(same_doc_uuid)
    # "not-a-number" and -5 ignored, "15" and 25 parsed
    assert rec.pages == [15, 25]

