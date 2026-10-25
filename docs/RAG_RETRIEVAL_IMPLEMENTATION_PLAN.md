# KẾ HOẠCH TRIỂN KHAI: PIPELINE TRUY VẤN RAG QUA LLAMAINDE X & QDRANT

> **Tài liệu tham chiếu:** [docs/RAG_RETRIEVAL_PIPELINE_DESIGN.md](RAG_RETRIEVAL_PIPELINE_DESIGN.md)  
> **Người thực hiện:** Long (AI Lead)  
> **Sprint:** Sprint 2 (Tuần 3–4)  
> **Trạng thái:** Sẵn sàng thực thi (Ready for Implementation)

---

## 1. MỤC TIÊU CỦA ĐỢT TRIỂN KHAI
Xây dựng hoàn chỉnh tầng dịch vụ **RAG Retrieval** (Truy xuất ngữ nghĩa) sử dụng LlamaIndex và Qdrant collection `learning_chunks`:
1. Cho phép tìm kiếm `top-k` chunks liên quan nhất từ câu hỏi người dùng theo `doc_id`.
2. Hỗ trợ tùy chọn lọc sâu theo số trang (`page_number`) khi người học muốn hỏi trong phạm vi trang hiện tại trên màn hình Split-View Workspace.
3. Áp dụng ngưỡng điểm tương đồng tối thiểu (`score_threshold`, mặc định $0.5$) để loại bỏ chunk rác, tránh hiện tượng ảo giác (hallucination) cho AI Socratic Tutor.
4. Đóng gói kết quả dưới dạng DTO chuẩn hóa, tự động gắn thẻ trích dẫn số trang `[[Trang X]]`.
5. Cung cấp API endpoint nội bộ `POST /api/v1/chat/documents/{document_id}/retrieval` để phục vụ kiểm thử độc lập và kết nối Frontend.

---

## 2. MA TRẬN FILES TÁC ĐỘNG

| File | Hành động | Mục đích |
| :--- | :---: | :--- |
| `apps/api/app/modules/chat/schemas.py` | **Tạo mới** | Pydantic Schemas: Request, Chunk DTO và Response |
| `apps/api/app/modules/chat/service.py` | **Tạo mới** | Lớp nghiệp vụ `ChatRAGService` bọc LlamaIndex retriever |
| `apps/api/app/modules/chat/router.py` | **Tạo mới** | APIRouter `/api/v1/chat` chứa endpoint `/documents/{doc_id}/retrieval` |
| `apps/api/app/modules/chat/__init__.py` | **Chỉnh sửa** | Export `chat_router` và `chat_rag_service` |
| `apps/api/app/main.py` | **Chỉnh sửa** | Đăng ký `chat_router` vào ứng dụng FastAPI |
| `apps/api/tests/test_chat_rag_retrieval.py` | **Tạo mới** | Bộ kiểm thử Unit & Integration Tests tự động |

---

## 3. CÁC BƯỚC THỰC THI CHI TIẾT (STEP-BY-STEP IMPLEMENTATION)

### Giai đoạn 1: Xây dựng Schemas (`apps/api/app/modules/chat/schemas.py`)
- [ ] **1.1.** Tạo file `apps/api/app/modules/chat/schemas.py`.
- [ ] **1.2.** Cài đặt `RAGChunkSearchRequest`:
  - `query: str` (min_length=2, max_length=1000).
  - `page_number: int | None = None` (ge=1).
  - `similarity_top_k: int = 5` (ge=1, le=20).
  - `score_threshold: float = 0.5` (ge=0.0, le=1.0).
- [ ] **1.3.** Cài đặt `RetrievedChunkDTO`:
  - `chunk_id: str`
  - `page_number: int`
  - `chunk_index: int`
  - `score: float`
  - `content: str`
  - `has_formula: bool`
  - `has_image: bool`
  - `citation_tag: str` (Định dạng: `[[Trang {page_number}]]`).
- [ ] **1.4.** Cài đặt `RAGChunkSearchResponse`:
  - `document_id: str`
  - `query: str`
  - `total_retrieved: int`
  - `chunks: list[RetrievedChunkDTO]`

---

### Giai đoạn 2: Xây dựng Core Service (`apps/api/app/modules/chat/service.py`)
- [ ] **2.1.** Tạo file `apps/api/app/modules/chat/service.py`.
- [ ] **2.2.** Khởi tạo class `ChatRAGService`:
  ```python
  class ChatRAGService:
      def __init__(self, vector_service: DocumentVectorService | None = None) -> None:
          self.vector_service = vector_service or document_vector_service
  ```
- [ ] **2.3.** Viết phương thức bất đồng bộ `async def retrieve_relevant_chunks`:
  ```python
  async def retrieve_relevant_chunks(
      self,
      document_id: str,
      query: str,
      page_number: int | None = None,
      similarity_top_k: int = 5,
      score_threshold: float = 0.5,
  ) -> list[RetrievedChunkDTO]:
  ```
- [ ] **2.4.** Thực hiện gọi:
  - `retriever = self.vector_service.get_retriever(document_id=document_id, page_number=page_number, similarity_top_k=similarity_top_k)`
  - `nodes_with_score = await retriever.aretrieve(query)`
- [ ] **2.5.** Lọc bỏ các nodes có `score < score_threshold`.
- [ ] **2.6.** Chuyển đổi dữ liệu sang `RetrievedChunkDTO` với `citation_tag = f"[[Trang {page_num}]]"`.
- [ ] **2.7.** Khởi tạo singleton instance: `chat_rag_service = ChatRAGService()`.

---

### Giai đoạn 3: Xây dựng API Endpoint & Đăng ký Router
- [ ] **3.1.** Tạo file `apps/api/app/modules/chat/router.py`:
  - Khởi tạo router: `router = APIRouter(prefix="/chat", tags=["Chat RAG"])`.
- [ ] **3.2.** Viết endpoint `POST /documents/{document_id}/retrieval`:
  - Nhận `document_id: str` qua path parameter.
  - Nhận `payload: RAGChunkSearchRequest` qua request body.
  - Kiểm tra sự tồn tại của document qua `ingestion_service.load_metadata(document_id)`. Nếu `None` $\rightarrow$ ném `HTTPException(404, "Document not found")`.
  - Kiểm tra trạng thái document: Nếu `metadata.status != "ready"` $\rightarrow$ ném `HTTPException(400, f"Document is not ready for retrieval (status: {metadata.status})")`.
  - Gọi `await chat_rag_service.retrieve_relevant_chunks(...)`.
  - Trả về `RAGChunkSearchResponse`.
- [ ] **3.3.** Cập nhật `apps/api/app/modules/chat/__init__.py`:
  - Export `chat_router = router`.
  - Export `chat_rag_service`.
- [ ] **3.4.** Cập nhật `apps/api/app/main.py`:
  - Import `chat_router` từ `app.modules.chat`.
  - Thêm dòng: `app.include_router(chat_router, prefix="/api/v1")`.

---

### Giai đoạn 4: Viết Bộ Test Suites (`apps/api/tests/test_chat_rag_retrieval.py`)
- [ ] **4.1.** Tạo file `apps/api/tests/test_chat_rag_retrieval.py`.
- [ ] **4.2.** Thiết lập Fixtures:
  - `mock_embed_model`: `MockEmbedding(embed_dim=3072)`.
  - `memory_qdrant_client`: `QdrantClient(":memory:")`.
  - `vector_service`: `DocumentVectorService` trỏ vào bộ nhớ giả lập.
  - `chat_rag_service`: `ChatRAGService(vector_service=vector_service)`.
- [ ] **4.3.** Viết Unit Tests cho `ChatRAGService`:
  - `test_retrieve_chunks_by_doc_id`: Nạp 2 trang dữ liệu, truy vấn từ khóa, xác nhận trả về đúng chunks kèm thẻ trích dẫn `[[Trang 1]]`.
  - `test_retrieve_chunks_with_page_number_filter`: Chỉ định `page_number=2`, xác nhận chỉ nhận được chunks của trang 2.
  - `test_retrieve_chunks_score_threshold`: Đặt `score_threshold=0.99`, xác nhận lọc sạch các chunks điểm thấp và trả về mảng rỗng `[]`.
- [ ] **4.4.** Viết Integration Tests cho FastAPI Endpoint:
  - `test_endpoint_retrieval_success`: Gọi qua `httpx.AsyncClient`, nhận HTTP 200 và cấu trúc JSON chuẩn.
  - `test_endpoint_document_not_ready`: Tạo metadata có `status = "indexing"`, gọi API, xác nhận nhận HTTP 400.
  - `test_endpoint_document_not_found`: Gọi với ID ngẫu nhiên, xác nhận nhận HTTP 404.

---

### Giai đoạn 5: Xác nhận Tiêu chí Nghiệm thu (Definition of Done - DoD)
- [ ] **5.1.** Chạy kiểm thử độc lập:
  ```bash
  cd apps/api && uv run pytest tests/test_chat_rag_retrieval.py -v
  ```
- [ ] **5.2.** Chạy toàn bộ test suite để đảm bảo không có regression:
  ```bash
  cd apps/api && uv run pytest
  ```
- [ ] **5.3.** Kiểm tra code formatting & linting:
  ```bash
  cd apps/api && uv run ruff check . && uv run ruff format --check .
  ```
- [ ] **5.4.** Đảm bảo 100% tests vượt qua và không còn cảnh báo lỗi.
