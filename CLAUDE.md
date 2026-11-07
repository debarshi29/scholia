# CLAUDE.md: Scholia

Scholia is a single-user, local-first platform for practising **AI-assisted code comprehension interview rounds**. In a session you get an unfamiliar 150-500 line Python codebase and 60 minutes. You find bugs and write design notes, helped by a **deliberately weak** local AI assistant. You then get a graded debrief against a **test-verified answer key**.

The skill being trained is reading code and verifying what an AI tells you. Every design choice serves that. If a change would make the assistant more helpful, or reveal the answer more easily, it is wrong unless the owner asks for it.

Owner: Debarshi. The machine is a laptop with an RTX 3050 (6 GB VRAM), so everything runs locally except Gemini API calls.

---

## 1. Scope

### v1 (milestones M0-M5)
- Python problems only.
- The corpus comes from **Tier 0 datasets** (SWE-bench Lite, BugsInPy) and is converted automatically. There is no manual curation.
- Web UI with three pages: **Library** (pick a problem and session settings), **Session** (code viewer, assistant, report form) and **Debrief** (results).
- Two assistant modes:
  - **Constrained** (the default): local Qwen2.5-Coder via Ollama. It sees only the lines you select, has a token cap (default 3072) and a question budget (default 12).
  - **Realistic**: Gemini, with the whole file in context and no budget.
- **Grading** happens in three steps: deterministic line matching, then a Gemini judge with a fixed rubric, then an audit of the assistant's claims.
- **Tracking**: miss rate per bug category, which weights the next problem pick.

### Explicitly NOT in v1. Do not build these unless asked.
- Users, auth, accounts, or hosted deployment.
- Languages other than Python.
- Running code during a session. There is no run-tests button yet.
- The Tier 1 GitHub miner, Tier 2 mutation, and Tier 3 LLM-planted bugs. These are M6 and later.
- The Docker verifier (M6). Tier 0 relies on the upstream dataset's own verification.
- The system design canvas mode (M7).
- A Rust rewrite. That is a possible later milestone, after M5.

If a task seems to need any of these, stop and ask.

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2, pydantic-settings |
| DB | SQLite via SQLModel (one file: `data/scholia.db`), async through SQLAlchemy's asyncio extension + `aiosqlite` |
| Local model | Ollama, model `qwen2.5-coder:3b` (7B is the ceiling for 6 GB VRAM), reached through its OpenAI-compatible endpoint `http://localhost:11434/v1` |
| Cloud model | Gemini via the `google-genai` SDK. The model name comes only from config. |
| LLM client | Thin internal adapter (`api/backends/`) over the OpenAI-compatible API. Do not add LiteLLM unless asked. |
| Tokenizer | HF `tokenizers` / `transformers` AutoTokenizer for `Qwen/Qwen2.5-Coder-3B-Instruct` (exact counts for the cap). Gemini counts are approximate. |
| Retries | tenacity (exponential backoff on 429 and 5xx) |
| Datasets | Hugging Face `datasets` (SWE-bench Lite), git clone of the BugsInPy repo |
| Git ops | GitPython |
| Frontend | React + Vite + TypeScript, Tailwind CSS, `@monaco-editor/react`, TanStack Query, Zustand |
| Tooling | uv (Python), pnpm (web), ruff (lint and format), pytest (async tests via the anyio plugin), `httpx` (API tests through `ASGITransport`), mypy (strict on `schema/` and `api/grader/`) |

Pin versions in `uv.lock` and `pnpm-lock.yaml`. **Ask before adding any dependency** that is not in this table.

---

## 3. Repo layout

```
scholia/
  CLAUDE.md
  README.md
  pyproject.toml            # uv-managed; packages: schema, corpus, api
  .env.example
  schema/                   # SINGLE SOURCE OF TRUTH for shared types
    taxonomy.py             # BugCategory enum
    answer.py               # AnswerKey, Bug, DesignNote
    report.py               # Report, Finding
    problem.py              # ProblemMeta
    session.py              # AssistantMode
    grading.py              # OutcomeStatus, ClaimVerdict
  corpus/
    sources/
      swebench.py           # Tier 0
      bugsinpy.py           # Tier 0
    filters.py              # line counts, file counts, licence allowlist
    sanitise.py             # strip hints
    publish.py              # write problems/<id>/ + index row
    build.py                # CLI: python -m corpus.build --tier 0 --source swebench --limit 20
  api/
    main.py                 # FastAPI app, routers
    config.py               # pydantic-settings
    db.py                   # SQLModel async engine + tables + get_db dependency
    log.py                  # JSON log formatter
    sessions.py             # picker, server-side clock, report intake
    proxy.py                # assistant proxy (ALL constraints enforced here)
    tokens.py               # token counting
    backends/
      base.py               # ChatBackend protocol
      ollama.py
      gemini.py
    grader/
      match.py              # deterministic matching
      judge.py              # Gemini rubric scoring
      audit.py              # assistant-claim audit
      prompts/              # judge + audit prompt templates (versioned files)
    tracker.py
  web/                      # React app
    src/pages/{Library,Session,Debrief}.tsx
    src/components/
    src/api/                # typed client generated from FastAPI OpenAPI
  problems/                 # generated; git-ignored except problems/_seed/
  data/                     # sqlite db, logs; git-ignored
  tests/
    fixtures/graded/        # hand-graded reports used to test the grader
```

---

## 4. Commands

```bash
# setup
uv sync
cd web && pnpm install && cd ..
ollama pull qwen2.5-coder:3b
cp .env.example .env            # then add GEMINI_API_KEY

# run
uv run uvicorn api.main:app --reload --port 8000
cd web && pnpm dev               # http://localhost:5173, proxies /api to :8000

# corpus
uv run python -m corpus.build --tier 0 --source swebench --limit 20
uv run python -m corpus.build --tier 0 --source bugsinpy --limit 20
uv run python -m corpus.build --tier 0 --source swebench --limit 20 --dry-run   # checks only, no Gemini

# quality
uv run ruff check . && uv run ruff format --check .
uv run mypy schema api/grader
uv run pytest -q
cd web && pnpm typecheck && pnpm lint

# regenerate the frontend API client after any API change
cd web && pnpm gen:api
```

Before calling a task done, run `ruff`, `mypy` and `pytest` (plus web `typecheck` if you touched `web/`), and report the results.

---

## 5. Core invariants. Never break these.

1. **The answer key never reaches the client before submit.** `answer.json` and `tests/` are never served by any endpoint that a live session can call. The debrief endpoint returns answer data only for sessions with `submitted_at` set. Write a test for this.
2. **The assistant proxy is the only path to a model during a session.** The frontend never calls Ollama or Gemini directly. All checks live in `api/proxy.py`.
3. **Constrained mode checks, in this order:**
   1. A selection exists. Requests without a line range are refused.
   2. The token count of the selected lines plus the fixed prompt overhead is at most `ctx_cap`, measured with the real Qwen tokenizer.
   3. `questions_used < q_budget`.
   - A refusal costs no budget, but **is logged** with its reason.
4. **The proxy sends only the selected lines** in Constrained mode. It never adds the rest of the file, other files or the problem metadata. The system prompt says the model is a code assistant seeing a fragment. It must not mention bugs, an interview, or that bugs exist.
5. **The server owns the clock.** `started_at` is stored server-side. The UI timer is display only. Submission after 60:00 is accepted but flagged `overtime`.
6. **Every assistant exchange is logged**: session, file, line range, token count, question, reply, model, latency, and any refusal reason.
7. **Only open-source code goes to Gemini.** Problems come from permissive-licence public repos (check `meta.json.licence` against the allowlist in `corpus/filters.py`). Never send anything from outside `problems/`.
8. **Problems are immutable once published.** A fix creates a new `version`. Sessions reference `(problem_id, version)`.
9. **Matching is deterministic. The LLM only scores.** The judge never decides whether a finding matched a bug.
10. **Model names, caps and budgets come only from config.** No hard-coded model strings in logic.

---

## 6. Data contracts

### Problem folder
Each published version has its own immutable directory (invariant 8), so older sessions can still be debriefed against the version they used.
```
problems/P-0001/v1/
  src/            # served files, sanitised (repo-relative paths kept)
  answer.json     # hidden until submit
  meta.json       # tier, source, upstream_id, origin repo, commit, licence, line_count, file_count
  tests/          # verifying tests, never served
```

### Bug taxonomy (`schema/taxonomy.py`). Changing it is a migration, so ask first.
`logic`, `boundary`, `null_empty`, `shared_mutable_state`, `concurrency`, `resource_leak`, `error_handling`, `complexity`

### answer.json
```json
{
  "problem_id": "P-0001",
  "version": 1,
  "bugs": [{
    "id": "b1",
    "file": "worker.py",
    "lines": [30, 36],
    "category": "concurrency",
    "severity": "high",
    "mechanism": "Lock released only on success; an exception leaves it held.",
    "fix_diff": "--- a/worker.py\n+++ b/worker.py\n...",
    "killing_test": "tests/test_worker.py::test_retry_releases_lock"
  }],
  "design_notes": ["Retry policy is hard-coded; inject it."]
}
```
Tier 0 conversions usually have a single bug. `category` is assigned by a Gemini classification pass during corpus build, stored with `category_source: "llm"` so it can be reviewed later. Severity defaults to `medium`.

### Report (submitted by the user)
`findings[]`: `{file, line_from, line_to, category, explanation, fix}`, plus `design_notes: str`.

### SQLite tables
| Table | Key columns |
|---|---|
| problems | id, version, tier, source, files, lines, categories, published_at |
| sessions | id, problem_id, problem_version, mode, ctx_cap, q_budget, started_at, submitted_at, overtime |
| queries | id, session_id, seq, file, line_from, line_to, tokens, question, reply, model, latency_ms, refused_reason |
| findings | id, session_id, file, line_from, line_to, category, explanation, fix |
| outcomes | session_id, bug_id, finding_id, status (`found` / `partial` / `missed` / `extra`), assisted, judge_mechanism, judge_fix |
| claim_audits | query_id, verdict (`correct` / `wrong` / `unverifiable`), relied_on, rationale |
| category_stats | category, attempts, misses, updated_at |

---

## 7. Component specs

### Corpus Tier 0 (`corpus/sources/`)
- **SWE-bench Lite:** load it from Hugging Face. For each instance, check out `repo@base_commit` (shallow clone, cached under `data/repos/`). Take the **source file(s) the gold `patch` touches**, excluding test files. Keep the instance only if it touches 1-2 source files and each file is 150-500 lines. v1 does no cropping (78 of 300 SWE-bench Lite instances fit as-is). `lines` in the answer key come from the patch hunks, mapped to buggy-version line numbers.
- **BugsInPy:** same idea, using each bug's patch against the buggy commit.
- Check each dataset's actual field names and licence when you implement it. Do not assume them from this file.
- **Sanitise** (`sanitise.py`): remove comments that mention the fix, TODO/FIXME/XXX on the bug's lines, and issue numbers. Never alter code semantics, and keep line numbers stable. Replace a removed comment line with an empty line rather than deleting it.
- `--limit N` is the number of problems to **publish**; candidates are scanned in dataset order until N are kept. `--dry-run` runs every deterministic check and publishes nothing.
- Patch hunk headers can be off from `base_commit` (git tolerates offsets), so changed lines are located by hunk content, not by header numbers. Lines end at `
` only (`str.splitlines()` also splits on form feeds).
- Every build run writes a summary (candidates, kept, dropped by reason) to `data/logs/`.

### Session API (`api/sessions.py`)
- `GET /api/problems`: list with stats. No answer data.
- `POST /api/sessions` `{problem_id?, mode, ctx_cap, q_budget}`: if `problem_id` is missing, use the weighted picker.
- `GET /api/sessions/{id}`: files (src only), settings, time left, questions used.
- `POST /api/sessions/{id}/ask` `{file, line_from, line_to, question}`: goes to the proxy.
- `POST /api/sessions/{id}/submit` `{findings, design_notes}`: freezes the report and runs grading in a background task.
- `GET /api/sessions/{id}/debrief`: returns 409 until submitted and graded.
- **Picker:** weight each unattempted problem by the sum of the user's miss rates over its categories, with a small exploration floor so unseen categories still come up.

### Assistant proxy (`api/proxy.py`)
- It enforces invariants 2-4 and 6.
- Realistic mode sends the whole file the selection is in (or the whole problem if nothing is selected) to Gemini. It has no budget but is still logged.
- The token overhead is the system prompt plus the template tokens, computed once at startup.

### Grader (`api/grader/`)
1. **match.py:** a finding matches a bug when the file is equal and the line ranges overlap after widening the bug by ±3 lines. Assignment is one-to-one, greedy by overlap size. Unmatched bugs get `missed` and unmatched findings get `extra`. Pure functions, fully unit-tested.
2. **judge.py:** for each matched pair, Gemini scores `mechanism` 0-2 and `fix` 0-2 against `answer.json`. Status is `found` if mechanism is 2, otherwise `partial`. It also scores design notes 0-3. Output is strict JSON validated by Pydantic. On a parse failure, retry once and then mark it `ungraded`. Never guess a score.
3. **audit.py:** for each assistant reply, the judge labels it `correct`, `wrong` or `unverifiable` against the answer key. `relied_on` is true when a `wrong` claim about lines X is followed by the user not reporting a key bug that overlaps X (or reporting an incorrect explanation there).
4. **assisted:** a found bug is `assisted` if any query's line range overlapped it before the finding was made. Without timestamps per finding in v1, use "any query overlapped it".
- Prompts live as files in `grader/prompts/` with a version header. Store the prompt version on every outcome row.

### Tracker
After grading, update `category_stats` from that session's key bugs (each attempt adds to attempts, each miss adds to misses).

---

## 8. Frontend

The approved mockups are on the design canvas (boards: Library, Session, Debrief, Architecture). Follow them:
- **Dark IDE look:** background `#0E1116`, panels `#151A21`, borders `#2A333F`, text `#E6EAF0` / `#9AA6B5`, accent cyan `#5CC8E8`, amber `#F2B24A` (timer, Realistic mode), coral `#FF7A6B` (flags and misses), green `#6FD08C`. Fonts are IBM Plex Sans for UI and IBM Plex Mono for code and numbers.
- **Session:** a file tree on the left. In the centre, read-only Monaco with the line selection driving the "Ask assistant" and "Flag as bug" actions, plus decorations for flagged lines. On the right, the assistant panel with a context-window bar, budget pips, the thread, and refusal notices. The report form sits under the editor.
- **Library:** weak-spot bars, source filters, problem cards, and the session setup panel.
- **Debrief:** stat tiles, answer key against your findings, assistant claim audit, judge notes, and the change in category stats.
- **Accessibility:** real buttons and labels, 44 px touch targets, and visible focus rings.

---

## 9. Config (`.env.example`)

```
GEMINI_API_KEY=
JUDGE_MODEL=                  # a free-tier Gemini Flash model name
REALISTIC_MODEL=              # usually same as JUDGE_MODEL
OLLAMA_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL=qwen2.5-coder:3b
LOCAL_TOKENIZER=Qwen/Qwen2.5-Coder-3B-Instruct
DEFAULT_CTX_CAP=3072
DEFAULT_Q_BUDGET=12
SESSION_MINUTES=60
MATCH_TOLERANCE_LINES=3
DB_PATH=data/scholia.db
PROBLEMS_DIR=problems
```

---

## 10. Conventions

- **Python:** full type hints, Pydantic models at every boundary, no bare `except`, structured logging (`logging` with JSON formatter), and async for all I/O in `api/`. The DB is async too: use `AsyncSession` from `api.db.get_db` and eager-load relationships (lazy loads fail under async).
- **Errors:** API errors return `{"error": {"code", "message"}}` with proper status codes. Refusals from the proxy are 200 responses with `refused: true` and a `reason`, because they are part of the session, not failures.
- **Tests:** at least one test per invariant in section 5. For the grader, tests in `tests/fixtures/graded/` hold hand-graded reports with expected outcomes. LLM calls are mocked in unit tests, and real-call tests are marked `@pytest.mark.live` and skipped by default.
- **Commits:** small and per-feature, with conventional prefixes (`feat:`, `fix:`, `test:`, `chore:`). Do not commit `.env`, `data/` or generated `problems/`.
- When a requirement here is ambiguous, ask instead of guessing. When you find this file is wrong or outdated, say so and propose an edit.

---

## 11. Milestones. Work in order and do not skip ahead.

| # | Deliverable | Done when |
|---|---|---|
| **M0** | Repo skeleton, `schema/` models, taxonomy, config, DB tables, tooling | `uv run pytest` passes with schema round-trip tests; lint and mypy are clean |
| **M1** | Tier 0 importer (SWE-bench Lite first, then BugsInPy), sanitiser, publisher | `corpus.build --limit 20` publishes 15+ valid problems; the build log explains every drop |
| **M2** | Session API + Library and Session pages (Monaco, selection, report form, server clock) | You can start a session, select lines, flag findings and submit; the answer-leak test passes |
| **M3** | Assistant proxy + Ollama and Gemini backends + logging | Each Constrained-mode refusal path is tested; Realistic mode works; every query is in `queries` |
| **M4** | Grader (match, judge, audit) + tracker + Debrief page | Matcher tests pass; judge output validates; the debrief renders for a real session |
| **M5** | **Dogfood gate:** 5-10 real sessions, then fix the friction | The owner hand-grades 10 reports, judge agreement is checked, and the rubric is fixed if needed |
| M6 | Docker verifier, Tier 1 GitHub miner, Tier 2 mutation | Only after M5, and only if the owner says go |
| M7 | System design mode (Excalidraw canvas, rubric grader) | Only after M6, and only if the owner says go |

**Start each session by stating which milestone you are on and what is left in it.**
