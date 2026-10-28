# Kế Hoạch Triển Khai Hệ Thống RAG Evaluation (Implementation Plan)

## Tổng Quan Tiến Độ

- [x] **Giai đoạn 1:** Khởi tạo Dependency & Cấu hình môi trường (`ragas`, `pandas`, `langchain-google-genai`)
- [x] **Giai đoạn 2:** Xây dựng Module lõi `app/ai_engine/evaluation/` (`metrics.py`, `runner.py`, `reporter.py`, `dataset_generator.py`)
- [x] **Giai đoạn 3:** Tạo Dữ liệu mẫu & Bộ Golden Dataset chuẩn (`data/evaluation/`)
- [x] **Giai đoạn 4:** Xây dựng Công cụ Dòng lệnh CLI (`scripts/eval_rag.py`)
- [x] **Giai đoạn 5:** Xây dựng Bộ kiểm thử Pytest Quality Gate (`tests/evaluation/test_rag_quality.py`)
- [x] **Giai đoạn 6:** Chạy Kiểm thử Đầu-Cuối (End-to-End Verification) và Kiểm tra Báo cáo Markdown

---

## Chi Tiết Các Giai Đoạn

### Giai đoạn 1: Dependency & Cấu hình môi trường
* Cập nhật `apps/api/pyproject.toml` để thêm `ragas>=0.2.0` và `langchain-google-genai` vào nhóm `dev`.
* Chạy `uv sync` để cập nhật `uv.lock` và môi trường ảo `.venv`.

### Giai đoạn 2: Module Lõi `app/ai_engine/evaluation/`
* `metrics.py`: Cấu hình LLM Judge bằng Gemini thông qua Ragas (`ChatGoogleGenerativeAI` hoặc direct wrapper) với temperature=0.0 cho tính tất định.
* `runner.py`: Pipeline điều phối gọi `VectorService`, `PromptComposer`, `LlmClient` để thu thập `retrieved_contexts` và `response`. Tích hợp Semaphore khống chế concurrency và cơ chế retry khi gặp lỗi 429.
* `reporter.py`: Định dạng kết quả thành Markdown report chi tiết và file tóm tắt JSON.
* `dataset_generator.py`: Module hỗ trợ sinh dữ liệu tổng hợp (Synthetic Dataset) từ văn bản tài liệu học tập.

### Giai đoạn 3: Dữ Liệu Kiểm Thử Chuẩn
* Tạo thư mục `apps/api/data/evaluation/` và `sample_docs/`.
* Xây dựng file `golden_dataset.json` mẫu chuẩn hóa (5–10 câu hỏi kiểm thử kiến thức học tập) với cấu trúc `user_input` và `reference`.

### Giai đoạn 4: CLI Script
* Tạo `apps/api/scripts/eval_rag.py` với `argparse`, hỗ trợ các cờ `--dataset`, `--generate-dataset`, `--output-dir`, in tóm tắt ra terminal.

### Giai đoạn 5: Pytest Quality Gate
* Tạo `apps/api/tests/evaluation/test_rag_quality.py`.
* Định nghĩa các ngưỡng assertion: Faithfulness >= 0.85, Answer Relevancy >= 0.80, Precision >= 0.75, Recall >= 0.75.

### Giai đoạn 6: Nghiệm Thu
* Thực thi chạy thử script và pytest.
* Kiểm tra báo cáo được sinh ra trong `apps/api/data/evaluation/reports/`.
