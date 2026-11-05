import json

from app.modules.chat.schemas import SSEStreamEvent
from app.modules.chat.service import FlashcardStreamFilter


def test_flashcard_stream_filter_single_chunk():
    """Lọc thành công tag gợi ý Flashcard trong 1 chunk và trích xuất đúng JSON payload."""
    filter_ = FlashcardStreamFilter()
    tag_data = {
        "front_text": "Định luật I Newton",
        "back_text": "Vật giữ nguyên trạng thái đứng yên hoặc chuyển động thẳng đều nếu không chịu tác dụng của lực nào.",
        "category": "concept",
        "trigger_reason": "Học sinh cho rằng cần có lực để duy trì chuyển động.",
    }
    raw_text = f"Bạn lưu ý nhé! <<<FLASHCARD_SUGGESTION:{json.dumps(tag_data)}>>> Chúc bạn học tốt."

    emitted = filter_.feed(raw_text)
    tail = filter_.flush()
    full_output = emitted + tail

    assert "Bạn lưu ý nhé!  Chúc bạn học tốt." == full_output
    assert filter_.found is True
    assert filter_.suggestion == tag_data


def test_flashcard_stream_filter_split_across_chunks():
    """Kiểm tra tag bị phân mảnh giữa các chunks trong luồng token của LLM."""
    filter_ = FlashcardStreamFilter()
    tag_data = {
        "front_text": "Công thức vận tốc",
        "back_text": "$v = v_0 + at$",
        "category": "formula",
        "trigger_reason": "Nhầm lẫn dấu gia tốc.",
    }
    json_str = json.dumps(tag_data)

    # Chia nhỏ thành 4 chunks
    c1 = "Hãy nhớ công thức sau: <<<FLASHCARD_SUGG"
    c2 = f"ESTION:{json_str[:15]}"
    c3 = f"{json_str[15:]}>>"
    c4 = "> Hãy áp dụng lại nhé!"

    out1 = filter_.feed(c1)
    out2 = filter_.feed(c2)
    out3 = filter_.feed(c3)
    out4 = filter_.feed(c4)
    out_tail = filter_.flush()

    total_visible = out1 + out2 + out3 + out4 + out_tail

    assert "<<<FLASHCARD_SUGGESTION:" not in total_visible
    assert ">>>" not in total_visible
    assert total_visible.strip() == "Hãy nhớ công thức sau:  Hãy áp dụng lại nhé!"
    assert filter_.found is True
    assert filter_.suggestion == tag_data


def test_sse_stream_event_flashcard_suggestion_event():
    """Đảm bảo SSEStreamEvent cho phép phát event 'flashcard_suggestion'."""
    payload = {
        "front_text": "Thế năng trọng trường",
        "back_text": "$W_t = mgh$",
        "category": "formula",
    }
    event = SSEStreamEvent(event="flashcard_suggestion", data=payload)
    encoded = event.encode()

    assert "event: flashcard_suggestion\n" in encoded
    assert '"front_text": "Thế năng trọng trường"' in encoded
    assert encoded.endswith("\n\n")
