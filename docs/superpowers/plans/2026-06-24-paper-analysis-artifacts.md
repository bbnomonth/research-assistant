# Paper Analysis Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend vertical slice for evidence-bound quick paper analysis: use parsed PDF chunks, call Qwen, validate JSON, persist an Artifact, and export Markdown.

**Architecture:** Add `Artifact` as a generic JSON-backed result table. A `PaperAnalysisService` collects first-page/method-related chunks as evidence, asks Qwen for a structured card, validates with Pydantic, and saves both structured content and evidence IDs. API endpoints expose quick analysis and Markdown export.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite, existing Qwen gateway, pytest.

---

## Tasks

- [ ] Add Artifact model/repository/schema.
- [ ] Add chunk listing by paper ID.
- [ ] Add `PaperAnalysisService.quick_analyze(paper_id)`.
- [ ] Add `/api/papers/{paper_id}/quick-analysis`.
- [ ] Add `/api/artifacts/{artifact_id}/markdown`.
- [ ] Verify tests, AST parse, ignored file checks, merge to main.

## Acceptance criteria

- [ ] Analysis uses only stored chunks as evidence.
- [ ] Qwen output is JSON-validated.
- [ ] Artifact persists type, title, JSON content and Markdown.
- [ ] API returns artifact ID and evidence page numbers.
- [ ] Markdown export works without calling the model again.
