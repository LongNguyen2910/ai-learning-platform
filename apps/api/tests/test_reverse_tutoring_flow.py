from types import SimpleNamespace
import pytest

from app.modules.chat.reverse_tutoring import (
    MAX_REVERSE_TURNS,
    determine_reverse_state,
)
from app.modules.chat.schemas import ChatRequest


def _make_msg(mode: str, phase: str, turn_count: int, concept: str | None = None):
    return SimpleNamespace(
        sender="assistant",
        content="mock content",
        mode=mode,
        mode_metadata={
            "reverse_phase": phase,
            "turn_count": turn_count,
            "target_concept": concept,
        },
    )


def test_initial_state_defaults_to_suggest():
    req = ChatRequest(content="Bắt đầu học thử vai nào", mode="reverse_tutoring")
    phase, turns, concept = determine_reverse_state(req, history=[])
    assert phase == "suggest"
    assert turns == 0
    assert concept is None


def test_start_session_action_initiates_roleplay():
    req = ChatRequest(
        content="Để mình giảng cho bạn về Định luật Ôm nhé",
        mode="reverse_tutoring",
        reverse_action="start_session",
        target_concept="Định luật Ôm",
    )
    phase, turns, concept = determine_reverse_state(req, history=[])
    assert phase == "roleplay"
    assert turns == 1
    assert concept == "Định luật Ôm"


def test_roleplay_turn_count_increments():
    history = [
        _make_msg("reverse_tutoring", "roleplay", 1, "Định luật Ôm"),
    ]
    req = ChatRequest(
        content="Cường độ dòng điện tỉ lệ thuận với hiệu điện thế",
        mode="reverse_tutoring",
    )
    phase, turns, concept = determine_reverse_state(req, history=history)
    assert phase == "roleplay"
    assert turns == 2
    assert concept == "Định luật Ôm"


def test_hard_turn_limit_auto_transitions_to_evaluate():
    # Previous turn was 3 (total 3 completed turns). Turn 4 reaches the hard limit.
    history = [
        _make_msg("reverse_tutoring", "roleplay", 3, "Định luật Ôm"),
    ]
    req = ChatRequest(
        content="Điện trở $R$ phụ thuộc vào bản chất vật dẫn",
        mode="reverse_tutoring",
    )
    phase, turns, concept = determine_reverse_state(req, history=history)
    assert phase == "evaluate"
    assert turns == MAX_REVERSE_TURNS
    assert concept == "Định luật Ôm"


def test_explicit_evaluate_action_transitions_immediately():
    history = [
        _make_msg("reverse_tutoring", "roleplay", 2, "Thuyết tương đối hẹp"),
    ]
    req = ChatRequest(
        content="Mình giải thích xong rồi, bạn đánh giá giúp mình nhé",
        mode="reverse_tutoring",
        reverse_action="evaluate",
    )
    phase, turns, concept = determine_reverse_state(req, history=history)
    assert phase == "evaluate"
    assert concept == "Thuyết tương đối hẹp"


def test_suggest_topics_action_resets_to_suggest():
    history = [
        _make_msg("reverse_tutoring", "roleplay", 2, "Thuyết tương đối hẹp"),
    ]
    req = ChatRequest(
        content="Gợi ý chủ đề khác cho mình đi",
        mode="reverse_tutoring",
        reverse_action="suggest_topics",
    )
    phase, turns, concept = determine_reverse_state(req, history=history)
    assert phase == "suggest"
    assert turns == 0
    assert concept is None
