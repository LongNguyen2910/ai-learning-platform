import pytest

from app.modules.chat.reverse_tutoring import (
    REVERSE_SUGGEST_TOPICS_PROMPT,
    compose_reverse_tutoring_prompt,
    parse_rubric_metadata,
)
from app.modules.chat.schemas import RetrievedChunkDTO


def _make_chunk(page: int, score: float, content: str = "Khái niệm bảo toàn") -> RetrievedChunkDTO:
    return RetrievedChunkDTO(
        chunk_id=f"c{page}",
        page_number=page,
        chunk_index=0,
        score=score,
        content=content,
        has_formula=True,
        has_image=False,
        citation_tag=f"[[Trang {page}]]",
    )


def test_suggest_prompt_contains_rag_chunks_and_format():
    chunks = [_make_chunk(5, 0.85, "Định luật bảo toàn cơ năng"), _make_chunk(6, 0.78)]
    prompt = compose_reverse_tutoring_prompt(
        phase="suggest",
        target_concept=None,
        chunks=chunks,
    )

    assert "Bạn là trợ lý gợi ý chủ đề" in prompt
    assert "[[Trang 5]]" in prompt
    assert "Định luật bảo toàn cơ năng" in prompt
    assert "Hãy chọn 1 chủ đề dưới đây để thử tài làm \"gia sư\" cho mình nhé:" in prompt


def test_student_roleplay_prompt_injects_concept_and_rules():
    concept = "Hiệu ứng Doppler"
    chunks = [_make_chunk(10, 0.9, "Sự thay đổi tần số sóng")]
    prompt = compose_reverse_tutoring_prompt(
        phase="roleplay",
        target_concept=concept,
        chunks=chunks,
    )

    assert concept in prompt
    assert "Bạn là \"Bạn Học Tò Mò\"" in prompt
    assert "mình - bạn" in prompt
    assert "TUYỆT ĐỐI KHÔNG GIẢI BÀI HOẶC TỔNG KẾT" in prompt
    assert "$...$" in prompt or "$$...$$" in prompt
    assert "[[Trang 10]]" in prompt


def test_evaluator_prompt_injects_concept_and_rubric_schema():
    concept = "Quang điện ngoài"
    chunks = [_make_chunk(15, 0.95)]
    prompt = compose_reverse_tutoring_prompt(
        phase="evaluate",
        target_concept=concept,
        chunks=chunks,
    )

    assert concept in prompt
    assert "Chuyên gia Đánh giá Sư phạm cao cấp theo Kỹ thuật Feynman" in prompt
    assert "Độ chính xác cốt lõi" in prompt
    assert "Tính trực quan & Dễ hiểu" in prompt
    assert "Khả năng gỡ rối hiểu lầm" in prompt
    assert "json:rubric_metadata" in prompt
    assert "accuracy_score" in prompt


def test_parse_rubric_metadata_valid_json():
    raw_output = """
### 🎓 Kết Quả Đánh Giá Giảng Bài (Feynman Rubric)

| Tiêu chí | Điểm | Nhận xét chi tiết |
| :--- | :---: | :--- |
| **1. Độ chính xác cốt lõi** | 9/10 | Nắm rất chắc bản chất định luật. |
| **2. Tính trực quan & Dễ hiểu** | 8/10 | Ví dụ tàu hỏa hú còi rất trực quan. |
| **3. Khả năng bắt bẻ lỗi sai** | 9/10 | Bắt bẻ ngộ nhận của bạn học thuyết phục. |

**💡 Điểm sáng:** Giải thích dễ hiểu bằng ví dụ thực tế.  
**🎯 Lỗ hổng cần khắc phục:** Chưa nêu rõ điều kiện sóng cơ học.  
**📖 Đề xuất ôn tập:** Xem lại [[Trang 10]] để nắm rõ công thức tần số quan sát.

```json:rubric_metadata
{
  "accuracy_score": 9,
  "simplicity_score": 8,
  "misconception_score": 9,
  "feedback_summary": "Giải thích xuất sắc, ví dụ trực quan dễ hiểu."
}
```
"""
    parsed = parse_rubric_metadata(raw_output)
    assert parsed is not None
    assert parsed["accuracy_score"] == 9
    assert parsed["simplicity_score"] == 8
    assert parsed["misconception_score"] == 9
    assert "Giải thích xuất sắc" in parsed["feedback"]


def test_parse_rubric_metadata_clamps_scores():
    raw_output = """
```json:rubric_metadata
{
  "accuracy_score": 15,
  "simplicity_score": -2,
  "misconception_score": 7,
  "feedback_summary": "Tốt"
}
```
"""
    parsed = parse_rubric_metadata(raw_output)
    assert parsed is not None
    assert parsed["accuracy_score"] == 10  # Clamped to max 10
    assert parsed["simplicity_score"] == 0  # Clamped to min 0
    assert parsed["misconception_score"] == 7


def test_parse_rubric_metadata_returns_none_when_missing():
    assert parse_rubric_metadata("Chưa có khối JSON nào ở đây") is None
