# TÀI LIỆU KỸ THUẬT: ĐỀ XUẤT CẢI TIẾN HẠ TẦNG RAG TRONG TƯƠNG LAI
## (RAG INFRASTRUCTURE OPTIMIZATION ROADMAP)

> **Dự án:** AI Learning Platform  
> **Người phụ trách:** Long (AI Lead)  
> **Mục đích:** Ghi nhận và thiết kế sẵn phương án kỹ thuật cho 2 cải tiến nâng cao: (1) Batching nạp tài liệu lớn và (2) Tầng Reranker / Hybrid Search nhằm đạt mục tiêu trích dẫn chính xác > 90% tại Sprint 4.  
> **Trạng thái:** Kế hoạch mở rộng (Future Roadmap - Sprint 3 & Sprint 4)

---

## 1. CẢI TIẾN 1: CHIA BATCH & XỬ LÝ CHỊU LỖI KHI INDEX TÀI LIỆU LỚN (BATCHING INGESTION)

### 1.1. Bối cảnh & Rủi ro hiện tại
* **Hiện trạng:** Trong `apps/api/app/modules/documents/vector_service.py`, hàm `index_document_pages` gom toàn bộ các đoạn văn bản của toàn bộ tài liệu vào danh sách `all_nodes` và gọi một lần duy nhất:
  ```python
  index.insert_nodes(all_nodes)
  ```
* **Rủi ro khi vào Production:** 
  * Đối với sách giáo trình đại học hoặc tài liệu chuyên ngành dài từ **50 đến 200+ trang**, số lượng chunks có thể lên tới **300 – 1.000 chunks**.
  * Việc gửi hàng trăm chunks cùng lúc sang Gemini Embedding API (`gemini-embedding-001`) dễ gây ra:
    1. Vượt quá giới hạn kích thước payload của một lượt gọi API.
    2. Chạm ngưỡng giới hạn tần suất (Rate Limit 429: *Resource Exhausted / RPM limit*).
    3. Nếu một node bị lỗi mạng giữa chừng, toàn bộ quá trình indexing bị gián đoạn và phải nạp lại từ đầu.

### 1.2. Giải pháp Kỹ thuật Đề xuất
1. **Chia nhỏ Chunk Batches:** Cắt danh sách `all_nodes` thành từng mẻ nhỏ (Batch size khuyến nghị: **32 – 64 chunks/batch**).
2. **Cơ chế Exponential Backoff with Jitter:** Tự động thử lại tối đa 3 lần khi gặp lỗi HTTP 429 hoặc kết nối mạng chập chờn.
3. **Theo dõi tiến độ nạp (Progress Tracking):** Log rõ tiến độ nạp (ví dụ: `Indexed batch 3/10 (nodes 96-128)`).

### 1.3. Bản mẫu mã nguồn nâng cấp (Code Blueprint)
```python
import asyncio
import logging

logger = logging.getLogger(__name__)

async def insert_nodes_in_batches(
    index: VectorStoreIndex,
    nodes: list[TextNode],
    batch_size: int = 32,
    max_retries: int = 3,
    delay_between_batches: float = 0.5,
) -> None:
    """Chia nhỏ danh sách nodes thành các batch và nạp an toàn kèm retry."""
    total_nodes = len(nodes)
    for start_idx in range(0, total_nodes, batch_size):
        end_idx = min(start_idx + batch_size, total_nodes)
        batch = nodes[start_idx:end_idx]
        
        batch_num = (start_idx // batch_size) + 1
        total_batches = (total_nodes + batch_size - 1) // batch_size
        logger.info(f"Nạp batch {batch_num}/{total_batches} ({len(batch)} nodes)...")
        
        # Retry with exponential backoff
        for attempt in range(1, max_retries + 1):
            try:
                # insert_nodes đồng bộ hoặc async tùy theo wrapper
                index.insert_nodes(batch)
                break
            except Exception as exc:
                if attempt == max_retries:
                    logger.error(f"Thất bại khi nạp batch {batch_num} sau {max_retries} lần thử: {exc}")
                    raise
                wait_time = (2 ** attempt) + 0.5
                logger.warning(f"Lỗi nạp batch {batch_num} (Lần thử {attempt}/{max_retries}). Đang đợi {wait_time}s... Lỗi: {exc}")
                await asyncio.sleep(wait_time)
        
        if delay_between_batches > 0:
            await asyncio.sleep(delay_between_batches)
```

---

## 2. CẢI TIẾN 2: TẦNG TÁI XẾP HẠNG (RERANKER) & HYBRID SEARCH (SPRINT 4)

### 2.1. Bối cảnh & Vấn đề của First-Stage Retrieval thuần túy
* **Vấn đề:** Tìm kiếm vector thuần túy bằng Cosine Distance (First-Stage Retrieval) chỉ tối ưu hóa cho độ bao phủ (Recall), nhưng chưa tối ưu cho độ chính xác cao nhất (Precision).
  * Mô hình embedding ánh xạ câu hỏi và đoạn văn độc lập vào không gian vector, có thể bỏ sót các mối quan hệ ngữ nghĩa phức tạp hoặc ưu tiên đoạn văn có từ ngữ tương đồng bề mặt nhưng không trả lời trực tiếp câu hỏi.
* **Mục tiêu Sprint 4 (Target DoD):** Đạt tỷ lệ trích dẫn trang RAG chính xác **> 90%** trên 10 bộ giáo trình thực tế (theo tiêu chí nghiệm thu tại `docs/DESIGN.md`).

### 2.2. Phương án Kiến trúc: Two-Stage Retrieval (Retrieve & Rerank)

```
[User Query]
     │
     ▼
[Stage 1: First-Pass Retrieval]
     ├─ Lấy tập ứng viên rộng hơn: top_k = 15 - 20 chunks từ Qdrant
     ▼
[Stage 2: Cross-Encoder Reranker]
     ├─ So sánh trực tiếp cặp (Query, Chunk) qua Cross-Attention
     ├─ Tính điểm liên quan sâu (Relevance Score)
     ├─ Sắp xếp lại và chọn top 3 - 5 chunks xuất sắc nhất
     ▼
[Gửi Context tinh nhuệ sang LLM Generation]
```

### 2.3. Các lựa chọn Công nghệ Reranker
1. **Lựa chọn A: Local Lightweight Reranker qua FlashRank (Khuyến nghị cho chi phí $0):**
   * Sử dụng thư viện `flashrank` (chạy ONNX runtime siêu nhẹ, tiêu tốn < 100MB RAM, không cần GPU).
   * Model: `ms-marco-MiniLM-L-12-v2`.
   * Độ trễ: $< 40\text{ms}$ cho 20 chunks.
   * Ưu điểm: Chạy 100% trong Docker backend, không phụ thuộc internet và không tốn chi phí API.
2. **Lựa chọn B: Cohere Rerank API (`rerank-v3.5`):**
   * Ưu điểm: Chất lượng hàng đầu thế giới, hỗ trợ đa ngôn ngữ và tiếng Việt rất tốt.
   * Nhược điểm: Phụ thuộc mạng ngoài và có chi phí API theo số lượt gọi.

### 2.4. Phương án Mở rộng Bổ sung: Hybrid Search (Dense + Sparse BM25)
* Đối với tài liệu kỹ thuật chứa nhiều ký hiệu toán học cụ thể (ví dụ: *"Định lý 2.1"*, *"Ma trận Jacobian"*, *"Phương trình Navier-Stokes"*):
  * Semantic Search đôi khi hiểu nhầm các thuật ngữ hiếm gặp.
  * **Giải pháp:** Kích hoạt tính năng **Sparse Vectors (BM25 / Splade)** trên Qdrant kết hợp cùng Dense Vectors hiện tại, dùng thuật toán **Reciprocal Rank Fusion (RRF)** để dung hòa cả tìm kiếm từ khóa chính xác và tìm kiếm ngữ nghĩa.

---

## 3. LỘ TRÌNH TRIỂN KHAI THEO SPRINT (ACTION PLAN)

| Hạng mục | Thời điểm | Điều kiện kích hoạt | Kết quả kỳ vọng |
| :--- | :---: | :--- | :--- |
| **Batching Ingestion** | **Sprint 3** | Khi bắt đầu thử nghiệm upload các tài liệu PDF thực tế dài > 50 trang | Quá trình indexing không bao giờ bị dính lỗi 429 hoặc tràn RAM. |
| **FlashRank / Cross-Encoder Reranker** | **Sprint 4** | Khi chạy bộ benchmark 10 tài liệu giáo trình để đo độ chính xác trích dẫn | Tỷ lệ trích dẫn đúng số trang tăng từ ~78–82% lên **> 92%**. |
| **Hybrid Search (Dense + BM25)** | **Sprint 4 (Dự phòng)** | Khi các câu hỏi tìm kiếm theo tên định lý/công thức chính xác bị trượt kết quả | Bắt chính xác 100% các từ khóa kỹ thuật hiếm. |
