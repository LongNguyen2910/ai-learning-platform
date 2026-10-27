import re

import pytest

from app.modules.chat.prompt_composer import (
    NO_CONTEXT_BLOCK,
    build_rag_context,
    compose_system_prompt,
    resolve_socratic_tier,
)
from app.modules.chat.schemas import RetrievedChunkDTO
from app.modules.chat.socratic_tiers import (
    NORMAL_MODE_PROMPT,
    SECURITY_ALERT_PROMPT,
    SOLVED_MARKER,
    TIER_1_THEORY_HINT,
    TIER_2_ANALOGOUS_EXAMPLE,
    TIER_3_SCAFFOLDED_STEPS,
)


def _chunk(page: int, score: float, content: str = "Nội dung") -> RetrievedChunkDTO:
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


# ---------------------------------------------------------------- tier logic


def test_tier_starts_at_one_for_first_turn():
    assert resolve_socratic_tier("Giải hộ mình bài này", prev_tier=0) == 1


def test_tier_escalates_1_to_2_on_chua_hieu():
    assert resolve_socratic_tier("Mình vẫn chưa hiểu lắm", prev_tier=1) == 2


def test_tier_escalates_2_to_3_on_kho_qua():
    assert resolve_socratic_tier("Khó quá bạn ơi", prev_tier=2) == 3


def test_tier_caps_at_three():
    assert resolve_socratic_tier("bí quá, chịu rồi", prev_tier=3) == 3


def test_tier_stays_without_stuck_signal():
    assert resolve_socratic_tier("Mình nghĩ là S = pi R^2", prev_tier=2) == 2


def test_new_question_resets_to_tier_one():
    assert resolve_socratic_tier("Bài mới nè", prev_tier=3, is_new_question=True) == 1


@pytest.mark.parametrize("requested", [1, 2, 3])
def test_requested_tier_overrides(requested):
    assert resolve_socratic_tier("abc", prev_tier=1, requested_tier=requested) == requested


def test_invalid_requested_tier_is_ignored():
    assert resolve_socratic_tier("chưa hiểu", prev_tier=1, requested_tier=7) == 2


# --------------------------------------------------------- prompt assembly


def test_compose_prompt_contains_citation_tags_and_latex_rules():
    chunks = [_chunk(14, 0.8, "Công thức $S = \\pi R^2$"), _chunk(15, 0.7)]
    prompt = compose_system_prompt(socratic_tier=1, chunks=chunks)

    assert "[[Trang 14]]" in prompt
    assert "[[Trang 15]]" in prompt
    assert "$...$" in prompt and "$$...$$" in prompt
    assert "CẤM dùng `\\[ \\]` hay `\\( \\)`" in prompt
    assert TIER_1_THEORY_HINT in prompt
    assert SOLVED_MARKER in prompt


@pytest.mark.parametrize(
    ("tier", "expected", "absent"),
    [
        (1, TIER_1_THEORY_HINT, TIER_2_ANALOGOUS_EXAMPLE),
        (2, TIER_2_ANALOGOUS_EXAMPLE, TIER_3_SCAFFOLDED_STEPS),
        (3, TIER_3_SCAFFOLDED_STEPS, TIER_1_THEORY_HINT),
    ],
)
def test_compose_prompt_selects_exactly_one_tier(tier, expected, absent):
    prompt = compose_system_prompt(socratic_tier=tier, chunks=[_chunk(1, 0.9)])
    assert expected in prompt
    assert absent not in prompt
    assert NORMAL_MODE_PROMPT not in prompt


def test_compose_prompt_normal_mode_for_tier_zero():
    prompt = compose_system_prompt(socratic_tier=0, chunks=[_chunk(3, 0.9)])
    assert NORMAL_MODE_PROMPT in prompt
    assert TIER_1_THEORY_HINT not in prompt
    assert SOLVED_MARKER not in prompt


def test_compose_prompt_adds_security_alert_on_jailbreak():
    prompt = compose_system_prompt(socratic_tier=2, chunks=[], jailbreak_detected=True)
    assert SECURITY_ALERT_PROMPT in prompt


def test_rag_context_without_chunks_forbids_page_tags():
    context = build_rag_context([])
    assert context == NO_CONTEXT_BLOCK
    assert re.search(r"\[\[Trang \d+\]\]", context) is None


def test_rag_context_ordered_by_score_and_capped():
    chunks = [_chunk(p, s) for p, s in [(1, 0.55), (2, 0.95), (3, 0.7), (4, 0.6), (5, 0.8), (6, 0.65)]]
    context = build_rag_context(chunks)
    pages = [int(p) for p in re.findall(r"\[\[Trang (\d+)\]\]:", context)]
    assert pages == [2, 5, 3, 6, 4]  # top-5 by score, lowest (page 1) dropped


def test_rag_context_truncates_long_chunks():
    context = build_rag_context([_chunk(1, 0.9, "x" * 5000)])
    assert len(context) < 2500
