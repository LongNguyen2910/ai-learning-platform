"""Modular Prompt Composer: lắp ráp System Prompt động theo tầng Socratic & ngữ cảnh RAG.

See docs/SOCRATIC_PROMPT_AND_GUARDRAIL_DESIGN.md §7.
"""

from collections.abc import Sequence

from app.modules.chat.guardrails import normalize_text
from app.modules.chat.schemas import RetrievedChunkDTO
from app.modules.chat.socratic_tiers import (
    BASE_SYSTEM_PROMPT,
    NORMAL_MODE_PROMPT,
    SECURITY_ALERT_PROMPT,
    SOCRATIC_COMMON_RULES,
    TIER_PROMPTS,
)

MIN_TIER = 1
MAX_TIER = 3

STUCK_SIGNALS: tuple[str, ...] = (
    "chưa hiểu",
    "không hiểu",
    "khó quá",
    "không biết làm",
    "bí quá",
    "gợi ý thêm",
    "ví dụ",
    "chịu rồi",
    "chưa rõ",
    "vẫn chưa",
    "không làm được",
)

# Giới hạn ngữ cảnh RAG để tránh "nhồi" prompt (giảm drift & chi phí token).
MAX_CONTEXT_CHUNKS = 5
MAX_CHUNK_CHARS = 1500

NO_CONTEXT_BLOCK = """---
[NGỮ CẢNH TÀI LIỆU HỌC TẬP]: Không tìm thấy đoạn nào trong giáo trình tải lên đủ liên quan tới câu hỏi.
---
Hãy cho người học biết nội dung này không có trong giáo trình đã tải lên, vẫn giữ phong cách hướng dẫn bằng kiến thức lý thuyết chung và TUYỆT ĐỐI KHÔNG gắn nhãn [[Trang X]]."""


def has_stuck_signal(user_query: str) -> bool:
    query_lower = normalize_text(user_query)
    return any(sig in query_lower for sig in STUCK_SIGNALS)


def resolve_socratic_tier(
    user_query: str,
    prev_tier: int,
    is_new_question: bool = False,
    requested_tier: int | None = None,
) -> int:
    """Xác định tầng Socratic phù hợp dựa trên ngữ cảnh hội thoại."""
    if requested_tier is not None and MIN_TIER <= requested_tier <= MAX_TIER:
        return requested_tier

    if is_new_question or prev_tier <= 0:
        return MIN_TIER

    if has_stuck_signal(user_query):
        return min(prev_tier + 1, MAX_TIER)

    return min(prev_tier, MAX_TIER)


def build_rag_context(chunks: Sequence[RetrievedChunkDTO]) -> str:
    """Định dạng chunks theo §7.2, sắp xếp theo độ liên quan, kèm nhãn [[Trang X]]."""
    if not chunks:
        return NO_CONTEXT_BLOCK

    ordered = sorted(chunks, key=lambda c: c.score, reverse=True)[:MAX_CONTEXT_CHUNKS]
    lines = ["---", "[NGỮ CẢNH TÀI LIỆU HỌC TẬP TỪ SÁCH GIÁO TRÌNH]:"]
    for chunk in ordered:
        content = chunk.content.strip()
        if len(content) > MAX_CHUNK_CHARS:
            content = content[:MAX_CHUNK_CHARS].rstrip() + "…"
        lines.append(f'{chunk.citation_tag}: "{content}"')
    lines.append("---")
    lines.append(
        "Hãy dùng các thông tin trên để định hướng và dẫn nguồn bằng tag [[Trang X]]."
    )
    return "\n".join(lines)


def compose_system_prompt(
    *,
    socratic_tier: int,
    chunks: Sequence[RetrievedChunkDTO],
    jailbreak_detected: bool = False,
) -> str:
    """Lắp ráp System Prompt hoàn chỉnh.

    socratic_tier = 0 -> chế độ hỏi đáp lý thuyết thông thường (NORMAL_MODE_PROMPT).
    socratic_tier 1..3 -> SOCRATIC_COMMON_RULES + prompt tầng tương ứng.
    """
    parts: list[str] = [BASE_SYSTEM_PROMPT]

    if socratic_tier in TIER_PROMPTS:
        parts.append(SOCRATIC_COMMON_RULES)
        parts.append(TIER_PROMPTS[socratic_tier])
    else:
        parts.append(NORMAL_MODE_PROMPT)

    if jailbreak_detected:
        parts.append(SECURITY_ALERT_PROMPT)

    parts.append(build_rag_context(chunks))
    return "\n\n".join(parts)
