# Thiết Kế Phân Quyền Tài Liệu & Bảo Mật Dữ Liệu RAG (Multi-tenant Document Security)

## 1. Tóm Tắt Yêu Cầu (Understanding Summary)
* **Mục tiêu:** Xây dựng cơ chế phân quyền và cô lập tài liệu cá nhân (Single-user Isolation) xuyên suốt từ REST API (upload, xem, tải, xóa) đến Qdrant Vector Database (RAG Retrieval).
* **Lý do tồn tại:** Ngăn chặn triệt để lỗ hổng IDOR (Insecure Direct Object Reference) và rò rỉ dữ liệu chéo (Data Leakage) giữa các người dùng khi AI tìm kiếm context để trả lời.
* **Đối tượng:** Học viên/người dùng nền tảng AI Learning Platform tải giáo trình và tài liệu cá nhân lên để phục vụ học tập.
* **Ràng buộc chính:**
  * Toàn bộ tài liệu và vector chunks thuộc quyền sở hữu riêng tư 100% của người tải lên.
  * Khi truy cập hoặc thao tác vào tài liệu không thuộc quyền sở hữu của mình, hệ thống trả về **`404 Not Found`** để che giấu hoàn toàn sự tồn tại của tài liệu.
  * Khi RAG retrieval trên Qdrant, bắt buộc dùng **Metadata Pre-filter** với `user_id`.
* **Mục tiêu ngoài phạm vi (Non-goals):**
  * Tạm thời chưa kích hoạt tính năng chia sẻ công khai (`is_public = False` cho mọi trường hợp).
  * Chưa hỗ trợ phân quyền theo nhóm, lớp học hoặc tổ chức.

---

## 2. Các Giả Định Kỹ Thuật (Assumptions)
* Mọi API tương tác với documents (upload, list, get content, render page image, RAG chat, delete) đều bắt buộc gửi kèm Bearer Token hợp lệ.
* Tận dụng index sẵn có trong Postgres `idx_documents_user_id` để query `WHERE id = :doc_id AND user_id = :user_id`, thời gian kiểm tra quyền < 5ms.
* Qdrant được cấu hình Payload Index `KEYWORD` trên trường `user_id` để đảm bảo tốc độ lọc không bị suy giảm khi khối lượng vector tăng lên.

---

## 3. Decision Log (Nhật Ký Quyết Định)

| Quyết định | Các phương án đã cân nhắc | Lý do lựa chọn |
| :--- | :--- | :--- |
| **Cơ chế phân quyền** | 1. FastAPI Dependency Guard (Chọn)<br>2. Manual Service Check<br>3. Postgres RLS + Qdrant Collections | Đảm bảo tính DRY, tập trung logic kiểm tra quyền tại 1 chỗ duy nhất, loại bỏ hoàn toàn nguy cơ lập trình viên quên check IDOR ở các route mới. |
| **Phản hồi khi vi phạm quyền** | 1. Trả về `404 Not Found` (Chọn)<br>2. Trả về `403 Forbidden` | Che giấu sự tồn tại của file, chống tấn công rà quét/dò tìm ID (enumeration attack). |
| **Phạm vi tài liệu** | 1. 100% Private (Chọn)<br>2. Cho phép Public | Tối giản kiến trúc (YAGNI), tập trung hoàn thiện bài toán bảo mật dữ liệu cá nhân trước. |
| **Cấu trúc File Storage** | 1. `storage/uploads/{user_id}/{doc_id}.pdf` (Chọn)<br>2. `storage/uploads/{doc_id}.pdf` (lưu phẳng) | Dễ phân tách dữ liệu trên ổ đĩa vật lý, thuận tiện dọn dẹp và kiểm tra quota người dùng. |
| **Vòng đời DB Session trong Background Task** | 1. Mở session mới độc lập trong task (Chọn)<br>2. Truyền session của request vào task | Tránh lỗi kết nối DB bị đóng ngắt giữa chừng sau khi endpoint trả về `202 Accepted`. |
| **Qdrant Multi-tenancy** | 1. Payload Metadata Filtering (Chọn)<br>2. Mỗi user 1 Qdrant collection | Tiết kiệm RAM/CPU tối đa, quản lý chung 1 collection tập trung nhưng vẫn bảo đảm cô lập dữ liệu tuyệt đối giữa các user. |
| **Xử lý tác vụ nền lỗi** | Đánh dấu `status="failed"` và lưu `error_message` | Người dùng biết nguyên nhân cụ thể và có thể bấm thử lại (Retry). |

---

## 4. Thiết Kế Kiến Trúc Chi Tiết

### 4.1. FastAPI Dependency Guard (`ValidDocumentDep`)
```python
async def get_valid_user_document(
    document_id: UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Document:
    stmt = select(Document).where(
        Document.id == document_id,
        Document.user_id == current_user.id
    )
    doc = await db.scalar(stmt)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc
```

### 4.2. Upload & Background Task Lifecycle
* **Upload:**
  * Lấy `current_user` qua `get_current_active_user`.
  * Lưu file vào `storage/uploads/{user_id}/{doc_id}.pdf`.
  * Insert bản ghi vào DB với `user_id=current_user.id`, `status="uploading"`.
  * Truyền primitive ID vào task nền: `background_tasks.add_task(process_pipeline, document_id=str(doc_id), user_id=str(user_id))`.
* **Background Task:**
  * Khởi tạo `async with async_session_maker() as session:` riêng để cập nhật trạng thái `processing`, `completed`, hoặc `failed`.

### 4.3. Qdrant Vector Store & Metadata Pre-filtering
* **Tạo index trên payload:**
  ```python
  self._create_payload_index_safe(field_name="user_id", field_schema=models.PayloadSchemaType.KEYWORD)
  ```
* **Gắn metadata khi chunking:**
  ```python
  node.metadata["user_id"] = str(user_id)
  node.metadata["doc_id"] = str(document_id)
  ```
* **Lọc trước khi truy vấn vector (Metadata Pre-filtering):**
  ```python
  filters = MetadataFilters(
      filters=[
          MetadataFilter(key="user_id", value=str(current_user.id)),
      ]
  )
  retriever = VectorIndexRetriever(index=index, similarity_top_k=5, filters=filters)
  ```

### 4.4. Dọn dẹp dữ liệu (`DELETE /documents/{id}`)
Thực hiện dọn dẹp đồng bộ ở 3 vị trí khi nhận request hợp lệ từ chủ sở hữu:
1. Xóa toàn bộ vector chunks trong Qdrant có `doc_id == document_id`.
2. Xóa bản ghi trong PostgreSQL (Cascade tự động xóa Chat/Flashcard liên quan).
3. Xóa thư mục/file vật lý trên đĩa.

---

## 5. Chiến Lược Kiểm Thử (Testing Strategy)
1. **Unit Test chống IDOR:** Giả lập `user_A` tạo document, `user_B` dùng token của mình truy cập -> Kiểm tra nhận về đúng mã `404 Not Found`.
2. **Integration Test RAG Isolation:** Index tài liệu chứa từ khóa độc nhất của `user_A`, thực hiện RAG query dưới quyền `user_B` -> Khẳng định kết quả trả về không chứa bất kỳ chunk nào của `user_A`.
