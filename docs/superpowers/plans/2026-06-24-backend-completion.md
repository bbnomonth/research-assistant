# Backend Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining course-demo backend workflows defined by the approved backend design.

**Architecture:** Keep FastAPI routes thin and place workflow rules in focused services and repositories. Reuse SQLite, SSE, `Artifact`, `Task`, `PaperChunk`, and the existing model gateway; require explicit identifiers for operations where guessing could select the wrong project or paper.

**Tech Stack:** Python 3.9 (`py39232`), FastAPI, SQLAlchemy, Pydantic, LangGraph, SQLite FTS5, pytest.

---

## File Structure

- `schemas/chat.py`: add explicit `paper_id` selection for guided reading.
- `services/guided_reading.py`: evidence-bound multi-turn reading guidance.
- `services/conversations.py`: dispatch guided reading and persist its messages/artifact event.
- `api/projects.py`, `schemas/projects.py`: project/session/history management.
- `services/arxiv_import.py`: bounded arXiv PDF download and parsing orchestration.
- `api/papers.py`, `schemas/papers.py`: import and task lifecycle endpoints.
- `repositories/tasks.py`: cancel, retry, and interrupted-task recovery operations.
- `api/system.py`, `schemas/system.py`: non-secret runtime diagnostics.
- `services/structured_output.py`: one-retry structured JSON validation helper.
- `services/model_call_logging.py`: consistent redacted model-call metrics.

### Task 1: Guided Reading Workflow

**Files:**
- Create: `backend/src/research_agent/services/guided_reading.py`
- Modify: `backend/src/research_agent/schemas/chat.py`
- Modify: `backend/src/research_agent/api/chat.py`
- Modify: `backend/src/research_agent/services/conversations.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_guided_reading.py`
- Test: `backend/tests/test_chat_sse.py`

- [ ] Write service tests requiring a real paper, stored chunks, feedback, next question, evidence pages, and a completion artifact.
- [ ] Run the targeted tests and confirm failure because `GuidedReadingService` is absent.
- [ ] Implement `GuidedReadingTurn(feedback, evidence_notes, next_question, completed, learning_summary)` and validate model JSON.
- [ ] Add optional `paper_id` to `ChatRequest` and pass it through the chat API.
- [ ] Reject missing paper selection, cross-project papers, and papers without chunks before calling the model.
- [ ] Stream `evidence_collection`, `reading_guidance`, optional `artifact`, `token`, and `done` events.
- [ ] Run guided-reading and chat SSE tests until green.

### Task 2: Project and Conversation APIs

**Files:**
- Create: `backend/src/research_agent/api/projects.py`
- Create: `backend/src/research_agent/schemas/projects.py`
- Modify: `backend/src/research_agent/repositories/conversations.py`
- Modify: `backend/src/research_agent/main.py`
- Test: `backend/tests/test_project_api.py`

- [ ] Write failing tests for project list/detail/rename, session list, and ordered message history.
- [ ] Add repository methods using SQLAlchemy `select`, never raw user-built SQL.
- [ ] Implement `GET /api/projects`, `GET/PATCH /api/projects/{id}`, `GET /api/projects/{id}/sessions`, and `GET /api/sessions/{id}/messages`.
- [ ] Return 404 for unknown IDs and reject a session that does not belong to the requested project.
- [ ] Run the project API tests until green.

### Task 3: arXiv PDF Import

**Files:**
- Create: `backend/src/research_agent/services/arxiv_import.py`
- Modify: `backend/src/research_agent/api/papers.py`
- Modify: `backend/src/research_agent/schemas/papers.py`
- Test: `backend/tests/test_arxiv_import.py`
- Test: `backend/tests/test_paper_api.py`

- [ ] Write failing tests with an injected fake downloader; no network calls are allowed in tests.
- [ ] Implement streamed download with a 10 MB hard limit, PDF content validation, UUID local filename, and cleanup on failure.
- [ ] Parse at most 60 pages, replace evidence chunks, and update the persisted task status.
- [ ] Add `POST /api/papers/{paper_id}/import-pdf`; reject uploads and papers without an HTTP(S) PDF URL.
- [ ] Preserve the arXiv record when download or parsing fails and expose a failed task with a redacted message.
- [ ] Run import and paper API tests until green.

### Task 4: Task Cancellation, Retry, and Recovery

**Files:**
- Modify: `backend/src/research_agent/repositories/tasks.py`
- Modify: `backend/src/research_agent/api/papers.py`
- Modify: `backend/src/research_agent/main.py`
- Test: `backend/tests/test_tasks_and_chunks.py`
- Test: `backend/tests/test_paper_api.py`

- [ ] Write failing tests for cancellation, retry eligibility, and startup conversion of active statuses to `interrupted`.
- [ ] Add repository transition checks for `pending`, `processing`, `completed`, `failed`, `cancelled`, and `interrupted`.
- [ ] Add `POST /api/tasks/{id}/cancel` and `POST /api/tasks/{id}/retry`.
- [ ] On application startup, mark leftover active tasks interrupted without deleting paper data.
- [ ] Run task tests until green.

### Task 5: Runtime Diagnostics

**Files:**
- Create: `backend/src/research_agent/api/system.py`
- Create: `backend/src/research_agent/schemas/system.py`
- Modify: `backend/src/research_agent/main.py`
- Test: `backend/tests/test_system_api.py`

- [ ] Write failing tests for redacted settings, writable data directory, OCR probe, and model connection probe.
- [ ] Add `GET /api/system/settings` without returning API keys.
- [ ] Add `POST /api/system/check-storage`, `POST /api/system/check-ocr`, and `POST /api/system/check-model`.
- [ ] Use temporary probe files only inside the configured data directory and always remove them.
- [ ] Return actionable status objects instead of exposing exception text.
- [ ] Run system API tests until green.

### Task 6: Structured Output Repair and Unified Model Logs

**Files:**
- Create: `backend/src/research_agent/services/structured_output.py`
- Create: `backend/src/research_agent/services/model_call_logging.py`
- Modify: `backend/src/research_agent/services/literature.py`
- Modify: `backend/src/research_agent/services/paper_analysis.py`
- Modify: `backend/src/research_agent/services/research_diagnosis.py`
- Modify: `backend/src/research_agent/services/guided_reading.py`
- Test: `backend/tests/test_structured_output.py`
- Test: `backend/tests/test_model_call_logging.py`

- [ ] Write failing tests proving malformed model JSON receives exactly one repair request and valid JSON is not retried.
- [ ] Implement a generic Pydantic validation helper that accepts the first raw response, performs one repair call, then returns the caller's explicit fallback.
- [ ] Implement a context helper that writes task type, model, duration, retry count, success, and redacted error type.
- [ ] Apply both helpers to discovery, analysis, comparison, diagnosis, and guided reading.
- [ ] Run service tests and verify no prompt, paper text, API key, or raw exception message is stored in `ModelCallLog`.

### Final Verification

- [ ] Run `E:\anaconda927\envs\py39232\python.exe -m pytest backend/tests -q`.
- [ ] Parse every Python source and test file with `ast.parse`.
- [ ] Run `git diff --check`.
- [ ] Inspect `git status --short --ignored` and confirm `.env`, SQLite files, uploads, temporary files, and the original product document remain ignored.
- [ ] Update `backend/README.md` with the completed API contracts and any remaining limitations.
