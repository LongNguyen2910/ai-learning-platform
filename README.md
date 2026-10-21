<div align="center">

# AI-Powered Personalized Learning Platform

An enterprise-grade, modular monolith platform delivering personalized learning workflows through AI-driven Socratic tutoring, Vision OCR, adaptive roadmap generation, Bloom's taxonomy quizzes, and SM-2 spaced repetition flashcards.

[![Architecture](https://img.shields.io/badge/Architecture-Modular%20Monolith-indigo.svg)](#architecture-overview)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%7C%20SQLAlchemy%202.0%20Async-009688.svg)](apps/api)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2014%20%7C%20Tailwind%20%7C%20shadcn%2Fui-000000.svg)](apps/web)
[![Package Manager: uv](https://img.shields.io/badge/Python%20Toolchain-uv%20(Astral)-blueviolet.svg)](https://github.com/astral-sh/uv)
[![Package Manager: pnpm](https://img.shields.io/badge/Node%20Toolchain-pnpm%20(Fast%20%26%20Efficient)-orange.svg)](https://pnpm.io/)
[![Database](https://img.shields.io/badge/Infrastructure-PostgreSQL%2015%20%7C%20Qdrant%20%7C%20Redis%207-blue.svg)](docker/docker-compose.yml)

</div>

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites & Toolchain](#prerequisites--toolchain)
3. [Quick Start Guide](#quick-start-guide)
   - [1. Clone and Environment Configuration](#1-clone-and-environment-configuration)
   - [2. Infrastructure Orchestration (Docker)](#2-infrastructure-orchestration-docker)
   - [3. Backend Setup (`apps/api` with `uv`)](#3-backend-setup-appsapi-with-uv)
   - [4. Frontend Setup (`apps/web` with `pnpm`)](#4-frontend-setup-appsweb-with-pnpm)
4. [Verification & Health Checks](#verification--health-checks)
5. [Database Migrations & Maintenance](#database-migrations--maintenance)
6. [Code Quality & Standards](#code-quality--standards)
7. [Team Responsibilities & Code Ownership](#team-responsibilities--code-ownership)
8. [Git Workflow & Collaboration](#git-workflow--collaboration)

---

## Architecture Overview

The repository adopts a **Modular Monolith Monorepo** pattern, ensuring high cohesion within business domains while decoupling deployment, testing, and interface contracts:

```text
ai-learning-platform/
├── apps/
│   ├── api/             # Backend: FastAPI, SQLAlchemy 2.0 Async, LlamaIndex, Google Gemini
│   └── web/             # Frontend: Next.js 14 (App Router), Tailwind CSS, shadcn/ui, KaTeX
├── docker/              # Multi-container orchestration (PostgreSQL 15, Qdrant, Redis 7)
├── docs/                # Architecture specifications, DDL schemas, and system designs
├── scripts/             # Operational automation scripts (development bootstrapper, seeding)
├── storage/             # Persistent volume mounts and upload directories
├── .env.example         # Canonical environment variable specification
└── README.md            # Project technical reference & setup guide
```

---

## Prerequisites & Toolchain

This project enforces modern, deterministic, and high-performance package management:
* **Python Toolchain:** Use [`uv`](https://github.com/astral-sh/uv) exclusively. Do not use legacy `pip` or virtualenv wrappers.
* **JavaScript/Node.js Toolchain:** Use [`pnpm`](https://pnpm.io/) exclusively. Avoid `npm` or `yarn` to guarantee lockfile parity and disk space efficiency via hard linking.

### Required Software

| Tool | Recommended Version | Installation Command |
| :--- | :--- | :--- |
| **Git** | `>= 2.40` | OS native package manager |
| **Docker & Docker Compose** | Engine `>= 26.0`, Compose `>= 2.25` | [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Engine |
| **Python** | `>= 3.11` | [python.org](https://www.python.org/) or via `uv python install 3.12` |
| **uv** | Latest | **macOS/Linux/WSL:** `curl -LsSf https://astral.sh/uv/install.sh \| sh`<br>**Windows (PowerShell):** `irm https://astral.sh/uv/install.ps1 \| iex` |
| **Node.js** | `>= 20.x (LTS)` | [nodejs.org](https://nodejs.org/) or via `nvm install --lts` |
| **pnpm** | `>= 9.x` | `corepack enable` or `npm install -g pnpm` |

---

## Quick Start Guide

### 1. Clone and Environment Configuration

Clone the repository and initialize the root configuration from the template:

```bash
git clone <REPOSITORY_URL> ai-learning-platform
cd ai-learning-platform

# Generate local environment file
cp .env.example .env
```

> [!IMPORTANT]
> Obtain a development API key from [Google AI Studio](https://aistudio.google.com/) and update `GEMINI_API_KEY`. Never commit `.env` to version control.

---

### 2. Infrastructure Orchestration (Docker)

Spin up containerized dependencies (PostgreSQL 15, Qdrant Vector DB v1.19, Redis 7):

```bash
# Start all infrastructure services in detached mode
docker compose -f docker/docker-compose.yml up -d

# Verify all services report healthy status
docker compose -f docker/docker-compose.yml ps
```

Expected output:
```text
NAME              IMAGE                   STATUS                    PORTS
ai_lms_postgres   postgres:15-alpine      Up (healthy)              0.0.0.0:5432->5432/tcp
ai_lms_qdrant     qdrant/qdrant:v1.19.2   Up (healthy)              0.0.0.0:6333-6334->6333-6334/tcp
ai_lms_redis      redis:7-alpine          Up (healthy)              0.0.0.0:6379->6379/tcp
```

---

### 3. Backend Setup (`apps/api` with `uv`)

All backend dependencies, virtual environments, and scripts are managed by **`uv`**.

```bash
# Navigate to the backend service
cd apps/api

# Synchronize virtualenv with deterministic lockfile
uv sync

# Verify environment configuration and database connectivity
uv run python -c "from app.core.config import settings; print('Config loaded successfully for env:', settings.APP_ENV)"

# Launch development server with hot-reload
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

* **Swagger UI Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc Interactive Docs:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Service Health Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)

---

### 4. Frontend Setup (`apps/web` with `pnpm`)

All frontend packages and build steps are managed using **`pnpm`**.

#### 4.1. Project Initialization (If scaffolding for the first time)
```bash
# From repository root
pnpm create next-app apps/web --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
```

#### 4.2. Dependency Installation
```bash
cd apps/web

# Install core runtime dependencies
pnpm add zustand axios clsx tailwind-merge lucide-react katex react-pdf
pnpm add -D @types/katex

# Initialize shadcn/ui components
pnpm dlx shadcn-ui@latest init
```

#### 4.3. Client Environment Setup
Create `apps/web/.env.local`:
```ini
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

#### 4.4. Launch Development Server
```bash
pnpm dev
```

* **Application Portal:** [http://localhost:3000](http://localhost:3000)

---

## Verification & Health Checks

Execute the provided automated validation pipeline:

```bash
# From repository root
./scripts/run_dev.sh
```

Or verify individual subsystems manually:

```bash
# 1. PostgreSQL connection
docker exec -it ai_lms_postgres pg_isready -U postgres -d ai_lms_db

# 2. Redis ping
docker exec -it ai_lms_redis redis-cli ping

# 3. Qdrant HTTP health endpoint
curl -f http://localhost:6333/healthz

# 4. FastAPI Health Route
curl -s http://localhost:8000/health | jq .
```

---

## Database Migrations & Maintenance

Database schema updates are handled asynchronously via **Alembic** within `apps/api`:

```bash
cd apps/api

# Generate an autodetected migration script after modifying models
uv run alembic revision --autogenerate -m "describe_migration"

# Apply pending migrations to PostgreSQL
uv run alembic upgrade head

# Roll back the most recent migration step
uv run alembic downgrade -1
```

---

## Code Quality & Standards

Strict linting and formatting standards are enforced across both stacks.

### Python Backend (`apps/api`)
```bash
cd apps/api

# Run Ruff linter and apply autofixes
uv run ruff check --fix .

# Format codebase according to PEP 8 standards
uv run ruff format .

# Run test suite
uv run pytest
```

### TypeScript Frontend (`apps/web`)
```bash
cd apps/web

# Run ESLint & TypeScript type checking
pnpm lint
pnpm tsc --noEmit
```

---

## Team Responsibilities & Code Ownership

Refer to [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) for full responsibility mappings:

| Member | Primary Domain | Modules & Directory Scope |
| :--- | :--- | :--- |
| **Long (AI Lead)** | AI Engine & Core Ingestion | `apps/api/app/ai_engine/`, Vision OCR Ingestion Worker (`modules/documents/`), Socratic RAG Chat (`modules/chat/`). |
| **Khoa (Study Engine)** | Adaptive Pedagogy & DB | `apps/api/app/modules/` (Roadmaps, Flashcards SM-2, Bloom Quizzes, Study Sessions), Alembic Migrations (`apps/api/migrations/`). |
| **Sơn (Workspace & Infra)** | Full-Stack UI & DevOps | `apps/web/` (Split-View Workspace, Quiz UI, Flashcards 3D, Admin Portal), Design System, Docker Compose (`docker/`). |

---

## Git Workflow & Collaboration

1. **Branching Protocol:** Never push directly to `main`. Create feature branches with descriptive prefixes:
   * `feature/ai-<name>`: AI engine, RAG pipeline, vision processing.
   * `feature/study-<name>`: Pedagogical algorithms, migrations, domain models.
   * `feature/ui-<name>`: Next.js pages, shadcn/ui components, client state.
2. **Commit Conventions:** Follow Conventional Commits format:
   * `feat: implement Socratic tiered response generator`
   * `fix: resolve Qdrant version compatibility in compose`
   * `refactor: optimize SM-2 interval computation`
3. **Security Assurance:** Never commit `.env`, credentials, or model weights. Verify that `.gitignore` patterns remain uncompromised before committing.

---

<div align="center">
<sub>Built with precision for scalable, intelligent pedagogical systems.</sub>
</div>
