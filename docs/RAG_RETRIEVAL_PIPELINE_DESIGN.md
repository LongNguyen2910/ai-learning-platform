# TÀI LIỆU THIẾT KẾ KỸ THUẬT: PIPELINE TRUY VẤN RAG QUA LLAMAINDE X VÀ QDRANT

## 1. TỔNG QUAN & MỤC TIÊU (OVERVIEW)
Tài liệu này xác định chi tiết thiết kế kỹ thuật cho **Pipeline truy vấn RAG qua LlamaIndex** (Sprint 2 - AI Lead: Long). Hệ thống chịu trách nhiệm truy xuất các đoạn văn bản (chunks) liên quan nhất từ Vector Database Qdrant (collection `learning_chunks`) dựa theo ngữ nghĩa câu hỏi và bộ lọc metadata (`doc_id`, `page_number`), làm nền tảng tri thức chuẩn xác cho AI Socratic Tutor, Bloom Quiz Generator và Flashcard Deck Generator.

---

## 2. HIỂU BIẾT & PHẠM VI (UNDERSTANDING SUMMARY)
* **Những gì được xây dựng:**
  * `ChatRAGService` trong `apps/api/app/modules/chat/service.py` quản lý pipeline truy vấn vector LlamaIndex.
  * Pydantic Schemas trong `apps/api/app/modules/chat/schemas.py` (`RAGChunkSearchRequest`, `RetrievedChunkDTO`, `RAGChunkSearchResponse`).
  * Endpoint REST API `POST /api/v1/chat/documents/{document_id}/retrieval` trong `apps/api/app/modules/chat/router.py`.
  * Bộ lọc kép: Pre-filter tại Qdrant (`doc_id` bắt buộc, `page_number` tùy chọn) và Post-filter (`score >= score_threshold`).
  * Định dạng trích dẫn chuẩn hóa `[[Trang X]]` cho từng chunk trả về.
  * Bộ kiểm thử toàn diện `apps/api/tests/test_chat_rag_retrieval.py`.
* **Mục đích:** Cung cấp tầng Retrieval độc lập, có thể đo lường và đánh giá chất lượng (Recall, Precision, Latency) trước khi tích hợp vào LLM Generation.
* **Non-goals:** Chưa triển khai gọi Gemini LLM sinh câu trả lời tự nhiên; chưa tích hợp SSE Chat streaming và Socratic 3 tầng (thuộc các task kế tiếp của Sprint 2).

---

## 3. GIẢ ĐỊNH & YÊU CẦU PHI CHỨC NĂNG (ASSUMPTIONS & NFRs)
1. **Mô hình Embedding:** Google `gemini-embedding-001` (3072 chiều) đồng bộ với collection `learning_chunks`.
2. **Hiệu năng:** Thời gian phản hồi tầng Retrieval $< 350\text{ms}$ (bao gồm cả latency gọi Gemini Embedding API và truy vấn vector từ Qdrant).
3. **Bảo mật & Phân quyền:** Chỉ cho phép người dùng truy vấn tài liệu mà họ sở hữu (`doc.user_id == current_user.id`), hoặc tài liệu công khai (`doc.is_public == True`), hoặc người dùng có vai trò `admin`.
4. **Trạng thái tài liệu:** Tài liệu phải ở trạng thái `status = 'ready'` mới cho phép thực hiện truy vấn.
5. **Chịu lỗi (Resilience):** Khi không có chunk nào đạt ngưỡng `score_threshold`, hệ thống trả về danh sách rỗng `[]` thay vì đưa dữ liệu không liên quan vào prompt. Khi Qdrant gián đoạn, trả về HTTP 503 với thông báo rõ ràng.

---

## 4. NHẬT KÝ QUYẾT ĐỊNH (DECISION LOG)

| STT | Vấn đề | Quyết định đã chọn | Các phương án đã cân nhắc | Lý do lựa chọn |
| :--- | :--- | :--- | :--- | :--- |
| **D1** | **Phạm vi task** | Tập trung 100% vào tầng Retrieval chuyên biệt | Option 1: Chỉ Retrieval<br>Option 2: Ghép cả LLM Generation<br>Option 3: Gộp chung vào Ingestion | Tuân thủ nguyên lý RAG: *"Retrieval quality > Generation quality"*, tách rời để kiểm thử và tối ưu độc lập. |
| **D2** | **Bộ lọc & Ngưỡng điểm** | Pre-filter metadata + Post-filter theo `score_threshold` | Option 1: Top-K cố định không lọc điểm<br>Option 2: Pre-filter + Score threshold | Tránh hiện tượng Context Pollution (nhiễm bẩn ngữ cảnh) gây ảo giác cho LLM khi câu hỏi không có trong sách. |
| **D3** | **Tổ chức Module** | Đặt tại `app/modules/chat/` (`service.py`, `schemas.py`, `router.py`) | Option 1: Đặt tại `app/ai_engine/`<br>Option 2: Đặt tại `app/modules/documents/`<br>Option 3: Đặt tại `app/modules/chat/` | Tuân thủ tuyệt đối cấu trúc dự án chuẩn tại `docs/PROJECT_STRUCTURE.md` (Module `chat` phụ trách LlamaIndex RAG & SSE Streaming). |
| **D4** | **UX Lọc số trang (`page_number`)** | Mặc định `None` (quét toàn bộ tài liệu); tự động truyền từ `workspace-store` nếu người dùng chọn hỏi trang | Option 1: Bắt buộc chọn trang<br>Option 2: Tự động ép theo trang đang mở<br>Option 3: Tùy chọn (Optional) | Người dùng phần lớn hỏi kiến thức tổng thể; không ép người dùng thao tác thừa nhưng vẫn hỗ trợ hỏi trang sâu khi cần. |

---

## 5. THIẾT KẾ CHI TIẾT (DETAILED DESIGN)

### 5.1. Sơ đồ Kiến trúc & Luồng dữ liệu (Data Flow)

```
Client (Frontend Split-View / API Consumer)
                    │
                    ▼
[POST /api/v1/chat/documents/{document_id}/retrieval]
                    │
                    ├─► [1] Auth & Ownership Check (JWT + PostgreSQL Document Query)
                    │         └─ Validate doc.status == "ready"
                    │
                    ▼
[ChatRAGService.retrieve_relevant_chunks]
                    │
                    ├─► [2] Gọi DocumentVectorService.get_retriever(doc_id, page_number, top_k)
                    │         └─ QdrantVectorStore Filter: { doc_id: "...", page_number: X (optional) }
                    │
                    ├─► [3] GeminiEmbedding.get_text_embedding(query_text) -> Vector 3072-dim
                    │
                    ├─► [4] Qdrant Similarity Search (Cosine distance) -> List[NodeWithScore]
                    │
                    ├─► [5] Post-filter: Giữ lại nodes có score >= score_threshold (mặc định 0.5)
                    │
                    ▼
[DTO Formatter: Chuyển đổi thành RetrievedChunkDTO]
  - chunk_id: Node ID
  - page_number, chunk_index, has_formula, has_image
  - citation_tag: "[[Trang {page_number}]]"
  - score: float
  - content: Markdown text
                    │
                    ▼
HTTP Response: 200 OK (RAGChunkSearchResponse)
```

### 5.2. Cấu trúc Pydantic Schemas (`apps/api/app/modules/chat/schemas.py`)

```python
from pydantic import BaseModel, Field

class RAGChunkSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000, description="Nội dung câu hỏi cần tra cứu")
    page_number: int | None = Field(default=None, ge=1, description="Giới hạn số trang (tùy chọn)")
    similarity_top_k: int = Field(default=5, ge=1, le=20, description="Số lượng chunk tối đa cần lấy")
    score_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Ngưỡng điểm tương đồng tối thiểu")

class RetrievedChunkDTO(BaseModel):
    chunk_id: str
    page_number: int
    chunk_index: int
    score: float
    content: str
    has_formula: bool
    has_image: bool
    citation_tag: str  # Ví dụ: "[[Trang 14]]"

class RAGChunkSearchResponse(BaseModel):
    document_id: str
    query: str
    total_retrieved: int
    chunks: list[RetrievedChunkDTO]
```

### 5.3. Giao diện Service (`apps/api/app/modules/chat/service.py`)

```python
class ChatRAGService:
    def __init__(self, vector_service: DocumentVectorService | None = None) -> None:
        self.vector_service = vector_service or document_vector_service

    async def retrieve_relevant_chunks(
        self,
        document_id: str,
        query: str,
        page_number: int | None = None,
        similarity_top_k: int = 5,
        score_threshold: float = 0.5,
    ) -> list[RetrievedChunkDTO]:
        """Thực thi truy vấn tìm kiếm chunks liên quan từ Qdrant qua LlamaIndex."""
        retriever = self.vector_service.get_retriever(
            document_id=document_id,
            page_number=page_number,
            similarity_top_k=similarity_top_k,
        )
        
        # Async retrieval qua LlamaIndex
        nodes_with_score = await retriever.aretrieve(query)
        
        results: list[RetrievedChunkDTO] = []
        for item in nodes_with_score:
            score = float(item.score or 0.0)
            if score < score_threshold:
                continue
            
            meta = item.node.metadata
            page_num = meta.get("page_number", 1)
            results.append(
                RetrievedChunkDTO(
                    chunk_id=item.node.node_id,
                    page_number=page_num,
                    chunk_index=meta.get("chunk_index", 0),
                    score=round(score, 4),
                    content=item.node.get_content(),
                    has_formula=meta.get("has_formula", False),
                    has_image=meta.get("has_image", False),
                    citation_tag=f"[[Trang {page_num}]]",
                )
            )
        return results
```

### 5.4. Xử lý Lỗi & Trường hợp biên (Error Handling & Edge Cases)
1. **Tài liệu chưa sẵn sàng:** Trả về HTTP `400 Bad Request` nếu `doc.status != "ready"`.
2. **Qdrant Timeout / Mất kết nối:** Bắt ngoại lệ và ném `HTTPException(status_code=503, detail="Dịch vụ vector search tạm thời gián đoạn")`.
3. **Không tìm thấy kết quả:** Trả về `total_retrieved: 0`, `chunks: []` với mã `200 OK`.
4. **Không đủ thẩm quyền:** Trả về HTTP `403 Forbidden` nếu người dùng không sở hữu tài liệu và tài liệu không public.

### 5.5. Chiến lược Kiểm thử (Testing Strategy)
Tạo file kiểm thử tự động tại `apps/api/tests/test_chat_rag_retrieval.py`:
- `test_retrieve_chunks_by_doc_id`: Truy vấn ra đúng nội dung và metadata theo `doc_id`.
- `test_retrieve_chunks_with_page_filter`: Lọc đúng số trang khi có tham số `page_number`.
- `test_score_threshold_filtering`: Loại bỏ an toàn các chunks có điểm thấp hơn ngưỡng.
- `test_retrieval_endpoint_auth_and_ownership`: Kiểm tra phân quyền truy cập endpoint REST API.
- `test_retrieval_endpoint_not_ready_document`: Kiểm tra chặn tài liệu chưa parse xong.
