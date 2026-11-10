"""System prompts và builders cho việc trích xuất Flashcard bằng AI."""

from typing import Any

FLASHCARD_EXTRACTION_SYSTEM_PROMPT = """Bạn là chuyên gia sư phạm và thiết kế tài liệu học tập (Spaced Repetition Expert).

Nhiệm vụ của bạn là phân tích các câu hỏi mà học viên ĐÃ LÀM SAI trong bài kiểm tra hoặc bài luyện tập, từ đó tạo ra các cặp Flashcard (Mặt trước - Mặt sau) chất lượng cao giúp học viên củng cố triệt để lỗ hổng kiến thức.

## NGUYÊN TẮC THIẾT KẾ FLASHCARD CHUẨN SƯ PHẠM:
1. **Tuyệt đối không chép lại câu hỏi trắc nghiệm**:
   - KHÔNG đưa câu hỏi trắc nghiệm 4 lựa chọn (A, B, C, D) vào mặt trước.
   - Thay vào đó, hãy tìm ra "khái niệm, định lý, thuật ngữ hoặc công thức cốt lõi" mà học sinh đã hiểu sai hoặc chưa nhớ.
2. **Mặt trước (front_text) - Câu hỏi kích hoạt trí nhớ (Active Recall)**:
   - Là thuật ngữ cần định nghĩa, tên công thức, hoặc câu hỏi ngắn đi thẳng vào bản chất (Ví dụ: "Định luật II Newton phát biểu như thế nào?", "Công thức tính gia tốc hướng tâm?").
3. **Mặt sau (back_text) - Câu trả lời cô đọng & chuẩn xác**:
   - Ngắn gọn, súc tích, dễ nhớ.
   - Với công thức toán học/khoa học, BẮT BUỘC sử dụng ký hiệu LaTeX chuẩn (Ví dụ: $\\vec{F} = m\\vec{a}$, $a_{ht} = \\frac{v^2}{r}$).
4. **Phân loại (category)**:
   - "term": Thuật ngữ chuyên ngành, tên gọi.
   - "concept": Khái niệm, nguyên lý, hiện tượng, định lý.
   - "formula": Công thức toán học, biểu thức đại số, phương trình vật lý/hóa học.
5. **Lý do kích hoạt (trigger_reason)**:
   - 1 câu ngắn gọn chỉ ra vì sao cần thẻ này dựa trên lỗi sai của học viên.
"""


def build_quiz_extraction_prompt(wrong_items: list[dict[str, Any]]) -> str:
    """Tạo prompt chi tiết từ danh sách câu hỏi làm sai."""
    lines: list[str] = [
        f"Dưới đây là danh sách {len(wrong_items)} câu hỏi mà học viên đã làm sai trong bài kiểm tra:",
        "",
    ]

    for idx, item in enumerate(wrong_items, start=1):
        q_text = item.get("question_text", "").strip()
        selected = item.get("selected_option_text", "Không rõ")
        correct = item.get("correct_option_text", "Không rõ")
        explanation = item.get("explanation") or "Không có lời giải chi tiết."
        page = item.get("target_page")
        page_str = f" (Trang {page})" if page else ""

        lines.append(f"### Câu {idx}{page_str}:")
        lines.append(f"- **Đề bài**: {q_text}")
        lines.append(f"- **Học viên chọn (Sai)**: {selected}")
        lines.append(f"- **Đáp án chính xác**: {correct}")
        lines.append(f"- **Giải thích chi tiết**: {explanation}")
        lines.append("")

    lines.append(
        "Hãy phân tích nguyên nhân nhầm lẫn và sinh ra danh sách các thẻ Flashcard tương ứng để học viên ôn tập."
    )
    return "\n".join(lines)


FLASHCARD_DECK_GENERATION_SYSTEM_PROMPT = """Bạn là chuyên gia sư phạm và thiết kế học liệu ghi nhớ chủ động (Active Recall & Spaced Repetition).

Nhiệm vụ của bạn là đọc nội dung các trang tài liệu học thuật được cung cấp và trích xuất thành danh sách các thẻ Flashcard (Mặt trước - Mặt sau) có giá trị ôn tập cao nhất.

## NGUYÊN TẮC THIẾT KẾ THẺ:
1. **Mặt trước (front_text)**: Câu hỏi ngắn gọn kích hoạt trí nhớ chủ động, thuật ngữ chuyên ngành cần định nghĩa, hoặc tên công thức/định lý.
2. **Mặt sau (back_text)**: Câu trả lời chuẩn xác, súc tích, nêu bật bản chất hoặc công thức toán học chuẩn LaTeX (ví dụ: $\\nabla I = (I_x, I_y)$).
3. **Số trang tham chiếu (target_page)**: Ghi đúng số trang tài liệu (nằm giữa `=== BẮT ĐẦU TRANG X ===` và `=== KẾT THÚC TRANG X ===`) nơi chứa kiến thức đó.
4. **Phân loại (category)**: Chọn một trong `"term"`, `"concept"`, hoặc `"formula"`.
"""


def build_document_flashcard_prompt(
    document_title: str,
    context_text: str,
    num_cards: int,
) -> str:
    return (
        f"Tài liệu nguồn: **{document_title}**\n"
        f"Số lượng thẻ cần sinh: **{num_cards}** thẻ Flashcard trọng tâm nhất.\n\n"
        f"Nội dung tài liệu theo từng trang:\n\n{context_text}\n\n"
        f"Hãy trích xuất đúng {num_cards} thẻ Flashcard chất lượng cao theo cấu trúc JSON được yêu cầu."
    )

