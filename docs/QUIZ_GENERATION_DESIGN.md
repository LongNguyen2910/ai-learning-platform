# Thiết Kế Chi Tiết: Endpoint Sinh Quiz Tự Động (Gemini Structured Output)

## 1. Tóm tắt & Mục tiêu (Understanding Summary)
* **Tính năng**: Endpoint API `POST /api/v1/quizzes/generate` sinh bộ câu hỏi trắc nghiệm tự động từ tài liệu học tập của người dùng bằng **Gemini Structured Output** (`response_schema` với Pydantic).
* **Mục đích**: Hỗ trợ người học kiểm tra nhanh mức độ nắm bắt kiến thức sau khi đọc tài liệu, phân loại nhận thức chuẩn xác theo thang đo Bloom và đính kèm số trang gốc (`target_page`) để dễ dàng đối chiếu ôn tập.
* **Đối tượng**: Học viên sử dụng nền tảng AI Learning Platform.
* **Số lượng & Phân bổ Bloom**:
  * Tổng số câu hỏi: 5 - 10 câu (mặc đinh 5 câu).
  * 3 Cấp độ nhận thức:
    * **Remember** (Nhận biết/Ghi nhớ): ~40%
    * **Understand** (Thông hiểu): ~40%
    * **Apply** (Vận dụng): ~20%
* **Dữ liệu mỗi câu hỏi**: Nội dung câu hỏi, 4 lựa chọn (A, B, C, D), đáp án đúng, giải thích (`explanation`), số trang trích xuất (`target_page`), nhãn chủ đề (`topic_tag`).
* **Lưu trữ**: Lưu trực tiếp vào PostgreSQL (bảng `quizzes` và `quiz_questions`), trả về ID của Quiz để sẵn sàng làm bài.
* **Phi mục tiêu (Non-goals)**: Chưa thực hiện nộp bài/chấm điểm attempt tại endpoint này (sẽ có endpoint nộp bài riêng).

---

## 2. Nhật Ký Quyết Định (Decision Log)

| Quyết định | Các phương án đã cân nhắc | Lý do lựa chọn |
| :--- | :--- | :--- |
| **Phạm vi nội dung đầu vào** | Toàn bộ Doc vs Khoảng trang vs Theo Roadmap | **Linh hoạt theo Doc & Page Range**: Bắt buộc `document_id`, tuỳ chọn lọc theo khoảng trang (`page_start`, `page_end`) hoặc `topic_tag`. |
| **3 Cấp độ Bloom** | 6 cấp độ Bloom / Nhóm 3 tầng / Remember-Understand-Apply | **Remember - Understand - Apply**: Phù hợp nhất cho trắc nghiệm 4 lựa chọn, phân bổ tỷ lệ ~40% / ~40% / ~20%. |
| **Cơ chế lưu trữ** | Lưu ngay vào DB vs Preview in-memory | **Lưu trực tiếp vào PostgreSQL**: Trả về `quiz_id` để client có thể bắt đầu làm bài ngay. |
| **Kiến trúc sinh Quiz** | Direct Context vs RAG Search vs Asynchronous Job | **Direct Context Reader + Gemini Structured Output**: Đơn giản, độ trễ thấp (3-6s), chính xác số trang `target_page`. |
| **Cấu trúc Options** | Key-value Map vs List các object có key/text | **Danh sách `[{key: "A", text: "..."}, ...]`**: Đồng nhất với schema `JSONB` hiện tại trong database. |

---

## 3. Giả định & Ràng buộc Phi chức năng (Assumptions & NFRs)
1. **Xác thực & Bảo mật**: Bắt buộc đăng nhập (JWT). Kiểm tra quyền sở hữu `document_id` thuộc về `current_user.id` (chống lỗ hổng IDOR).
2. **Hiệu năng & Thời gian phản hồi**: Sử dụng model Gemini Flash qua `google-genai` SDK, thời gian phản hồi kỳ vọng 3–6s, timeout cấu hình 30s.
3. **Tính toàn vẹn dữ liệu (ACID)**: Quá trình tạo `Quiz` và các `QuizQuestion` được bọc trong một Database Transaction duy nhất.
4. **Trích xuất Context**: Đọc các file markdown trang (`storage/documents/{doc_id}/pages/page_{i}.md`), bọc thẻ `=== BẮT ĐẦU TRANG X ===` để đảm bảo Gemini định vị chính xác `target_page`.

---

## 4. Đặc tả Hợp đồng Dữ liệu (Data Contracts & Schemas)

### 4.1. Gemini Structured Output Schema
```python
from enum import Enum
from pydantic import BaseModel, Field

class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"

class QuizOptionItem(BaseModel):
    key: str = Field(description="Mã đáp án: A, B, C hoặc D")
    text: str = Field(description="Nội dung chi tiết của lựa chọn")

class GeneratedQuestionItem(BaseModel):
    question_text: str = Field(description="Nội dung câu hỏi trắc nghiệm")
    bloom_level: BloomLevel = Field(description="Cấp độ Bloom: remember, understand hoặc apply")
    options: list[QuizOptionItem] = Field(description="Đúng 4 lựa chọn A, B, C, D")
    correct_option: str = Field(description="Đáp án đúng: A, B, C hoặc D")
    explanation: str = Field(description="Giải thích ngắn gọn vì sao đáp án đúng dựa vào tài liệu")
    target_page: int = Field(description="Số trang tài liệu chính xác nơi xuất hiện kiến thức này")
    topic_tag: str = Field(description="Nhãn chủ đề hoặc khái niệm chính")

class GeneratedQuizPayload(BaseModel):
    title: str = Field(description="Tiêu đề gợi ý phù hợp cho bộ Quiz")
    questions: list[GeneratedQuestionItem] = Field(description="Danh sách các câu hỏi được sinh")
```

### 4.2. API Request & Response DTOs
```python
from uuid import UUID
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class QuizGenerateRequest(BaseModel):
    document_id: UUID
    num_questions: int = Field(default=5, ge=5, le=10)
    page_start: Optional[int] = Field(default=1, ge=1)
    page_end: Optional[int] = Field(default=None, ge=1)
    topic_tag: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=255)

class QuizQuestionResponse(BaseModel):
    id: UUID
    question_text: str
    bloom_level: str
    options: list[QuizOptionItem]
    correct_option: str
    explanation: Optional[str]
    target_page: Optional[int]
    topic_tag: Optional[str]

    model_config = {"from_attributes": True}

class QuizResponse(BaseModel):
    id: UUID
    document_id: UUID
    subject_id: Optional[UUID]
    title: str
    total_questions: int
    time_limit_minutes: int
    created_at: datetime
    questions: list[QuizQuestionResponse]

    model_config = {"from_attributes": True}
```

---

## 5. Đặc tả Prompt & Quy tắc Khảo thí

### 5.1. System Instruction (`QUIZ_GENERATOR_SYSTEM_PROMPT`)
```text
Role: Bạn là chuyên gia khảo thí và thiết kế câu hỏi trắc nghiệm học thuật theo thang đo nhận thức Bloom (Bloom's Revised Taxonomy).

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
```

### 5.2. Công thức phân bổ số lượng câu
Cho tổng số câu hỏi $N \in [5, 10]$:
* $N_{\text{remember}} = \text{round}(N \times 0.4)$
* $N_{\text{understand}} = \text{round}(N \times 0.4)$
* $N_{\text{apply}} = N - N_{\text{remember}} - N_{\text{understand}}$

---

## 6. Kiến trúc Triển khai & Cấu trúc Thư mục

Module `quizzes` trong backend:
```
apps/api/app/modules/quizzes/
├── __init__.py
├── models.py         # Quiz, QuizQuestion, QuizAttempt, QuizAttemptAnswer
├── schemas.py        # QuizGenerateRequest, QuizResponse, GeneratedQuizPayload, v.v.
├── prompt.py         # System prompt & prompt templates
├── service.py        # QuizService: Context loader, Gemini caller, DB persistence
└── router.py         # Endpoints: POST /quizzes/generate, GET /quizzes/{id}
```

---

## 7. Xử lý Lỗi & Kiểm thử

### 7.1. Xử lý lỗi (Error Handling)
* `DocumentNotFoundError` (404): Nếu `document_id` không tồn tại hoặc không thuộc quyền sở hữu của user.
* `DocumentNotReadyError` (400): Nếu `document.status != "completed"` hoặc các file markdown trang chưa hoàn tất.
* `GeminiGenerationError` (502): Bọc ngoại lệ từ `google-genai`, ghi log chi tiết và trả lỗi thân thiện.
* `InvalidPageRangeError` (422): `page_start > page_end` hoặc `page_start > total_pages`.

### 7.2. Kế hoạch kiểm thử (Testing Strategy)
* **Unit Tests**:
  * Kiểm tra logic phân bổ số lượng Bloom theo công thức.
  * Mock Gemini API trả về `GeneratedQuizPayload`, verify tính toàn vẹn dữ liệu.
* **Integration Tests**:
  * Kiểm tra endpoint `POST /api/v1/quizzes/generate` ghi thành công vào PostgreSQL.
  * Kiểm tra chống lỗ hổng bảo mật IDOR giữa các user.
  * Kiểm tra endpoint `GET /api/v1/quizzes/{id}` đọc lại đầy đủ thông tin quiz kèm danh sách câu hỏi.
