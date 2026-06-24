# Backend Foundation Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable FastAPI backend that persists projects and conversations, routes chat modes through LangGraph, calls Qwen through the OpenAI-compatible API, and streams normal research answers over SSE.

**Architecture:** Use a small FastAPI application factory, SQLAlchemy 2.0 repositories over SQLite, and dependency-injected model gateways. A LangGraph router owns mode selection and dispatch, while the first vertical slice fully implements normal research Q&A; literature discovery, paper reading, and diagnosis are represented by stable modes but receive dedicated implementation plans later.

**Tech Stack:** Python 3.9, FastAPI, Pydantic 2, SQLAlchemy 2, LangGraph, OpenAI Python SDK, SQLite, pytest, FastAPI TestClient.

---

## Scope and follow-on plans

This plan intentionally implements the common backend foundation and one complete path:

```text
HTTP request
→ auto-create project/session
→ persist user message
→ classify mode
→ execute LangGraph normal-QA node
→ stream Qwen tokens as SSE
→ persist assistant message
→ record a sanitized model-call log
```

The remaining backend is split into later plans:

1. arXiv literature discovery and import;
2. PDF upload, parsing, OCR, tasks, chunks, and FTS5 evidence search;
3. guided reading, quick analysis, comparison, diagnosis, artifacts, and Markdown export.

## File map

```text
backend/
├─ pyproject.toml                 # package metadata, runtime and test dependencies
├─ .env.example                  # non-secret configuration template
├─ README.md                     # setup, run and test commands
├─ src/research_agent/
│  ├─ __init__.py
│  ├─ main.py                    # FastAPI application factory
│  ├─ config.py                  # environment-backed settings and path resolution
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ dependencies.py         # database and service dependency providers
│  │  ├─ health.py               # health/readiness endpoints
│  │  └─ chat.py                 # chat request and SSE endpoint
│  ├─ db/
│  │  ├─ __init__.py
│  │  ├─ base.py                 # SQLAlchemy declarative base
│  │  ├─ engine.py               # engine/session factory and schema initialization
│  │  └─ models.py               # Project, Session, Message, ModelCallLog
│  ├─ repositories/
│  │  ├─ __init__.py
│  │  └─ conversations.py        # project/session/message persistence operations
│  ├─ schemas/
│  │  ├─ __init__.py
│  │  └─ chat.py                 # request, mode and SSE event schemas
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ model_gateway.py        # model protocol and Qwen OpenAI implementation
│  │  └─ conversations.py        # chat orchestration and persistence
│  └─ workflows/
│     ├─ __init__.py
│     └─ router.py               # rule-first mode classification and LangGraph
└─ tests/
   ├─ conftest.py                # temporary SQLite app and fake model fixtures
   ├─ test_config.py
   ├─ test_health.py
   ├─ test_conversations.py
   ├─ test_router.py
   └─ test_chat_sse.py
```

### Task 1: Package scaffold and safe configuration

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/src/research_agent/__init__.py`
- Create: `backend/src/research_agent/config.py`
- Create: `backend/tests/test_config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing settings test**

```python
# backend/tests/test_config.py
from pathlib import Path

from research_agent.config import Settings


def test_settings_resolve_data_paths_from_app_root(tmp_path: Path) -> None:
    settings = Settings(
        app_root=tmp_path,
        database_path=Path("data/app.sqlite3"),
        upload_dir=Path("data/uploads"),
        qwen_api_key=None,
    )

    assert settings.resolved_database_path == tmp_path / "data/app.sqlite3"
    assert settings.resolved_upload_dir == tmp_path / "data/uploads"
    assert settings.qwen_model == "qwen3.7-plus"
    assert settings.pdf_max_bytes == 10 * 1024 * 1024
    assert settings.pdf_max_pages == 60
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_config.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'research_agent'`.

- [ ] **Step 3: Add package metadata and dependencies**

```toml
# backend/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "research-training-agent-backend"
version = "0.1.0"
requires-python = ">=3.9,<3.10"
dependencies = [
  "fastapi==0.128.8",
  "httpx==0.28.1",
  "langgraph>=0.2,<0.3",
  "openai==1.109.1",
  "pydantic==2.12.2",
  "python-multipart==0.0.20",
  "SQLAlchemy==2.0.43",
  "uvicorn==0.39.0",
]

[project.optional-dependencies]
test = ["pytest==8.4.2"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 4: Implement the minimal settings object**

```python
# backend/src/research_agent/config.py
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Settings:
    app_root: Path = Path(__file__).resolve().parents[3]
    database_path: Path = Path("data/app.sqlite3")
    upload_dir: Path = Path("data/uploads")
    qwen_api_key: Optional[str] = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.7-plus"
    pdf_max_bytes: int = 10 * 1024 * 1024
    pdf_max_pages: int = 60

    @property
    def resolved_database_path(self) -> Path:
        return self._resolve(self.database_path)

    @property
    def resolved_upload_dir(self) -> Path:
        return self._resolve(self.upload_dir)

    def _resolve(self, value: Path) -> Path:
        return value if value.is_absolute() else self.app_root / value

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_root=Path(os.getenv("APP_ROOT", Path.cwd())),
            database_path=Path(os.getenv("DATABASE_PATH", "data/app.sqlite3")),
            upload_dir=Path(os.getenv("UPLOAD_DIR", "data/uploads")),
            qwen_api_key=os.getenv("DASHSCOPE_API_KEY"),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            qwen_model=os.getenv("QWEN_MODEL", "qwen3.7-plus"),
        )
```

Add `backend/.env.example` with names only and no real credentials:

```dotenv
DASHSCOPE_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen3.7-plus
DATABASE_PATH=data/app.sqlite3
UPLOAD_DIR=data/uploads
```

Extend `.gitignore` with:

```gitignore
backend/*.egg-info/
backend/src/*.egg-info/
```

- [ ] **Step 5: Install the editable package and run GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pip install -e 'backend[test]'
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_config.py -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore backend
git commit -m "build: scaffold backend package and settings"
```

### Task 2: SQLite schema and session lifecycle

**Files:**
- Create: `backend/src/research_agent/db/__init__.py`
- Create: `backend/src/research_agent/db/base.py`
- Create: `backend/src/research_agent/db/models.py`
- Create: `backend/src/research_agent/db/engine.py`
- Create: `backend/tests/test_conversations.py`

- [ ] **Step 1: Write the failing schema test**

```python
# backend/tests/test_conversations.py
from sqlalchemy import inspect

from research_agent.db.engine import Database


def test_database_creates_foundation_tables(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()

    names = set(inspect(database.engine).get_table_names())

    assert {"projects", "sessions", "messages", "model_call_logs"} <= names
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversations.py -q
```

Expected: import fails because `research_agent.db.engine` does not exist.

- [ ] **Step 3: Implement the schema**

Use SQLAlchemy 2.0 declarative models with string UUID primary keys and timezone-aware UTC timestamps:

```python
# backend/src/research_agent/db/base.py
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

```python
# backend/src/research_agent/db/models.py
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), default="未命名项目")
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ConversationSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    mode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ModelCallLog(Base):
    __tablename__ = "model_call_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_type: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    duration_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
```

```python
# backend/src/research_agent/db/engine.py
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .base import Base
from . import models  # noqa: F401


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversations.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/research_agent/db backend/tests/test_conversations.py
git commit -m "feat: add SQLite foundation schema"
```

### Task 3: Conversation repository and automatic project creation

**Files:**
- Create: `backend/src/research_agent/repositories/__init__.py`
- Create: `backend/src/research_agent/repositories/conversations.py`
- Modify: `backend/tests/test_conversations.py`

- [ ] **Step 1: Add a failing repository test**

```python
from research_agent.repositories.conversations import ConversationRepository


def test_repository_auto_creates_project_session_and_messages(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.create_schema()
    with database.session_factory() as db:
        repo = ConversationRepository(db)
        project, session = repo.ensure_conversation(None, None)
        user_message = repo.add_message(session.id, "user", "解释强化学习")
        assistant_message = repo.add_message(
            session.id,
            "assistant",
            "强化学习通过奖励信号学习策略。",
            mode="general_qa",
        )
        db.commit()

        assert project.name == "未命名项目"
        assert user_message.session_id == session.id
        assert assistant_message.mode == "general_qa"
        assert [m.role for m in repo.list_recent_messages(session.id, 20)] == [
            "user",
            "assistant",
        ]
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversations.py::test_repository_auto_creates_project_session_and_messages -q
```

Expected: import fails because the repository does not exist.

- [ ] **Step 3: Implement repository operations**

Implement:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple

from research_agent.db.models import ConversationSession, Message, Project


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_conversation(
        self,
        project_id: Optional[str],
        session_id: Optional[str],
    ) -> Tuple[Project, ConversationSession]:
        if project_id is None:
            project = Project()
            self.db.add(project)
            self.db.flush()
        else:
            project = self.db.get(Project, project_id)
            if project is None:
                raise LookupError("project not found")

        if session_id is None:
            conversation = ConversationSession(project_id=project.id)
            self.db.add(conversation)
            self.db.flush()
        else:
            conversation = self.db.get(ConversationSession, session_id)
            if conversation is None or conversation.project_id != project.id:
                raise LookupError("session not found for project")

        return project, conversation

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        mode: Optional[str] = None,
    ) -> Message:
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            mode=mode,
        )
        self.db.add(message)
        self.db.flush()
        return message

    def list_recent_messages(self, session_id: str, limit: int) -> List[Message]:
        statement = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(self.db.scalars(statement))
        messages.reverse()
        return messages
```

Required behavior:

- unknown non-null project or session IDs raise `LookupError`;
- a missing project ID creates `未命名项目`;
- a missing session ID creates a session under the selected project;
- recent messages are returned oldest-to-newest after applying the limit;
- repository methods flush but do not commit, leaving transaction ownership to the service.

- [ ] **Step 4: Run all repository tests and verify GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversations.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/research_agent/repositories backend/tests/test_conversations.py
git commit -m "feat: persist projects and conversations"
```

### Task 4: Rule-first mode router and LangGraph dispatch

**Files:**
- Create: `backend/src/research_agent/schemas/__init__.py`
- Create: `backend/src/research_agent/schemas/chat.py`
- Create: `backend/src/research_agent/workflows/__init__.py`
- Create: `backend/src/research_agent/workflows/router.py`
- Create: `backend/tests/test_router.py`

- [ ] **Step 1: Write failing rule-router tests**

```python
# backend/tests/test_router.py
import pytest

from research_agent.schemas.chat import ChatMode
from research_agent.workflows.router import classify_mode


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("帮我搜索物流调度相关论文", ChatMode.LITERATURE_DISCOVERY),
        ("分析我刚上传的这篇PDF", ChatMode.PAPER_READING),
        ("这个选题和研究框架合理吗", ChatMode.RESEARCH_DIAGNOSIS),
        ("什么是混合整数规划", ChatMode.GENERAL_QA),
    ],
)
def test_rule_first_classification(message, expected) -> None:
    assert classify_mode(message) is expected
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_router.py -q
```

Expected: imports fail because chat schemas and router are missing.

- [ ] **Step 3: Implement stable chat modes and classifier**

```python
# backend/src/research_agent/schemas/chat.py
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ChatMode(str, Enum):
    GENERAL_QA = "general_qa"
    LITERATURE_DISCOVERY = "literature_discovery"
    PAPER_READING = "paper_reading"
    RESEARCH_DIAGNOSIS = "research_diagnosis"


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    mode_override: Optional[ChatMode] = None
```

Implement `classify_mode()` with explicit Chinese and English keyword sets. Add a `TypedDict` graph state and compile a LangGraph whose router node dispatches to four named nodes. In this phase:

- `general_qa` returns control to the conversation service for model streaming;
- the other nodes return a stable `not_implemented` workflow result, not an exception;
- `mode_override` always wins over classification.

- [ ] **Step 4: Add and pass graph dispatch tests**

Add tests asserting:

```python
result = graph.invoke({"content": "搜索人工智能论文"})
assert result["mode"] == ChatMode.LITERATURE_DISCOVERY
assert result["workflow_status"] == "not_implemented"
```

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_router.py -q
```

Expected: all router and graph tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/research_agent/schemas backend/src/research_agent/workflows backend/tests/test_router.py
git commit -m "feat: add LangGraph chat mode router"
```

### Task 5: Qwen model gateway with streaming and sanitized logs

**Files:**
- Create: `backend/src/research_agent/services/__init__.py`
- Create: `backend/src/research_agent/services/model_gateway.py`
- Create: `backend/tests/test_model_gateway.py`

- [ ] **Step 1: Write failing fake-gateway and message-shaping tests**

```python
# backend/tests/test_model_gateway.py
import asyncio

from research_agent.services.model_gateway import FakeModelGateway, build_qwen_messages


def test_build_qwen_messages_keeps_only_recent_context() -> None:
    history = [
        {"role": "user", "content": f"question-{i}"}
        for i in range(25)
    ]
    messages = build_qwen_messages(history, "latest", history_limit=20)

    assert messages[0]["role"] == "system"
    assert messages[-1] == {"role": "user", "content": "latest"}
    assert all("question-0" not in item["content"] for item in messages)


def test_fake_gateway_streams_tokens() -> None:
    async def collect() -> list[str]:
        gateway = FakeModelGateway(["第一段", "第二段"])
        return [token async for token in gateway.stream_chat([])]

    assert asyncio.run(collect()) == ["第一段", "第二段"]
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_model_gateway.py -q
```

Expected: import fails because the model gateway does not exist.

- [ ] **Step 3: Implement the gateway boundary**

Define:

```python
class ModelGateway(Protocol):
    model_name: str

    def stream_chat(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        pass
```

Implement:

- `FakeModelGateway` for deterministic tests;
- `QwenOpenAIGateway` using `AsyncOpenAI(api_key=api_key, base_url=base_url)`;
- `stream_chat()` using `chat.completions.create(model=self.model_name, messages=messages, stream=True)`;
- at most one retry before emitting a typed `ModelGatewayError`;
- `build_qwen_messages()` with the research-coach system instruction and at most 20 recent messages;
- no API key, full prompt, or paper text in exception messages.

Do not make a live API call in automated tests.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_model_gateway.py -q
```

Expected: all gateway tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/research_agent/services backend/tests/test_model_gateway.py
git commit -m "feat: add Qwen streaming gateway"
```

### Task 6: Conversation service and SSE event contract

**Files:**
- Modify: `backend/src/research_agent/schemas/chat.py`
- Create: `backend/src/research_agent/services/conversations.py`
- Create: `backend/tests/test_conversation_service.py`

- [ ] **Step 1: Write a failing service-stream test**

```python
# backend/tests/test_conversation_service.py
import asyncio

from research_agent.services.conversations import ConversationService
from research_agent.services.model_gateway import FakeModelGateway


def test_service_streams_mode_tokens_and_done(database) -> None:
    async def collect():
        with database.session_factory() as db:
            service = ConversationService(
                db=db,
                model_gateway=FakeModelGateway(["回答", "内容"]),
            )
            return [
                event async for event in service.stream_reply(content="什么是排队论")
            ]

    events = asyncio.run(collect())

    assert [event.event for event in events] == [
        "mode",
        "metadata",
        "token",
        "token",
        "done",
    ]
    assert events[-1].data["content"] == "回答内容"
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversation_service.py -q
```

Expected: import fails because the conversation service is missing.

- [ ] **Step 3: Implement typed events and transactional persistence**

Add:

```python
class StreamEvent(BaseModel):
    event: str
    data: dict

    def to_sse(self) -> str:
        return f"event: {self.event}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"
```

Implement `ConversationService.stream_reply()` so it:

1. creates or loads project/session;
2. persists the user message and commits before model execution;
3. classifies or applies mode override;
4. emits `mode` and `metadata` containing project/session IDs;
5. streams normal-QA tokens from the gateway;
6. accumulates and persists the final assistant message;
7. writes a sanitized `ModelCallLog`;
8. emits `done`;
9. on failure, rolls back the active transaction, writes a failed log in a fresh transaction, and emits a safe `error` event.

For non-implemented modes, emit a Chinese explanatory token and `done`; do not call Qwen until their dedicated workflows exist.

- [ ] **Step 4: Run service tests and verify GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_conversation_service.py backend/tests/test_conversations.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/research_agent/schemas/chat.py backend/src/research_agent/services/conversations.py backend/tests
git commit -m "feat: orchestrate persistent streaming conversations"
```

### Task 7: FastAPI app, health endpoints, and chat SSE endpoint

**Files:**
- Create: `backend/src/research_agent/api/__init__.py`
- Create: `backend/src/research_agent/api/dependencies.py`
- Create: `backend/src/research_agent/api/health.py`
- Create: `backend/src/research_agent/api/chat.py`
- Create: `backend/src/research_agent/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/tests/test_chat_sse.py`

- [ ] **Step 1: Write failing API tests**

```python
# backend/tests/test_health.py
def test_health_reports_database_and_model_configuration(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "model_configured": False,
    }
```

```python
# backend/tests/test_chat_sse.py
def test_chat_endpoint_streams_sse_and_persists_ids(client) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"content": "什么是运筹学"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: mode" in body
    assert '"mode": "general_qa"' in body
    assert "event: token" in body
    assert "event: done" in body
    assert '"project_id":' in body
    assert '"session_id":' in body
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_health.py backend/tests/test_chat_sse.py -q
```

Expected: fixture or application imports fail because the API has not been implemented.

- [ ] **Step 3: Implement the application factory and dependency overrides**

`create_app(settings, model_gateway=None)` must:

- create data directories;
- initialize the SQLite schema during lifespan startup;
- store `settings`, `database`, and `model_gateway` on `app.state`;
- use `FakeModelGateway` only when explicitly injected by tests;
- return HTTP 503 for normal Q&A if no API key is configured in real runtime;
- include `/api/health` and `/api/chat/stream`.

Use `StreamingResponse`:

```python
return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    },
)
```

- [ ] **Step 4: Run API tests and verify GREEN**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests/test_health.py backend/tests/test_chat_sse.py -q
```

Expected: all API tests pass.

- [ ] **Step 5: Run the entire test suite**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests -q
```

Expected: all tests pass with no warnings.

- [ ] **Step 6: Commit**

```powershell
git add backend/src/research_agent/api backend/src/research_agent/main.py backend/tests
git commit -m "feat: expose health and SSE chat APIs"
```

### Task 8: Runtime documentation, privacy verification, and smoke test

**Files:**
- Create: `backend/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write the runtime instructions**

Document exact Windows commands:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pip install -e 'backend[test]'
$env:DASHSCOPE_API_KEY='your-local-key'
& 'E:\anaconda927\envs\py39232\python.exe' -m uvicorn research_agent.main:app --app-dir backend/src --reload
```

Document:

- API docs URL: `http://127.0.0.1:8000/docs`;
- health URL: `http://127.0.0.1:8000/api/health`;
- API keys belong in environment variables or a local ignored `.env`;
- SQLite data is stored under ignored `data/`;
- the first phase fully supports normal Q&A, while the other routed modes return a stable “under construction” result.

- [ ] **Step 2: Add local runtime ignores**

Ensure `.gitignore` covers:

```gitignore
backend/data/
backend/.env
backend/*.egg-info/
backend/src/*.egg-info/
```

- [ ] **Step 3: Verify tests, imports, and staged privacy**

Run:

```powershell
& 'E:\anaconda927\envs\py39232\python.exe' -m pytest backend/tests -q
& 'E:\anaconda927\envs\py39232\python.exe' -c "from research_agent.main import app; print(app.title)"
git diff --check
git status --short --ignored
```

Expected:

- all tests pass;
- app title prints;
- `git diff --check` has no output;
- `.env`, database files, uploaded documents, logs, and original `.docx` remain ignored.

- [ ] **Step 4: Start the API and perform a local health smoke test**

Run the server in a hidden background process, request `/api/health`, then stop that exact process. Expected JSON:

```json
{"status":"ok","database":"ok","model_configured":false}
```

Do not perform a paid Qwen request unless the user has provided a local API key and explicitly wants a live integration test.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore backend/README.md
git commit -m "docs: add backend setup and privacy guidance"
```

## Final verification checklist

- [ ] `pytest backend/tests -q` passes.
- [ ] `git diff --check` produces no errors.
- [ ] `git status --short --ignored` shows no secrets or runtime data tracked.
- [ ] `/api/health` responds from a real local Uvicorn process.
- [ ] `/api/chat/stream` passes the fake-gateway integration test.
- [ ] No automated test sends a live request to Qwen.
- [ ] All new service and repository behavior was introduced by a failing test first.
- [ ] A code review checks the implementation against this plan and the backend design spec.
