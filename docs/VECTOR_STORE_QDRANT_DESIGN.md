# TÀI LIỆU THIẾT KẾ: CẤU HÌNH LLAMAINDEX VÀ QDRANT COLLECTION `learning_chunks`

## 1. TỔNG QUAN VÀ MỤC TIÊU (OVERVIEW)
Tài liệu này xác định chi tiết thiết kế kỹ thuật cho việc tích hợp LlamaIndex với Vector Database Qdrant (collection `learning_chunks`), thực hiện chunking tài liệu theo trang và lưu trữ vector cùng metadata (`doc_id`, `page_number`, v.v.) phục vụ RAG và AI Socratic Chatbot.

---

## 2. HIỂU BIẾT VÀ PHẠM VI (UNDERSTANDING SUMMARY)
* **Những gì được xây dựng:**
  * `DocumentVectorService` trong `app/modules/documents/vector_service.py`.
  * Cấu hình LlamaIndex `QdrantVectorStore` và `VectorStoreIndex`.
  * Khởi tạo và thiết lập Collection `learning_chunks` (vector 3072-dim, Cosine distance) và Payload Indexes (`doc_id`, `page_number`).
  * Embedding model: Google `gemini-embedding-001` (3072-dim).
  * Per-page chunking với `SentenceSplitter(chunk_size=768, chunk_overlap=100)`.
  * Đồng bộ luồng trạng thái Ingestion: `uploading` -> `parsing` -> `indexing` -> `ready` (hoặc `failed`).
  * Giao diện Retriever hỗ trợ lọc metadata chính xác theo `doc_id` và `page_number`.
  * Dọn dẹp dữ liệu (xóa points theo `doc_id`) khi re-index hoặc khi xóa document.
* **Mục đích:** Cung cấp hạ tầng retrieval chính xác 100% theo trang tài liệu cho Split-view Workspace, AI Socratic Tutor, Bloom Quiz Generator và Flashcards.
* **Non-goals:** Chưa triển khai prompt Socratic hay SSE Chat Streaming trong phạm vi task này.

---

## 3. GIẢ ĐỊNH & YÊU CẦU PHI CHỨC NĂNG (ASSUMPTIONS & NFRs)
1. **Qdrant Instance:** Chạy cục bộ tại `http://localhost:6333` (HTTP) / port `6334` (gRPC).
2. **Quy mô:** Mỗi tài liệu thông thường từ 10 - 200 trang (~50 - 1.000 chunks).
3. **Hiệu năng:** Thời gian truy vấn tìm kiếm vector có metadata filter < 50ms.
4. **Idempotency:** Collection và payload index tự động kiểm tra và tạo nếu chưa có; nạp lại tài liệu sẽ xóa vector cũ trước khi thêm mới.

---

## 4. NHẬT KÝ QUYẾT ĐỊNH (DECISION LOG)

| STT | Quyết định | Các phương án đã cân nhắc | Lý do lựa chọn |
| :--- | :--- | :--- | :--- |
| **D1** | **Kiến trúc module** | Option 1: Module hóa `DocumentVectorService`<br>Option 2: Nhúng vào `IngestionService`<br>Option 3: Generic AI Engine | Đảm bảo nguyên lý Single Responsibility (SRP), dễ kiểm thử độc lập, sẵn sàng tái sử dụng cho RAG Chat mà không vi phạm YAGNI. |
| **D2** | **Chiến lược Chunking** | Chunking theo trang (Per-page) vs Chunking toàn văn bản | Chunking theo từng trang bảo đảm metadata `page_number` chính xác 100%, không bị lẫn trang khi cắt ranh giới. |
| **D3** | **Vòng đời trạng thái (Status Flow)** | Giữ nguyên trạng thái `parsed` vs Cập nhật `indexing` -> `ready` | Tận dụng `DocumentStatus` sẵn có trong schema (`indexing` khi bắt đầu đưa vào Qdrant, `ready` khi hoàn tất) giúp UI hiển thị tiến độ trực quan. |
| **D4** | **Tính toàn vẹn dữ liệu (Lifecycle)** | Tự động dọn dẹp vs Append-only | Tự động xóa vector cũ theo `doc_id` trước khi re-index và móc vào `delete_document` để bảo đảm tính lũy đẳng (idempotent). |
| **D5** | **Số chiều Vector (Dimensions)** | Giữ 768 qua MRL output_dimensionality vs Nâng Collection lên 3072 | Lựa chọn nâng Collection lên 3072 theo `gemini-embedding-001` gốc để khai thác trọn vẹn biểu diễn ngữ nghĩa cao nhất của mô hình. Tự động kiểm tra và recreate collection nếu phát hiện lệch kích thước. |

---

## 5. THIẾT KẾ CHI TIẾT (DETAILED DESIGN)

### 5.1. Sơ đồ Kiến trúc & Luồng dữ liệu (Data Flow)

```
[IngestionService: Hoàn thành Vision Parsing]
                     │
                     ▼
  DocumentVectorService.index_document_pages(doc_id, pages_meta)
                     │
                     ├─► [1] Dọn dẹp: delete_document_vectors(doc_id)
                     │
                     ├─► [2] Lặp qua từng trang (page_meta in pages_meta):
                     │         ├─ Bỏ qua nếu trang trống (char_count == 0)
                     │         ├─ Đọc markdown của page_{page_num}.md
                     │         ├─ Dùng SentenceSplitter sinh danh sách TextNode
                     │         └─ Gán Metadata chuẩn hóa cho từng TextNode
                     │
                     ├─► [3] Đưa danh sách Nodes vào VectorStoreIndex:
                     │         ├─ GeminiEmbedding sinh vector 768-dim cho từng node
                     │         └─ QdrantVectorStore lưu trữ vector + payload vào Qdrant
                     │
                     ▼
[Cập nhật DocumentMetadata: status = "ready"]
```

### 5.2. Cấu trúc Payload trong Qdrant Collection `learning_chunks`

```json
{
  "doc_id": "c3b8f1a2-9b21-4d33-bc89-123456789abc",
  "page_number": 14,
  "chunk_index": 3,
  "has_formula": true,
  "has_image": false,
  "text": "Định lý 2.1: Cho hàm số f(x)... Công thức: $$f'(x) = \\lim_{h \\to 0} \\frac{f(x+h) - f(x)}{h}$$"
}
```

### 5.3. Giao diện Truy vấn (Retriever Interface)

```python
def get_retriever(
    self,
    doc_id: str,
    page_number: int | None = None,
    similarity_top_k: int = 5,
) -> VectorIndexRetriever:
    """Trả về retriever LlamaIndex với metadata filter theo doc_id và tùy chọn page_number."""
```

### 5.4. Xử lý lỗi & Trường hợp biên (Error Handling & Edge Cases)
1. **Qdrant Unreachable:** Cập nhật `metadata.status = "failed"`, `error_message = "Qdrant vector indexing failed: <reason>"`. Markdown gốc vẫn được giữ nguyên để re-index sau.
2. **Rate Limit API (429):** Tích hợp retry with backoff khi tạo embedding.
3. **Trang trống:** Không gọi embedding vô ích, bỏ qua an toàn.
4. **Xóa Document:** Hàm `delete_document(doc_id)` gọi xóa đồng thời file trên đĩa và điểm vector trên Qdrant.

---

## 6. CHIẾN LƯỢC KIỂM THỬ (TESTING STRATEGY)
* **Unit Tests (`tests/test_vector_service.py`):**
  * Mock `QdrantClient` và `GeminiEmbedding` kiểm thử:
    * Khởi tạo collection & payload indexes.
    * Tạo `TextNode` với đúng metadata (`doc_id`, `page_number`, `chunk_index`).
    * Cấu hình bộ lọc `MetadataFilters` trong retriever.
    * Gọi dọn dẹp điểm vector khi tài liệu bị xóa.
* **Integration Tests:**
  * Chạy thực tế với local Qdrant container để xác nhận vector 768-dim và Cosine similarity search.
