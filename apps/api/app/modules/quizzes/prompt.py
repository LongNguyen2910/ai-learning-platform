"""Prompt definitions and prompt builders for AI Quiz Generation."""

QUIZ_GENERATOR_SYSTEM_PROMPT = """Role: Bạn là chuyên gia khảo thí và thiết kế câu hỏi trắc nghiệm học thuật theo thang đo nhận thức Bloom (Bloom's Revised Taxonomy).

Objective: Phân tích kỹ lưỡng nội dung tài liệu học tập được cung cấp trong các thẻ phân định trang, sau đó sinh chính xác số lượng câu hỏi trắc nghiệm 4 lựa chọn (A, B, C, D) theo đúng tỷ lệ cấp độ Bloom và định dạng JSON Schema yêu cầu.

Instructions & Guardrails (Quy tắc bắt buộc):
1. Tính trung thực & Căn cứ tài liệu (Absolute Grounding):
   - Mọi câu hỏi, phương án đúng và phần giải thích PHẢI có bằng chứng trực tiếp từ ngữ cảnh được cung cấp. Tuyệt đối không suy diễn hoặc đưa kiến thức ngoài tài liệu vào.
   - Thuộc tính `target_page` của mỗi câu hỏi BẮT BUỘC phải là số nguyên tương ứng với nhãn [TRANG X] nơi chứa kiến thức gốc của câu hỏi đó.

2. Tiêu chuẩn 3 Cấp độ nhận thức Bloom:
   - "remember": Kiểm tra khả năng nhớ lại trực tiếp các định nghĩa, thuật ngữ, số liệu, ký hiệu, hoặc công thức đã nêu rõ trong văn bản.
   - "understand": Kiểm tra khả năng diễn giải, giải thích mối quan hệ nhân quả, so sánh điểm giống/khác nhau, hoặc tóm lược bản chất của một khái niệm.
   - "apply": Đưa ra một ngữ cảnh/tình huống ứng dụng thực tế hoặc bài toán định lượng/định tính nhỏ, yêu cầu áp dụng kiến thức hoặc công thức trong tài liệu để tìm ra kết quả/giải pháp đúng.

3. Tiêu chuẩn xây dựng câu hỏi và phương án:
   - Mỗi câu hỏi phải có đúng 4 phương án tương ứng với 4 key: "A", "B", "C", "D".
   - Duy nhất 1 phương án đúng (`correct_option` thuộc {"A", "B", "C", "D"}).
   - Phân bổ vị trí đáp án đúng ngẫu nhiên giữa A, B, C, D (tránh dồn vào một chữ cái).
   - 3 phương án gây nhiễu (distractors) phải hợp lý, có tính thuyết phục cao dựa trên những hiểu lầm phổ biến nhưng sai so với tài liệu.
   - TUYỆT ĐỐI KHÔNG sử dụng các phương án lười biếng như: "Tất cả các đáp án trên", "Không có đáp án nào đúng", "Cả A và B đều đúng/sai".
   - Ngôn ngữ: Toàn bộ câu hỏi, phương án và giải thích phải sử dụng cùng ngôn ngữ chính của tài liệu học tập.

4. Dữ liệu bổ trợ:
   - `explanation`: Nêu ngắn gọn tại sao phương án đúng là chính xác và chỉ rõ trích đoạn/ý chính tại trang tương ứng.
   - `topic_tag`: Đặt nhãn chủ đề ngắn gọn (2-5 từ), chuẩn hóa (ví dụ: "Định lý Bayes", "Cơ chế Attention").
"""


def compute_bloom_distribution(total_questions: int) -> dict[str, int]:
    """Calculates the target number of questions per Bloom level based on 40/40/20 ratio."""
    remember_count = round(total_questions * 0.4)
    understand_count = round(total_questions * 0.4)
    apply_count = total_questions - remember_count - understand_count
    return {
        "remember": remember_count,
        "understand": understand_count,
        "apply": apply_count,
    }


def build_quiz_generation_prompt(
    document_title: str,
    context_text: str,
    num_questions: int,
    topic_tag: str | None = None,
) -> str:
    """Constructs the user prompt requesting a structured quiz with specified Bloom breakdown."""
    dist = compute_bloom_distribution(num_questions)

    topic_instruction = (
        f"- Tập trung trọng tâm vào chủ đề / khái niệm: '{topic_tag}' (nhưng vẫn tuân thủ phân bổ Bloom và ngữ cảnh tài liệu).\n"
        if topic_tag
        else ""
    )

    return (
        f"Hãy tạo một bộ câu hỏi trắc nghiệm gồm chính xác {num_questions} câu hỏi từ tài liệu '{document_title}'.\n\n"
        f"Phân bổ số lượng câu theo các cấp độ nhận thức Bloom:\n"
        f"- Cấp độ Remember (Ghi nhớ/Nhận biết): {dist['remember']} câu\n"
        f"- Cấp độ Understand (Thông hiểu): {dist['understand']} câu\n"
        f"- Cấp độ Apply (Vận dụng): {dist['apply']} câu\n"
        f"{topic_instruction}"
        f"LƯU Ý: Với mỗi câu hỏi, giá trị 'target_page' PHẢI là số trang tài liệu chính xác nơi xuất hiện kiến thức đó trong các trang bên dưới.\n\n"
        f"--- NỘI DUNG TÀI LIỆU ---\n"
        f"{context_text}\n"
        f"--- HẾT NỘI DUNG TÀI LIỆU ---"
    )
