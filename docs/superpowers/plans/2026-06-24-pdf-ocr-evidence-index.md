# PDF OCR Evidence Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PDF upload, first-60-page parsing, optional Tesseract OCR fallback, persistent background task state, and SQLite FTS5 evidence search.

**Architecture:** FastAPI accepts local PDF uploads into ignored `data/uploads`, creates a `Task`, and invokes a local parser service. PyMuPDF extracts page text first; OCR is represented behind a Tesseract service boundary and only runs when text quality is too low. Parsed chunks are stored in `paper_chunks` plus an FTS5 virtual table for evidence search.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite FTS5, PyMuPDF, Tesseract CLI, pytest.

---

## File map

```text
backend/src/research_agent/
├─ api/papers.py                 # upload, task status, evidence search endpoints
├─ db/models.py                  # Task and PaperChunk tables
├─ main.py                       # include papers router
├─ repositories/tasks.py         # task state transitions
├─ repositories/paper_chunks.py  # chunk storage and FTS search
├─ schemas/papers.py             # upload/task/search response schemas
└─ services/pdf_processing.py    # PyMuPDF/Tesseract parsing boundary

backend/tests/
├─ test_pdf_processing.py
├─ test_paper_chunks.py
├─ test_tasks.py
└─ test_paper_api.py
```

## Task 1: Task and chunk persistence

- [ ] Write failing tests for creating a task, updating status, storing chunks, and searching FTS5.
- [ ] Add `Task` and `PaperChunk` models.
- [ ] Create FTS5 table during `Database.create_schema()`.
- [ ] Implement task and chunk repositories.
- [ ] Verify tests pass and commit.

## Task 2: PDF parser service

- [ ] Write failing tests using an in-memory generated PDF with two text pages.
- [ ] Implement `PdfProcessor.extract_text_chunks(path, max_pages=60)`.
- [ ] Enforce 10 MB and 60-page defaults at service boundary.
- [ ] Add text quality detection; expose `needs_ocr`.
- [ ] Verify tests pass and commit.

## Task 3: OCR service boundary

- [ ] Write tests with a fake OCR runner so no real OCR is needed in unit tests.
- [ ] Implement Tesseract command construction using configurable executable path and `chi_sim+eng`.
- [ ] Mark OCR chunks with `is_ocr=True`.
- [ ] Keep OCR fallback optional; if OCR fails, preserve extracted text and task error message.
- [ ] Verify tests pass and commit.

## Task 4: Upload and task status API

- [ ] Write failing API tests for uploading a small PDF, rejecting non-PDF, rejecting >10 MB, and returning task status.
- [ ] Add `/api/papers/upload`, `/api/tasks/{task_id}`, and `/api/papers/{paper_id}/evidence`.
- [ ] Save uploads under ignored data directory using generated safe names.
- [ ] Run parsing synchronously in tests; production can use FastAPI background tasks.
- [ ] Verify tests pass and commit.

## Task 5: Evidence search integration and verification

- [ ] Add an endpoint test for searching text and receiving page numbers/snippets.
- [ ] Document upload limits and OCR configuration in `backend/README.md`.
- [ ] Run full tests, AST parse, ignored-file checks, and local health smoke test.
- [ ] Commit and merge to main.

## Acceptance criteria

- [ ] PDF uploads are limited to 10 MB.
- [ ] Only the first 60 pages are parsed.
- [ ] Extracted chunks persist with page numbers and OCR flags.
- [ ] FTS5 search returns snippets and page numbers.
- [ ] OCR path is configurable and not required for normal text PDFs.
- [ ] Uploads, extracted text, and SQLite files remain ignored by Git.
