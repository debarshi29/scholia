# Operations guide

Running, configuring, observing, backing up and troubleshooting Scholia. For installation see [setup.md](setup.md).

## Configuration reference

All settings come from environment variables or `.env` (see `.env.example`). Model names, caps and budgets are **only** configurable here: no model name is hard-coded in logic. Restart the API after changing `.env`.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | none | Enables the judge, the corpus classifier and Realistic mode. Stored as a secret and never logged |
| `GEMINI_MODEL` | empty | Fallback model name for `JUDGE_MODEL` and `REALISTIC_MODEL` |
| `JUDGE_MODEL` | `GEMINI_MODEL` | Model for grading and classification |
| `REALISTIC_MODEL` | `GEMINI_MODEL` | Model for Realistic mode |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint of the local model |
| `LOCAL_MODEL` | `qwen2.5-coder:3b` | Local assistant. 7B is the ceiling for a 6 GB GPU |
| `LOCAL_TOKENIZER` | `Qwen/Qwen2.5-Coder-3B-Instruct` | Tokenizer used for exact token counts |
| `DEFAULT_CTX_CAP` | `3072` | Tokens of context the Constrained assistant may be given. Keep at or below Ollama's context length |
| `DEFAULT_Q_BUDGET` | `12` | Questions per Constrained session (refusals are free) |
| `SESSION_MINUTES` | `60` | Length of a session. Submitting later is accepted and flagged overtime |
| `MAX_REPLY_TOKENS` | `512` | Cap on an assistant reply |
| `MAX_QUESTION_CHARS` | `1000` | Longest question accepted |
| `MATCH_TOLERANCE_LINES` | `3` | A finding matches a bug when ranges overlap after widening the bug by this many lines |
| `JUDGE_MAX_TOKENS` | `700` | Output cap for judge calls |
| `GEMINI_THINKING_TOKENS` | `2048` | Extra allowance for the model's hidden reasoning, added to every Gemini limit. Without it, long prompts can come back empty |
| `LIBRARY_TOPICS` | `ml,scientific,math,dsa` | Topics to build and show; empty means all |
| `DB_PATH` | `data/scholia.db` | SQLite file |
| `PROBLEMS_DIR` | `problems` | Where published problems live |

Profiles can override the session defaults (mode, context window, question budget) per person.

The dev web server proxies `/api` to `http://localhost:8000`; set `SCHOLIA_API` to point it elsewhere (for example a second API on a scratch database).

## Processes and ports

| Process | Port | Command |
|---|---|---|
| API | 8000 | `uv run python -m uvicorn api.main:app --port 8000` |
| Web (dev) | 5173 | `cd web && pnpm dev` |
| Ollama | 11434 | started by the Ollama app or `ollama serve` |

`GET /api/health` returns `200` when the API is up. The API creates the database on first start, scans `problems/` and rebuilds the problem index.

### Serving a production build

`cd web && pnpm build` writes a static site to `web/dist`. Serve it with any static server that also forwards `/api` to the API (a reverse proxy rule). The API does not serve the SPA. Remember the API has no authentication; keep both on localhost.

## Data and backups

| Path | Contents | Back up? |
|---|---|---|
| `data/scholia.db` | Sessions, assistant logs, reports, outcomes, stats, profiles | **Yes** |
| `problems/` | Published problems and their answer keys | **Yes** (regenerable, but a rebuild may pick different problems) |
| `data/repos/` | Cached clones and dataset pages | No (cache) |
| `data/logs/` | Corpus build summaries | Optional |
| `.env` | Secrets | Keep a private copy; never commit |

SQLite backup: stop the API and copy the file, or use `sqlite3 data/scholia.db ".backup 'backup.db'"` while it runs.

Schema changes are additive and applied automatically on start (`init_db`). Problems are immutable and never migrate.

## Observability

- **Application logs** are JSON lines on stderr: `ts`, `level`, `logger`, `msg`, plus structured fields.
- **Assistant exchanges** are persisted in the `queries` table: session, file, line range, token count, question, reply, model, latency and any refusal reason. This is your audit trail for how the assistant was used.
- **Corpus builds** write `data/logs/build-<source>-<timestamp>.json` with candidates seen, kept, and dropped by reason, plus per-candidate detail.
- **Grading** state is on the session: `graded_at`, `grade_error`. A session whose grading crashed shows `grading_failed` and can be regraded.

Useful queries:

```sql
-- refusals by reason
SELECT refused_reason, count(*) FROM queries WHERE refused_reason IS NOT NULL GROUP BY 1;
-- slowest assistant replies
SELECT session_id, model, latency_ms FROM queries ORDER BY latency_ms DESC LIMIT 10;
-- sessions awaiting a regrade
SELECT id FROM sessions WHERE submitted_at IS NOT NULL AND graded_at IS NULL;
```

## Security and privacy

- **Authentication:** none, by design. Profiles separate progress; they do not protect it. Do not expose the API or the dev server to a network.
- **Secrets:** the Gemini key lives only in `.env` (git-ignored) and in process memory as a secret value.
- **What leaves the machine:** with a key configured, open-source problem code and your report for that problem go to Gemini for judging and Realistic mode, and only for problems whose licence is on the allowlist. The local assistant, your assistant logs and your history never leave the machine. Without a key, nothing is sent.
- **Answer key:** unreadable by any live-session endpoint; the debrief returns it only after submit.
- **Corpus build:** Tier 0 builds read git objects and never run repository code. The planted-bug build runs a repository's doctests with a timeout; use it only on repositories you are comfortable running tests for.
- **Reporting a vulnerability:** see [SECURITY.md](../../SECURITY.md).

## Troubleshooting

| Symptom | Check |
|---|---|
| API will not start | Port 8000 in use; `.env` has an invalid value (the error names the setting); Python 3.12 environment missing (`uv sync`) |
| `409 grading_pending` for a long time | The judge is slow or rate limited. Wait, or check the API log; use **Grade again** when it finishes |
| `409 grading_failed` | Read `grade_error` on the session (`sessions` table), fix the cause, press **Grade again** |
| Every judged item is `ungraded` | No key or model name; key invalid; problem licence not on the allowlist |
| Constrained answers are `backend_error` | Ollama is down, the model is not pulled, or `OLLAMA_BASE_URL` is wrong |
| Questions are refused as `over_ctx_cap` | The selection plus question exceeds `DEFAULT_CTX_CAP`; select fewer lines |
| Library shows fewer problems than were built | `LIBRARY_TOPICS` hides projects of other topics; problems remain on disk |
| Problem missing on a debrief (`410`) | The folder under `problems/` was deleted; restore it from a backup |
| Build keeps dropping everything | Read the build log's `dropped` counts; `too_long` and `licence_unknown` are normal for large projects |

## Upgrading

```bash
git pull
uv sync --locked
cd web && pnpm install --frozen-lockfile && cd ..
```

Restart the API (it applies additive schema changes) and the dev server. If the API's request or response shapes changed, regenerate the web client types with `cd web && pnpm gen:api`.
