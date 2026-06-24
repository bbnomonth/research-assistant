# arXiv Literature Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the literature-discovery placeholder with a real arXiv workflow that generates an English query, retrieves up to 20 genuine papers, selects 5–10 recommendations, persists metadata, and streams structured results to the client.

**Architecture:** Add a provider boundary around LangChain Community's `ArxivRetriever` so network behavior is replaceable in tests. A literature service uses the existing Qwen gateway for query generation and recommendation labeling, while authoritative bibliographic fields always come from arXiv documents and are persisted in SQLite.

**Tech Stack:** Python 3.9, FastAPI, LangGraph, LangChain Community, arxiv, Pydantic 2, SQLAlchemy 2, pytest.

---

## File map

```text
backend/
├─ pyproject.toml
├─ src/research_agent/
│  ├─ db/models.py
│  ├─ repositories/papers.py
│  ├─ schemas/literature.py
│  ├─ services/arxiv_search.py
│  ├─ services/literature.py
│  └─ services/conversations.py
└─ tests/
   ├─ test_arxiv_search.py
   ├─ test_literature_service.py
   └─ test_chat_sse.py
```

### Task 1: Dependencies, paper schema, and persistence

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/research_agent/db/models.py`
- Create: `backend/src/research_agent/repositories/papers.py`
- Create: `backend/src/research_agent/schemas/literature.py`
- Create: `backend/tests/test_papers.py`

- [ ] Write a failing test that saves the same arXiv ID twice and asserts one `Paper` row remains.
- [ ] Run `pytest backend/tests/test_papers.py -q` and verify failure because the model/repository is missing.
- [ ] Add `langchain-community>=0.3.27,<0.4` and `arxiv>=2.1,<3` dependencies.
- [ ] Add `Paper` with `arxiv_id`, title, authors JSON, abstract, published date, categories JSON, entry URL, PDF URL, project ID, recommendation reason, purpose labels JSON, and timestamps.
- [ ] Add a unique constraint on `(project_id, arxiv_id)`.
- [ ] Implement `PaperRepository.upsert_arxiv_papers(project_id, papers)` using authoritative metadata only.
- [ ] Run the paper tests and commit as `feat: persist arXiv paper metadata`.

### Task 2: LangChain arXiv provider

**Files:**
- Create: `backend/src/research_agent/services/arxiv_search.py`
- Create: `backend/tests/test_arxiv_search.py`

- [ ] Write failing tests for mapping LangChain `Document` metadata into a normalized `ArxivPaper`.
- [ ] Test that duplicate arXiv version URLs such as `2305.05665v1` and `2305.05665v2` normalize to one base ID.
- [ ] Implement `ArxivSearchProvider` protocol.
- [ ] Implement `LangChainArxivSearchProvider` with `ArxivRetriever(load_max_docs=20, get_full_documents=False)`.
- [ ] Run synchronous retriever work with `asyncio.to_thread`.
- [ ] Map only returned metadata and summary text; never let Qwen invent title, authors, dates, URLs, or IDs.
- [ ] Run provider tests and commit as `feat: add LangChain arXiv search provider`.

### Task 3: Query generation and recommendation service

**Files:**
- Modify: `backend/src/research_agent/services/model_gateway.py`
- Create: `backend/src/research_agent/services/literature.py`
- Create: `backend/tests/test_literature_service.py`

- [ ] Write a failing test where a fake gateway returns a JSON English query and JSON recommendations for fake arXiv candidates.
- [ ] Add `collect_chat()` helper that consumes the existing stream without adding another external SDK path.
- [ ] Define Pydantic schemas:

```python
class LiteratureQuery(BaseModel):
    english_query: str

class RecommendationItem(BaseModel):
    arxiv_id: str
    reason: str
    purpose_labels: list[str]

class LiteratureDiscoveryResult(BaseModel):
    query: str
    candidates: list[ArxivPaper]
    recommendations: list[RecommendedPaper]
```

- [ ] Implement robust JSON extraction from plain JSON or fenced JSON.
- [ ] If query JSON is invalid, fall back to the original user text.
- [ ] Filter recommendation IDs against actual candidate IDs.
- [ ] Deduplicate and cap recommendations at 10; if fewer than 5 valid model choices exist, fill from candidates in arXiv order with a neutral reason.
- [ ] Run service tests and commit as `feat: generate evidence-bound literature recommendations`.

### Task 4: Connect literature discovery to the chat stream

**Files:**
- Modify: `backend/src/research_agent/main.py`
- Modify: `backend/src/research_agent/services/conversations.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_chat_sse.py`

- [ ] Write a failing SSE test asserting a literature query emits `mode`, `metadata`, `stage`, `search_results`, `token`, and `done`.
- [ ] Inject the arXiv provider through `create_app`; production uses `LangChainArxivSearchProvider`, tests use a fake provider.
- [ ] In `ConversationService`, execute `LiteratureDiscoveryService` for `literature_discovery`.
- [ ] Emit stages for query generation, arXiv retrieval, recommendation, and persistence.
- [ ] Persist selected papers under the auto-created project.
- [ ] Store a concise assistant summary message without duplicating all abstracts in chat history.
- [ ] Preserve the existing placeholder behavior for paper reading and research diagnosis.
- [ ] Run the complete test suite and commit as `feat: stream arXiv literature discovery results`.

### Task 5: Verification and real arXiv smoke test

**Files:**
- Modify: `backend/README.md`

- [ ] Document the literature-discovery SSE event payload and arXiv rate-limit behavior.
- [ ] Run `pytest backend/tests -q`.
- [ ] Run AST parsing over all Python files.
- [ ] Verify `.env`, SQLite, logs, uploaded documents, and fetched PDFs remain ignored.
- [ ] Perform one real arXiv search for `"vehicle routing" AND "machine learning"` with at most 3 results.
- [ ] Perform one local API request using the configured Qwen key and confirm genuine arXiv IDs appear in `search_results`.
- [ ] Do not download PDFs in this phase.
- [ ] Commit as `docs: document arXiv literature discovery`.

## Acceptance criteria

- [ ] Chinese research topics can be converted into an English arXiv query.
- [ ] arXiv returns at most 20 candidates.
- [ ] The service recommends 5–10 genuine candidates.
- [ ] Every returned title, author, date, abstract, URL, and arXiv ID originates from arXiv.
- [ ] Duplicate versions are collapsed by base arXiv ID.
- [ ] Results are persisted under the active project.
- [ ] SSE exposes progress and structured search results.
- [ ] arXiv failure emits a safe error without disabling normal Q&A.
- [ ] No PDF is downloaded during literature discovery.
- [ ] All tests pass without live network or paid model calls.
