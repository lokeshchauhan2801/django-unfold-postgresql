# AI Knowledge & Chat Platform

A Django-based Demo Company for intelligent chat and document processing. Built with a modular architecture that supports multiple AI providers, vector search, async task processing, and observability out of the box.

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        Django Application                        │
│  chat  ·  docs  ·  auth  ·  company  ·  ai  ·  audit             │
│  basics  ·  scrapper  ·  infrastructure                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
   │  PostgreSQL  │    │    Redis     │    │   Celery Workers  │
   │  (primary   │    │  (cache &    │    │  (document ingest │
   │   database) │    │   broker)    │    │   & async tasks)  │
   └─────────────┘    └──────────────┘    └──────────────────┘
          │                                        │
   ┌──────┴──────┐    ┌──────────────┐    ┌───────┴──────────┐
   │   Temporal  │    │   ChromaDB   │    │      Kafka        │
   │  (workflow  │    │ (vector store│    │  (event streaming)│
   │  orchestr.) │    │  & RAG)      │    │                   │
   └─────────────┘    └──────────────┘    └──────────────────┘
                               │
                      ┌────────┴────────┐
                      │    Langfuse      │
                      │ (LLM observabil.)│
                      └─────────────────┘
```

**Infrastructure services:**

| Service    | Purpose                          | Port  |
|------------|----------------------------------|-------|
| Django     | Web application & REST API       | 8000  |
| PostgreSQL | Primary relational database      | 5432  |
| Redis      | Cache, session store, task broker| 6379  |
| Kafka      | Event streaming (KRaft mode)     | 9092  |
| ChromaDB   | Vector store for RAG             | 8001  |
| Langfuse   | LLM tracing & observability      | 3001  |
| Temporal   | Durable workflow orchestration   | 7233  |
| Temporal UI| Workflow management dashboard    | 8080  |

---

## Quick Start (3 commands)

```bash
make env          # copy .env.example → .env
make migrate      # apply database migrations
make run          # start development server at http://127.0.0.1:8000
```

---

## Full Local Setup (without Docker)

### Prerequisites

- Python 3.10+
- Node.js 22+
- Git

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd django-unfold
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements/local.txt
cd frontend && npm ci && npm run build && cd ..
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — set DJANGO_SECRET_KEY, OPENAI_API_KEY (embeddings), and the chat provider settings
```

### 4. Run migrations and create a superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 5. Start the development server

```bash
# Document indexing runs asynchronously in the local development server.
python manage.py runserver
```

Uploads are saved immediately and indexed by a managed local background executor, so
Redis and a Celery worker do not need to be started for local development. The chat
shows queued, processing-stage, and progress updates; ask questions about a file
after it reaches Ready. In production, Docker Compose starts Redis and the Celery
worker automatically. Celery uses four worker processes; embedding requests contain
up to 96 text chunks and run at most four concurrently per document.

Open:
- http://127.0.0.1:8000/ — React chat workspace
- http://127.0.0.1:8000/admin/ — Django Unfold admin

The chat and admin routes share the same sign-in screen and accept either a username or email address. The same Django session is used on both routes. Active company owners and admins can access the admin workspace for their own company; system administrators can access every company.

The main site opens a React-powered ChatGPT-style workspace. Start a chat from the sidebar, browse saved conversations, and use the plus button inside the prompt composer to attach PDF, DOCX, TXT, Markdown, CSV, XLSX, or JSON files. Chats and messages are stored in Django and scoped to the selected company; users with multiple memberships choose a company workspace before chatting. Uploaded files retain their owner, company, conversation, file metadata, processing status, chunk count, and database reference; each attachment appears in its conversation history and the Library. Supported files are extracted, split into overlapping chunks, embedded with OpenAI, and stored in persistent Chroma. In the admin workspace, the Chat sessions view shows sessions on the left and the selected conversation with its indexed chunk text on the right. System administrators can also load stored embedding vectors for individual chunks. Each chunk UUID and source location is stored in Django and returned as a citation. Chat responses use the configured AI provider. When a chart is requested, the chat API returns validated pie, bar, or line chart data grounded in retrieved file passages; the React client renders that API response. Scanned/image-only PDFs, legacy XLS files, and other unsupported formats are rejected.

Set `OPENAI_API_KEY` for document embeddings. By default, chat uses OpenAI with `AI_PROVIDER=openai` and `DEFAULT_LLM_MODEL=gpt-4o-mini`. To use DeepSeek or another OpenAI-compatible chat API, set `AI_PROVIDER=openai_compatible`, `AI_BASE_URL` to that API's `/v1` endpoint, `AI_API_KEY` to its key, and `DEFAULT_LLM_MODEL` to its model identifier. Chat credentials are separate from the OpenAI embedding key; switching chat providers does not require code changes. Extracted text from supported files and chat prompts are sent to the configured provider for answers. Local development stores Chroma data under `chroma_data/`; Docker uses the persistent Chroma service volume. The admin remains available at `/admin/`.

---

## Docker Compose Setup

Docker Compose brings up the full stack: Postgres, Redis, Kafka, ChromaDB, Langfuse, Temporal, Django, and Celery workers.

### Prerequisites

- Docker 24+
- Docker Compose v2

### 1. Prepare environment file

```bash
cp .env.example .env
# Set secure values for DJANGO_SECRET_KEY and LANGFUSE_NEXTAUTH_SECRET
```

### 2. Start infrastructure services only (recommended first time)

```bash
make docker-up
# Equivalent: docker-compose up -d postgres redis kafka chromadb langfuse temporal temporal-ui
```

### 3. Start the full stack including Django

```bash
docker-compose up -d
```

### 4. View logs

```bash
make docker-logs
# Or tail a specific service:
docker-compose logs -f django
```

### 5. Stop everything

```bash
make docker-down
```

### Service URLs (Docker)

| Service     | URL                          |
|-------------|------------------------------|
| Django app  | http://localhost:8000        |
| Django admin| http://localhost:8000/admin/ |
| Langfuse    | http://localhost:3001        |
| Temporal UI | http://localhost:8080        |
| ChromaDB    | http://localhost:8001        |

---

## Environment Variables Reference

Copy `.env.example` to `.env` and override as needed.

| Variable                    | Default                        | Description                                      |
|-----------------------------|--------------------------------|--------------------------------------------------|
| `DJANGO_SECRET_KEY`         | *(required)*                   | Django secret key — use a strong random value    |
| `DJANGO_DEBUG`              | `1`                            | Set to `0` in production                         |
| `DJANGO_ALLOWED_HOSTS`      | `localhost,127.0.0.1,[::1]`    | Comma-separated allowed hosts                    |
| `DJANGO_SETTINGS_MODULE`    | `base.settings.local`           | Settings module to use                           |
| `POSTGRES_DB`               | `aiplatform`                   | PostgreSQL database name                         |
| `POSTGRES_USER`             | `aiplatform`                   | PostgreSQL user                                  |
| `POSTGRES_PASSWORD`         | `aiplatform123`                | PostgreSQL password                              |
| `POSTGRES_HOST`             | `localhost`                    | PostgreSQL host (`postgres` in Docker)           |
| `POSTGRES_PORT`             | `5432`                         | PostgreSQL port                                  |
| `REDIS_URL`                 | `redis://localhost:6379/0`     | Redis connection URL                             |
| `KAFKA_BOOTSTRAP_SERVERS`   | `localhost:9092`               | Kafka broker address                             |
| `TEMPORAL_HOST`             | `localhost:7233`               | Temporal server address                          |
| `CHROMA_HOST`               | *(empty)*                      | Chroma server host; empty uses persistent local Chroma |
| `CHROMA_PORT`               | `8000`                         | Chroma server port (Docker service port)         |
| `CHROMA_PATH`               | `chroma_data`                  | Persistent local vector data directory           |
| `LANGFUSE_HOST`             | `http://localhost:3001`        | Langfuse API base URL                            |
| `LANGFUSE_PUBLIC_KEY`       | *(empty)*                      | Langfuse project public key                      |
| `LANGFUSE_SECRET_KEY`       | *(empty)*                      | Langfuse project secret key                      |
| `LANGFUSE_NEXTAUTH_SECRET`  | `changeme-in-production`       | Langfuse auth secret — **change in production**  |
| `LANGFUSE_SALT`             | `changeme-salt`                | Langfuse password hashing salt                   |
| `AI_PROVIDER`               | `openai`                       | Chat provider: `openai` or `openai_compatible`   |
| `DEFAULT_LLM_MODEL`         | `gpt-4o-mini`                  | Chat model name                                  |
| `AI_API_KEY`                | `OPENAI_API_KEY`               | Chat API key; use the provider-specific key      |
| `AI_BASE_URL`               | *(empty)*                      | Chat API `/v1` base URL for compatible providers|
| `OPENAI_EMBEDDING_MODEL`    | `text-embedding-3-small`       | OpenAI embedding model for document chunks/queries |
| `OPENAI_API_KEY`            | *(required for embeddings)*    | OpenAI key for embeddings; also default chat key|
| `OLLAMA_BASE_URL`           | `http://localhost:11434`       | Ollama base URL for local LLM                    |
| `DOCUMENT_PROCESSING_BACKEND` | `celery`                     | Processing backend: `celery`, `kafka`, `temporal`|
| `CORS_ALLOWED_ORIGINS`      | `http://localhost:3000,...`    | CORS allowed origins (comma-separated)           |
| `MAX_UPLOAD_SIZE_MB`        | `50`                           | Maximum file upload size in MB                   |

---

## API Endpoints Reference

### Chat

| Method | URL             | Description                   |
|--------|-----------------|-------------------------------|
| GET    | `/chat/`        | Chat UI page                  |
| POST   | `/chat/api/`    | Send a message, get an AI reply and PDF citations |
| GET    | `/chat/api/conversations/` | List the signed-in user's conversations |
| GET    | `/chat/api/conversations/<id>/` | Load a conversation, messages, citations, charts, and attached-file metadata |

### Documents

| Method | URL                   | Description              |
|--------|-----------------------|--------------------------|
| GET    | `/documents/`         | List uploaded documents and their processing metadata |
| POST   | `/documents/upload/`  | Upload and index a supported document, linked to a conversation |
| POST   | `/documents/<id>/reprocess/` | Retry indexing a previously saved failed upload |

### Users / Auth

| Method | URL              | Description                         |
|--------|------------------|-------------------------------------|
| POST   | `/api/v1/auth/register/` | Register a new user            |
| POST   | `/api/v1/auth/login/`  | Obtain JWT access & refresh tokens |
| POST   | `/api/v1/auth/logout/` | Invalidate refresh token       |
| GET    | `/api/v1/auth/me/`     | Get current authenticated user info |
| POST   | `/chat/session/login/` | Create the chat page's signed-in session |
| POST   | `/chat/session/logout/` | End the chat page's session |

### Admin

| URL       | Description              |
|-----------|--------------------------|
| `/admin/` | Django Unfold admin panel |

---

## Development Commands (Makefile)

Run `make help` to see all available targets.

```
  help                   Show this help
  install                Install Python dependencies (local)
  migrate                Apply database migrations
  makemigrations         Create new migrations
  run                    Start development server
  shell                  Open Django shell
  createsuperuser        Create admin superuser
  collectstatic          Collect static files
  test                   Run tests
  lint                   Run ruff linter
  format                 Format code
  docker-up              Start all infrastructure services
  docker-down            Stop all services
  docker-logs            Tail service logs
  celery-worker          Start Celery worker (local)
  celery-beat            Start Celery beat scheduler (local)
  env                    Copy .env.example to .env
```

---

## Project Structure

```
django-unfold/
│
├── ai/                            # AI provider abstractions
├── audit/                         # Audit logs
├── auth/                          # Authentication and user model
├── basics/                        # Shared models, middleware, admin
├── chat/                          # Conversations and messaging
├── company/                       # Company tenancy and memberships
├── docs/                          # Document processing and chunks
├── scrapper/                      # Document API and queue integration
│
├── config/                        # Django project configuration
│   └── ...                        # Compatibility imports for base project config
├── base/                          # Active settings, URLs, WSGI, ASGI, Celery
│
├── docker/
│   └── Dockerfile.django          # Production Docker image
│
├── infrastructure/                # External service integrations
│   ├── celery/                    # Celery app & task routing
│   ├── kafka/                     # Kafka producers & consumers
│   ├── llm/                       # LLM client wrappers
│   ├── redis/                     # Redis client utilities
│   ├── storage/                   # File storage backends
│   ├── temporal/                  # Temporal workflow definitions
│   └── vectorstore/               # ChromaDB / vector store client
│
├── requirements/
│   ├── base.txt                   # Core dependencies
│   └── local.txt                  # Development extras (pytest, ruff, etc.)
│
├── tests/                         # Project-level test suite
│
├── .env.example                   # Environment variable template
├── docker-compose.yml             # Full-stack Docker Compose definition
├── Makefile                       # Developer convenience commands
└── manage.py                      # Django management entry point
```

---

## Settings Modules

| Module                      | Use case                              |
|-----------------------------|---------------------------------------|
| `base.settings.local`      | Local development (default)           |
| `base.settings.production` | Docker / production deployment        |

Override via environment variable:
```bash
DJANGO_SETTINGS_MODULE=base.settings.production python manage.py runserver
```

---

## AI Provider and document privacy

Chat uses OpenAI by default. To switch to DeepSeek or another OpenAI-compatible chat API, configure `AI_PROVIDER=openai_compatible`, `AI_BASE_URL`, `AI_API_KEY`, and `DEFAULT_LLM_MODEL`; no code changes are needed. `OPENAI_API_KEY` remains configured for document embeddings unless an embedding integration is changed separately. There is no canned-response fallback. Document text is sent to OpenAI for embeddings, and prompts/context are sent to the selected chat provider for answers. Local Chroma is persistent and telemetry is disabled. The Docker setup uses its persistent Chroma volume.
