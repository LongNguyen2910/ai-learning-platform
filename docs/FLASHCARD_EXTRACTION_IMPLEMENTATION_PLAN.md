# KẾ HOẠCH TRIỂN KHAI: HỆ THỐNG TRÍCH XUẤT TỰ ĐỘNG FLASHCARD (CHAT & QUIZ)

> **Tài liệu tham chiếu:** [docs/FLASHCARD_EXTRACTION_DESIGN.md](FLASHCARD_EXTRACTION_DESIGN.md)  
> **Kiến trúc áp dụng:** Strategy Pattern + Gemini Structured Output + SSE Real-time Inline Event  
> **Trạng thái:** Sẵn sàng thực thi (Ready for Implementation)

---

## 1. MỤC TIÊU TRIỂN KHAI

1. **Xây dựng Flashcard Extraction Core:**
   * Cung cấp endpoint `POST /api/v1/flashcards/extract` cho phép trích xuất các cặp thẻ (Thuật ngữ - Định nghĩa / Công thức - Khái niệm) từ bài Quiz có câu làm sai (`quiz_attempt`).
   * Sử dụng Google GenAI với `response_schema` đảm bảo dữ liệu trả về 100% chuẩn JSON Pydantic.
   * Xử lý tối ưu: Bỏ qua gọi LLM và trả về mảng rỗng ngay nếu bài Quiz không có câu sai (điểm 10/10).
2. **Cung cấp Bulk Persistence:**
   * Cung cấp endpoint `POST /api/v1/flashcards/bulk` cho phép học viên lưu danh sách thẻ đã duyệt vào Deck chỉ định với các thông số Spaced Repetition (SM-2) mặc định.
3. **Mở rộng AI Tutor Chat (Real-time Inline Suggestion):**
   * Bổ sung chỉ dẫn vào System Prompt của AI Tutor để phát hiện khi học viên trả lời sai hoặc có ngộ nhận khái niệm.
   * Phát event SSE `flashcard_suggestion` và tự động lưu gợi ý vào trường `metadata` (JSONB) của bảng `chat_messages`.
4. **Bảo mật & Kiểm thử:**
   * Bảo vệ quyền sở hữu dữ liệu (chống tấn công IDOR) trên mọi tài nguyên Quiz và Chat.
   * Đạt độ bao phủ kiểm thử tự động với Pytest (Unit tests + Integration tests).

---

## 2. MA TRẬN FILES TÁC ĐỘNG

| File | Hành động | Mục đích |
| :--- | :---: | :--- |
| `apps/api/app/modules/flashcards/schemas.py` | **Tạo mới** | Pydantic DTOs cho Extract Request/Response và Bulk Create |
| `apps/api/app/modules/flashcards/prompt.py` | **Tạo mới** | Prompt trích xuất chuẩn hóa tri thức từ câu hỏi sai |
| `apps/api/app/modules/flashcards/service.py` | **Tạo mới** | `FlashcardService` + `QuizExtractionStrategy` + Gemini Structured Output |
| `apps/api/app/modules/flashcards/router.py` | **Tạo mới** | APIRouter `/api/v1/flashcards` với các route `/extract` và `/bulk` |
| `apps/api/app/modules/flashcards/__init__.py` | **Chỉnh sửa** | Export `flashcards_router` và `flashcard_service` |
| `apps/api/app/main.py` | **Chỉnh sửa** | Đăng ký `flashcards_router` vào ứng dụng FastAPI |
| `apps/api/app/modules/chat/schemas.py` | **Chỉnh sửa** | Bổ sung `FlashcardSuggestionPayload` vào schema SSE và Message |
| `apps/api/app/modules/chat/service.py` | **Chỉnh sửa** | Bắt marker gợi ý flashcard và bắn event `flashcard_suggestion` qua SSE |
| `apps/api/tests/test_flashcard_extraction.py` | **Tạo mới** | Bộ kiểm thử tự động cho Quiz Extraction & Bulk Save |
| `apps/api/tests/test_chat_flashcard_inline.py` | **Tạo mới** | Bộ kiểm thử cho Chat Inline Misconception & Metadata |

---

## 3. CÁC BƯỚC THỰC THI CHI TIẾT (STEP-BY-STEP IMPLEMENTATION)

---

### Giai đoạn 1: Schemas & Prompt cho Flashcard Module

#### Task 1.1: Tạo Schemas DTO (`apps/api/app/modules/flashcards/schemas.py`)
- **Mục tiêu:** Định nghĩa toàn bộ schema request/response cho việc trích xuất và lưu thẻ.
- **Chi tiết cài đặt:**
  * `ExtractionSourceType` Enum: `"quiz_attempt"`, `"chat_session"`.
  * `FlashcardExtractRequest`: `source_type`, `source_id: UUID`, `message_ids: list[UUID] | None`.
  * `ExtractedFlashcardItem`: `front_text`, `back_text`, `category` (`"term" | "concept" | "formula"`), `context_snippet`, `trigger_reason`.
  * `FlashcardExtractResponse`: `source_type`, `source_id`, `cards: list[ExtractedFlashcardItem]`, `total_extracted: int`, `message: str | None`.
  * `FlashcardItemCreate`: `front_text`, `back_text`, `page_number: int | None`.
  * `FlashcardBulkCreateRequest`: `deck_id: UUID`, `cards: list[FlashcardItemCreate]`.
  * `FlashcardResponse`: Schema trả về chi tiết thẻ sau khi lưu vào DB.

#### Task 1.2: Xây dựng System Prompt (`apps/api/app/modules/flashcards/prompt.py`)
- **Mục tiêu:** Thiết kế prompt chuyên sâu cho LLM để chuyển hóa câu hỏi trắc nghiệm sai thành cặp Flashcard bản chất.
- **Nguyên tắc Prompt:**
  * Không copy nguyên văn câu hỏi trắc nghiệm A/B/C/D vào mặt trước.
  * Phân tích tại sao học sinh chọn phương án sai để xác định "khái niệm hoặc công thức bị nhầm lẫn".
  * Mặt trước (`front_text`): Câu hỏi gợi mở khái niệm, thuật ngữ hoặc tên công thức cần nhớ.
  * Mặt sau (`back_text`): Định nghĩa cô đọng, bản chất quy tắc đúng hoặc công thức chuẩn (hỗ trợ LaTeX $\LaTeX$).

---

### Giai đoạn 2: Tầng Nghiệp Vụ Trích Xuất (Service & Strategy)

#### Task 2.1: Triển khai `QuizExtractionStrategy` (`apps/api/app/modules/flashcards/service.py`)
- **Mục tiêu:** Truy vấn lượt làm quiz, kiểm tra quyền và tạo ngữ cảnh cho LLM.
- **Các bước:**
  1. Truy vấn `QuizAttempt` theo `source_id` kèm `options` và `questions` thông qua `selectinload`.
  2. **IDOR Check:** Nếu `attempt.user_id != user_id`, ném `HTTPException(status_code=404, detail="Quiz attempt not found")`.
  3. **Trạng thái Check:** Nếu `attempt.status != "completed"`, ném `HTTPException(status_code=400, detail="Vui lòng hoàn thành bài quiz trước khi trích xuất flashcard.")`.
  4. Lọc danh sách câu trả lời sai: `wrong_answers = [a for a in attempt.answers if not a.is_correct]`.
  5. **Fast-path:** Nếu `len(wrong_answers) == 0`, lập tức trả về `FlashcardExtractResponse(cards=[], total_extracted=0, message="Tuyệt vời! Bạn không làm sai câu nào.")` mà không gọi LLM.
  6. Nếu `len(wrong_answers) > 10`: Cắt lấy tối đa 10 câu sai đầu tiên.
  7. Gọi Gemini Client với `response_schema=list[ExtractedFlashcardItem]`.

#### Task 2.2: Triển khai Bulk Save (`FlashcardService.bulk_create_flashcards`)
- **Mục tiêu:** Lưu danh sách thẻ vào CSDL một cách an toàn và nguyên tử (atomic transaction).
- **Các bước:**
  1. Kiểm tra sự tồn tại của `FlashcardDeck` theo `deck_id` và xác thực quyền sở hữu `deck.user_id == user_id`.
  2. Tạo danh sách các đối tượng `Flashcard` với giá trị mặc định:
     * `repetition_number = 0`
     * `easiness_factor = 2.5`
     * `interval_days = 0`
     * `next_review_date = datetime.now(timezone.utc).date()`
  3. Thêm vào session và `await db.commit()`.

---

### Giai đoạn 3: Tầng Giao Tiếp API (Router & App Integration)

#### Task 3.1: Xây dựng Router (`apps/api/app/modules/flashcards/router.py`)
- **Mục tiêu:** Cung cấp các API RESTful cho frontend.
- **Endpoints:**
  * `POST /api/v1/flashcards/extract` -> Gọi `flashcard_service.extract_flashcards(db, current_user.id, request)`.
  * `POST /api/v1/flashcards/bulk` -> Gọi `flashcard_service.bulk_create_flashcards(db, current_user.id, request)`.
- **Bảo mật:** Sử dụng dependency `get_current_user` và `get_db`.

#### Task 3.2: Đăng ký Router vào hệ thống
- Chỉnh sửa `apps/api/app/modules/flashcards/__init__.py`: Export `flashcards_router`.
- Chỉnh sửa `apps/api/app/main.py`: Thêm `app.include_router(flashcards_router, prefix="/api/v1")`.

---

### Giai đoạn 4: Tích hợp Gợi Ý Thời Gian Thực Cho Chat AI Tutor

#### Task 4.1: Cập nhật System Prompt AI Tutor (`apps/api/app/modules/chat/prompt_composer.py`)
- Bổ sung quy tắc vào prompt của AI Tutor:
  * Khi phát hiện học viên trả lời sai hoặc biểu lộ hiểu lầm nghiêm trọng về mặt lý thuyết/công thức:
  * Bên cạnh câu phản hồi sư phạm, hãy xuất một khối ẩn theo định dạng:
    ```
    <!--FLASHCARD_SUGGESTION:{"front_text": "...", "back_text": "...", "category": "term|concept|formula", "trigger_reason": "..."}-->
    ```

#### Task 4.2: Cập nhật Stream Filter & SSE Event (`apps/api/app/modules/chat/service.py`)
- Mở rộng `MarkerStreamFilter` để nhận diện tag `<!--FLASHCARD_SUGGESTION:...-->`.
- Khi phát hiện tag:
  1. Loại bỏ tag này khỏi text stream hiển thị cho người dùng (để giữ tin nhắn sạch sẽ).
  2. Phát một SSE event riêng: `event: flashcard_suggestion`.
  3. Parse JSON và lưu vào trường `metadata` của bản ghi `ChatMessage` trước khi commit vào DB.

---

### Giai đoạn 5: Viết Kiểm Thử Tự Động (Automated Testing)

#### Task 5.1: Kiểm thử Flashcard Extraction (`apps/api/tests/test_flashcard_extraction.py`)
1. `test_extract_quiz_no_wrong_answers_returns_empty`:
   * Tạo bài thi 100% đúng -> Gọi API extract -> Kỳ vọng `cards == []`, mock LLM không bị gọi.
2. `test_extract_quiz_idor_defense`:
   * User B gọi trích xuất bài thi của User A -> Kỳ vọng `404 Not Found`.
3. `test_extract_quiz_incomplete_status`:
   * Bài thi có trạng thái `"in_progress"` -> Kỳ vọng `400 Bad Request`.
4. `test_extract_quiz_success_with_mock_llm`:
   * Mock Gemini trả về danh sách 2 thẻ -> Gọi API -> Kỳ vọng `200 OK` với dữ liệu chuẩn.
5. `test_bulk_save_flashcards`:
   * Lưu 2 thẻ vào deck của user -> Kiểm tra DB đảm bảo tạo đúng bản ghi với SM-2 defaults.

#### Task 5.2: Kiểm thử Chat Misconception Suggestion (`apps/api/tests/test_chat_flashcard_inline.py`)
1. `test_marker_stream_filter_extracts_flashcard_suggestion`:
   * Đưa chunk chứa `<!--FLASHCARD_SUGGESTION:...-->` qua filter -> Kiểm tra text đầu ra sạch và payload gợi ý được bắt chính xác.
2. `test_chat_message_metadata_saves_suggestion`:
   * Kiểm tra bản ghi `ChatMessage` trong DB có trường `metadata["flashcard_suggestion"]`.

---

## 4. LỆNH XÁC MINH & KIỂM TRA CHẤT LƯỢNG (VERIFICATION COMMANDS)

Sau khi hoàn thành triển khai, chạy chuỗi lệnh sau để xác nhận:

```bash
# 1. Kiểm tra Lint & Type Check
ruff check apps/api/app/modules/flashcards apps/api/app/modules/chat
ruff format --check apps/api/app/modules/flashcards

# 2. Chạy toàn bộ Test Suite mới
pytest apps/api/tests/test_flashcard_extraction.py -v
pytest apps/api/tests/test_chat_flashcard_inline.py -v

# 3. Chạy Regression Tests cho Chat & Quizzes
pytest apps/api/tests/test_chat_*.py -v
```
