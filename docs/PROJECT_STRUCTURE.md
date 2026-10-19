# TÀI LIỆU CẤU TRÚC DỰ ÁN (PROJECT STRUCTURE SPECIFICATION)
## DỰ ÁN: NỀN TẢNG HỌC TẬP CÁ NHÂN HÓA TÍCH HỢP AI (AI LEARNING PLATFORM)

---

| **Thuộc tính** | **Giá trị** |
| :--- | :--- |
| **Mô hình kiến trúc** | Modular Monolith (Monorepo) |
| **Tech Stack chính** | Next.js 14, Tailwind CSS, shadcn/ui, FastAPI, SQLAlchemy 2.0 Async, PostgreSQL 15, Qdrant, Redis 7, Google Gemini 1.5 Flash |
| **Đội ngũ phụ trách** | **Long** (AI Lead), **Khoa** (Full-stack Study Engine), **Sơn** (Full-stack Workspace) |
| **Tài liệu tham chiếu** | [DESIGN.md](DESIGN.md) |
| **Phiên bản** | 1.0 |

---

## 1. TỔNG QUAN VÀ NGUYÊN TẮC THIẾT KẾ (DESIGN PRINCIPLES)

1. **Modular Monolith Monorepo**: Toàn bộ dự án nằm chung trong 1 kho lưu trữ Git nhưng phân tách thành 2 ứng dụng độc lập (`apps/api` và `apps/web`), dùng chung cấu hình hạ tầng (`docker/`), tài liệu kỹ thuật (`docs/`) và scripts tiện ích (`scripts/`).
2. **High Cohesion & Low Coupling**: Mỗi module nghiệp vụ ở Backend (Auth, Ingestion, Chat RAG, Roadmap, Quiz Bloom, Flashcard SM-2, Pomodoro, Admin) tự quản lý `models.py`, `schemas.py`, `router.py`, `service.py`. Giao tiếp giữa các module phải thông qua tầng Service hoặc Dependency Injection, không import chéo model thô.
3. **Cô lập Tầng AI (Decoupled AI Engine)**: Toàn bộ code liên quan đến Gemini API, Qdrant Vector DB, System Prompts và bộ lọc Prompt Injection nằm gọn trong `app/ai_engine/`. Tầng business logic chỉ gọi AI Engine qua các interface chuẩn.
4. **Phân chia Phân quyền Mã nguồn (Code Ownership)**: Đảm bảo 3 thành viên phát triển song song trong 4 Sprints (8 tuần) mà không gây xung đột mã nguồn (merge conflicts).

---

## 2. MA TRẬN PHÂN CÔNG TRÁCH NHIỆM (CODE OWNERSHIP MATRIX)

| Khu vực thư mục / File | Mô tả nghiệp vụ | Thành viên phụ trách |
| :--- | :--- | :--- |
| `apps/api/app/ai_engine/` | Client Gemini 1.5 Flash, Qdrant Client, Prompts sư phạm, Guardrails | **Long (AI Lead)** |
| `apps/api/app/modules/documents/` | Upload PDF, Worker phân tích Vision OCR (LaTeX $...$, caption ảnh) | **Long (AI Lead)** |
| `apps/api/app/modules/chat/` | LlamaIndex RAG, Chatbot Socratic 3 tầng, SSE Streaming | **Long (AI Lead)** |
| `apps/api/app/modules/roadmaps/` | Cây Lộ trình học (Roadmap Tree), Thuật toán chia Study Blocks (15-30p) | **Khoa (Study Engine)** |
| `apps/api/app/modules/flashcards/` | Quản lý thẻ ghi nhớ, Thuật toán SuperMemo SM-2 | **Khoa (Study Engine)** |
| `apps/api/app/modules/quizzes/` | Sinh đề Bloom 3 cấp độ, Thuật toán trộn đề Interleaving (70/30) | **Khoa & Long** |
| `apps/api/app/modules/study_sessions/` | API lưu phiên học Pomodoro, tổng hợp thời gian theo môn | **Khoa (Study Engine)** |
| `apps/api/migrations/` | 11 bảng CSDL PostgreSQL, Alembic Migrations | **Khoa (Study Engine)** |
| `apps/web/src/app/(dashboard)/workspace/` | Split-View Workspace: PDF Viewer bên trái, KaTeX Chat bên phải | **Sơn (Workspace)** |
| `apps/web/src/app/(dashboard)/quiz/` | Giao diện Focus Mode làm bài trắc nghiệm, Countdown, Gap Analysis | **Sơn (Workspace)** |
| `apps/web/src/app/(dashboard)/flashcards/` | Giao diện Lật thẻ 3D, 4 nút đánh giá độ nhớ SM-2 | **Sơn (Workspace)** |
| `apps/web/src/app/(admin)/` & `apps/api/modules/admin/` | Quản lý tài khoản, Khóa user, Biểu đồ Token & Chi phí API | **Sơn (Workspace)** |
| `docker/`, `scripts/`, `apps/web/src/components/ui/` | Docker Compose, setup local dev, Design System (shadcn/ui Indigo) | **Sơn (Workspace)** |

---

## 3. SƠ ĐỒ CÂY THƯ MỤC TOÀN DỰ ÁN (PROJECT DIRECTORY TREE)

```text
ai-learning-platform/
├── .github/                                # CI/CD Workflows tự động
│   └── workflows/
│       ├── backend-ci.yml                  # Linter Ruff & Pytest Backend
│       └── frontend-ci.yml                 # ESLint, Prettier & TypeScript Typecheck
│
├── docker/                                 # Môi trường container hóa
│   ├── docker-compose.yml                  # Postgres 15, Qdrant, Redis 7, Backend, Frontend
│   ├── docker-compose.override.yml.example # File override cho môi trường local từng máy
│   ├── Dockerfile.backend                  # Multi-stage build cho FastAPI
│   ├── Dockerfile.frontend                 # Standalone build cho Next.js 14
│   └── nginx/                              # Nginx reverse proxy định tuyến local
│       └── default.conf
│
├── docs/                                   # Tài liệu kỹ thuật
│   ├── DESIGN.md                           # Tài liệu thiết kế hệ thống v3.0 (SRS & DB DDL)
│   └── PROJECT_STRUCTURE.md                # Tài liệu này (Quy chuẩn cấu trúc dự án)
│
├── scripts/                                # Scripts tự động hóa tác vụ phát triển & demo
│   ├── init_db.sh                          # Khởi tạo DB Postgres & Vector Collection Qdrant
│   ├── seed_data.py                        # Nạp tài liệu mẫu, câu hỏi và user demo
│   └── run_dev.sh                          # 1 lệnh khởi động trọn bộ môi trường dev
│
├── storage/                                # Thư mục lưu trữ vật lý (Volume mount)
│   └── uploads/                            # File PDF gốc người dùng tải lên
│
├── apps/
│   ├── api/                                # =========================================
│   │   │                                   # BACKEND: FastAPI Modular Monolith (Python)
│   │   │                                   # =========================================
│   │   ├── pyproject.toml                  # Quản lý dependency bằng `uv`
│   │   ├── alembic.ini                     # Cấu hình database migrations
│   │   ├── migrations/                     # Thư mục lịch sử thay đổi Schema Database
│   │   │   ├── env.py                      # Kết nối async SQLAlchemy với Alembic
│   │   │   └── versions/                   # Chứa script DDL của 11 bảng chuẩn hóa
│   │   ├── tests/                          # Automated tests
│   │   │   ├── conftest.py                 # Fixtures test: Test DB, Fake Gemini Client
│   │   │   ├── unit/                       # Test SM-2, Bloom Quiz, Prompt Injection
│   │   │   └── integration/                # Test RAG retrieval, Auth API, Upload API
│   │   └── app/                            # Mã nguồn chính của Backend
│   │       ├── main.py                     # Entry point FastAPI, CORS, Global Exception
│   │       ├── core/                       # Thành phần nền tảng dùng chung
│   │       │   ├── config.py               # Pydantic Settings đọc biến môi trường .env
│   │       │   ├── database.py             # Async Engine & async_sessionmaker (PostgreSQL)
│   │       │   ├── redis.py                # Redis client (Rate Limiter & Session Cache)
│   │       │   ├── security.py             # Hash bcrypt, tạo & kiểm tra JWT token
│   │       │   ├── exceptions.py           # Custom Exception Classes & HTTP Error mappings
│   │       │   └── middlewares.py          # Middleware audit token, kiểm tra rate limit
│   │       ├── common/                     # Thư viện tái sử dụng chung
│   │       │   ├── pagination.py           # Schema phân trang đồng nhất (page, size, total)
│   │       │   └── response.py             # Standard JSON response wrapper
│   │       ├── ai_engine/                  # Hạ tầng AI (Long phụ trách)
│   │       │   ├── gemini_client.py        # Client Google Gemini 1.5 Flash (Vision & LLM)
│   │       │   ├── qdrant_client.py        # Kết nối Vector DB `learning_chunks` (768-dim)
│   │       │   ├── prompts/                # Toàn bộ Prompt Template chuẩn sư phạm
│   │       │   │   ├── socratic_tiers.py   # Prompts 3 tầng gợi mở Socratic Scaffolding
│   │       │   │   ├── bloom_quiz.py       # Prompt sinh quiz 3 cấp độ nhận thức Bloom
│   │       │   │   └── flashcard_gen.py    # Prompt trích xuất công thức & định lý
│   │       │   └── guardrails/             # An toàn & Bảo mật AI
│   │       │       └── prompt_injection.py # Chặn phá vỡ quy tắc sư phạm / leak system prompt
│   │       └── modules/                    # Các Domain Modules nghiệp vụ
│   │           ├── auth/                   # Quản lý xác thực người dùng
│   │           │   ├── models.py           # SQLAlchemy User model (bảng `users`)
│   │           │   ├── schemas.py          # Pydantic schemas (Login, Register, Token)
│   │           │   ├── router.py           # APIRouter `/api/v1/auth`
│   │           │   └── service.py          # Logic nghiệp vụ đăng ký/đăng nhập
│   │           ├── subjects/               # Quản lý môn học
│   │           │   ├── models.py           # Subject model (bảng `subjects`)
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/subjects`
│   │           │   └── service.py
│   │           ├── documents/              # Quản lý tài liệu & Ingestion Worker
│   │           │   ├── models.py           # Document model (bảng `documents`)
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/documents`
│   │           │   ├── service.py
│   │           │   └── ingestion_worker.py # Vision OCR (LaTeX, caption), Chunking, Vector
│   │           ├── chat/                   # AI Tutor RAG & Socratic Chatbot
│   │           │   ├── models.py           # ChatSession, ChatMessage models
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/chat` (SSE Stream)
│   │           │   └── service.py          # LlamaIndex retrieval & citation parser
│   │           ├── roadmaps/               # Cây Lộ trình học & Study Blocks
│   │           │   ├── models.py           # Roadmap, RoadmapNode models
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/roadmaps`
│   │           │   └── service.py          # Phân bổ khối 15-30p, mở khóa tuần tự
│   │           ├── study_sessions/         # Phiên học Pomodoro
│   │           │   ├── models.py           # StudySession model (bảng `study_sessions`)
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/study-sessions`
│   │           │   └── service.py
│   │           ├── flashcards/             # Thẻ ghi nhớ & Thuật toán SM-2
│   │           │   ├── models.py           # FlashcardDeck, Flashcard models
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/flashcards`
│   │           │   └── sm2_algorithm.py    # Hàm tính EF', interval_days, due_date
│   │           ├── quizzes/                # Bài kiểm tra Bloom & Phân tích lỗ hổng
│   │           │   ├── models.py           # Quiz, QuizQuestion, QuizAttempt models
│   │           │   ├── schemas.py
│   │           │   ├── router.py           # APIRouter `/api/v1/quizzes`
│   │           │   └── interleaving.py     # Trộn 70% bài mới, 30% bài cũ
│   │           └── admin/                  # Cổng Quản trị & Audit
│   │               ├── models.py           # TokenUsageLog model
│   │               ├── schemas.py
│   │               ├── router.py           # APIRouter `/api/v1/admin`
│   │               └── service.py
│   │
│   └── web/                                # =========================================
│                                           # FRONTEND: Next.js 14 App Router (Sơn)
│                                           # =========================================
│       ├── package.json
│       ├── tsconfig.json
│       ├── tailwind.config.ts              # Cold Tone: Indigo-600, Slate-50/950, KaTeX
│       ├── next.config.mjs
│       ├── public/                         # Static assets, favicon, PDF worker
│       │   └── pdf.worker.min.js
│       └── src/
│           ├── app/                        # Next.js 14 App Router Pages
│           │   ├── layout.tsx              # Root Layout: Themes, Fonts, Providers
│           │   ├── page.tsx                # Trang giới thiệu / Landing Page
│           │   ├── (auth)/                 # Route Group: Màn hình xác thực
│           │   │   ├── login/page.tsx
│           │   │   └── register/page.tsx
│           │   ├── (dashboard)/            # Route Group: Không gian sinh viên
│           │   │   ├── layout.tsx          # Sidebar, Header, Widget Pomodoro nổi
│           │   │   ├── dashboard/page.tsx  # Tổng quan: streak, giờ học, môn học
│           │   │   ├── workspace/[id]/page.tsx # Split-View Workspace (PDF + Chat KaTeX)
│           │   │   ├── roadmap/page.tsx    # Cây lộ trình học tương tác
│           │   │   ├── quiz/[id]/page.tsx  # Focus Mode thi trắc nghiệm Bloom
│           │   │   └── flashcards/page.tsx # Lật thẻ 3D ôn tập SM-2
│           │   └── (admin)/                # Route Group: Cổng quản trị viên
│           │       ├── layout.tsx          # Admin Navigation
│           │       ├── admin/users/page.tsx      # Quản lý & Khóa tài khoản
│           │       └── admin/analytics/page.tsx  # Biểu đồ token tiêu thụ & chi phí API
│           ├── components/
│           │   ├── ui/                     # Bộ UI Components (shadcn/ui nguyên tử)
│           │   │   ├── button.tsx, dialog.tsx, card.tsx, progress.tsx, tabs.tsx
│           │   ├── shared/                 # Thành phần dùng chung toàn ứng dụng
│           │   │   ├── citation-pill.tsx   # Thẻ trích dẫn [[Trang X]] điều hướng PDF
│           │   │   ├── katex-renderer.tsx  # Render công thức toán học $...$ và $$...$$
│           │   │   ├── pomodoro-timer.tsx  # Widget Pomodoro nổi (Floating)
│           │   │   └── navbar.tsx
│           │   └── modules/                # Components chia theo nghiệp vụ
│           │       ├── workspace/          # PDFViewer (react-pdf), ChatBox (SSE Stream)
│           │       ├── roadmap/            # RoadmapTree, NodeCard, StudyBlockModal
│           │       ├── quiz/               # QuestionCard, TimerCountdown, GapAnalysis
│           │       └── flashcards/         # Card3DFlip, MemoryRatingButtons
│           ├── hooks/                      # Custom React Hooks
│           │   ├── use-pomodoro.ts         # Quản lý đếm giờ & sync session với server
│           │   ├── use-sse-chat.ts         # Hook nhận stream Markdown từ FastAPI
│           │   └── use-pdf-scroll.ts       # Hook điều phối cuộn trang PDF từ Chatbox
│           ├── stores/                     # State Management (Zustand)
│           │   ├── auth-store.ts           # Token, user info, login state
│           │   ├── workspace-store.ts      # Active page, target citation, zoom
│           │   └── pomodoro-store.ts       # Running state, minutes, current subject
│           ├── lib/                        # Thư viện tiện ích
│           │   ├── api-client.ts           # Axios / Fetch client gắn JWT tự động
│           │   └── utils.ts                # Helper cn (clsx + twMerge), formatters
│           └── types/                      # TypeScript Definitions chuẩn hóa
│               ├── api.d.ts                # Định nghĩa Response & Payload chuẩn
│               ├── roadmap.d.ts
│               └── quiz.d.ts
│
├── .env.example                            # Bản mẫu biến môi trường chuẩn
├── .gitignore                              # Quy tắc bỏ qua files tạm, cache, storage
└── README.md                               # Hướng dẫn setup nhanh & kịch bản chạy
```

---

## 4. QUY CHUẨN CƠ SỞ DỮ LIỆU & ÁNH XẠ MODEL BACKEND

11 bảng dữ liệu chuẩn hóa bậc 3 (3NF) từ `docs/DESIGN.md` được ánh xạ chính xác vào các modules tại `apps/api/app/modules/`:

| Tên bảng CSDL | Đường dẫn Model | Chức năng nghiệp vụ |
| :--- | :--- | :--- |
| `users` | `modules/auth/models.py` | Tài khoản, vai trò, hạn ngạch token hàng ngày |
| `subjects` | `modules/subjects/models.py` | Môn học cá nhân / hệ thống |
| `documents` | `modules/documents/models.py` | Quản lý file PDF, tổng số trang, trạng thái xử lý |
| `roadmaps` | `modules/roadmaps/models.py` | Lộ trình học tổng thể theo môn |
| `roadmap_nodes` | `modules/roadmaps/models.py` | Các chặng phân cấp & khối Study Blocks 15-30p |
| `study_sessions` | `modules/study_sessions/models.py` | Phiên học Pomodoro và tổng thời lượng tích lũy |
| `chat_sessions` | `modules/chat/models.py` | Phiên trò chuyện gắn với tài liệu |
| `chat_messages` | `modules/chat/models.py` | Lịch sử tin nhắn, tầng Socratic (0-3), Citations |
| `flashcard_decks` | `modules/flashcards/models.py` | Bộ thẻ ghi nhớ theo môn/tài liệu |
| `flashcards` | `modules/flashcards/models.py` | Mặt trước/sau, hệ số EF, khoảng cách ôn SM-2 |
| `quizzes` | `modules/quizzes/models.py` | Bài kiểm tra tổng hợp từ tài liệu |
| `quiz_questions` | `modules/quizzes/models.py` | Câu hỏi theo 3 cấp độ Bloom (Cấp 1, 2, 3) |
| `quiz_attempts` | `modules/quizzes/models.py` | Lịch sử làm bài, điểm số, thời gian |
| `quiz_attempt_answers` | `modules/quizzes/models.py` | Câu trả lời từng câu, xác định lỗ hổng |
| `token_usage_logs` | `modules/admin/models.py` | Nhật ký tiêu thụ token Gemini, cảnh báo injection |

---