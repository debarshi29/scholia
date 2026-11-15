# Set up Scholia locally

This guide gets you from a clean machine to a working practice session, either directly on your machine or with [Docker](#11-run-with-docker-alternative-to-steps-3-to-7). Everything runs on your computer. The only outside service is Google Gemini, which is needed for two things: building problems (a one-time classification pass) and the optional judge and Realistic assistant.

**Time:** about 15 minutes plus model and corpus downloads. **Disk:** roughly 4 GB (the local model is about 2 GB; cloned repositories are cached).

## 1. Prerequisites

| Tool | Version | Why | Install |
|---|---|---|---|
| Git | any recent | clone the repo; the corpus build uses it | https://git-scm.com |
| Python | 3.12 | the API and corpus CLI | managed by uv (below) |
| [uv](https://docs.astral.sh/uv/) | recent | Python environments and locking | `pip install uv`, or the installer on the uv site |
| Node.js | 24 | the web app | https://nodejs.org (or `nvm`, `fnm`) |
| pnpm | 12 | web dependencies | `npm install -g pnpm@12` or `corepack enable` |
| [Ollama](https://ollama.com) | recent | the local, deliberately weak assistant | installer from ollama.com |
| Gemini API key | free tier is enough | build problems, judge, Realistic mode | https://aistudio.google.com/apikey |

Hardware: a GPU with 6 GB of VRAM runs the 3B local model comfortably. Without a GPU it runs on CPU, slower; reduce questions or use Realistic mode.

## 2. Get the code

```bash
git clone https://github.com/debarshi29/scholia.git
cd scholia
```

## 3. Install dependencies

```bash
uv python install 3.12
uv sync --locked                 # creates .venv and installs the locked Python dependencies
cd web
pnpm install --frozen-lockfile
cd ..
```

On Windows, run `pnpm` from **PowerShell** (the shim does not work in Git Bash).

## 4. Pull the local model

```bash
ollama pull qwen2.5-coder:3b
```

The first Constrained question also downloads the matching tokenizer (`Qwen/Qwen2.5-Coder-3B-Instruct`) from Hugging Face and caches it. Constrained mode needs this tokenizer to count tokens exactly.

Keep `DEFAULT_CTX_CAP` at or below the context length Ollama is configured with: its OpenAI-compatible endpoint cannot set `num_ctx` per request.

## 5. Configure

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

Edit `.env`:

```ini
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=<a Flash model name from Google AI Studio>
```

`GEMINI_MODEL` is used for the judge, the corpus classifier and Realistic mode. Set `JUDGE_MODEL` or `REALISTIC_MODEL` to override one of them. All other settings have working defaults; see the [configuration reference](operations.md#configuration-reference).

`.env` is git-ignored. Never commit it, and never paste the key into an issue or a log.

## 6. Build the problem library

Problems are generated locally from open-source bug fixes, so the repository ships none. Start with a dry run, which performs every deterministic check and publishes nothing (no Gemini call):

```bash
uv run python -m corpus.build --tier 0 --source swebench --limit 10 --dry-run
```

Then build for real. `--limit` is the number of problems to **publish**; re-running adds more and skips what is already published.

```bash
uv run python -m corpus.build --tier 0 --source swebench  --limit 15
uv run python -m corpus.build --tier 0 --source bugsinpy  --limit 15
```

Each run prints a summary and writes a log to `data/logs/` explaining every candidate (kept, or dropped with a reason such as `too_long` or `licence_unknown`). Expect many drops: files must be 150-500 lines with a one-region fix and a permissive licence.

By default only AI/ML, numerical, maths and algorithm projects are kept (`LIBRARY_TOPICS=ml,scientific,math,dsa`). Use `--topics all` to build everything.

### Data-structure and algorithm problems (planted bugs)

This source clones a public algorithms repository, plants one small bug per file, and keeps it only if the file's own doctests then fail. **It executes that repository's doctests on your machine** (each with a 20-second timeout), so it is an explicit, opt-in command. Review the source in `corpus/sources/planted.py` first if you want to.

```bash
uv run python -m corpus.build --tier 2 --source planted --limit 10 --dry-run   # checks, no Gemini
uv run python -m corpus.build --tier 2 --source planted --limit 10
```

## 7. Run

Two terminals.

**API** (port 8000):

```bash
uv run python -m uvicorn api.main:app --port 8000
```

**Web** (port 5173, proxies `/api` to 8000):

```bash
cd web
pnpm dev
```

Open http://localhost:5173. Check the API at http://localhost:8000/api/health.

The API binds to localhost. It has **no authentication**: do not expose it on a network.

## 8. Your first session

1. Pick a problem on the Library page (or choose **Start** to let the picker weight by your weak spots).
2. In the editor, click a line number, then another, to select a range. The context bar shows what that selection costs.
3. **Ask assistant** about it. In Constrained mode the model sees only the selected lines; refusals cost nothing.
4. **Flag as bug** on the lines you suspect and write why it is a bug and how to fix it. Use **Fix** mode to edit the code if you want your fix graded too.
5. **Submit report**. You get a debrief: your findings against the answer key, judge scores, an audit of what the assistant told you, and the upstream fix as a diff.

Use the sun or moon button for light and dark mode, and the profile menu to keep separate progress for different people or goals.

## 9. Verify the install (optional)

```bash
uv run ruff check . && uv run ruff format --check .
uv run python -m mypy schema api/grader
uv run pytest -q                       # about 360 tests, no network needed
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Tests mock every model call. `uv run pytest -q -m live` runs the opt-in tests against real Ollama, Gemini and the tokenizer.

## 10. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Library is empty | No problems built yet. Run step 6. Check the topic filter: `LIBRARY_TOPICS` may exclude what you built |
| Realistic mode is greyed out | `GEMINI_API_KEY` or the model name is missing in `.env` (restart the API after editing) |
| Constrained question returns a backend error | Ollama is not running, or the model is not pulled. `ollama list`; `ollama pull qwen2.5-coder:3b` |
| First Constrained question is slow | The tokenizer and model are loading. Later questions are faster |
| Debrief shows "ungraded" items | The judge was unreachable or the key is missing. Fix `.env`, then press **Grade again** |
| `licence_unknown` drops in a build | The project's licence could not be resolved to an allowlisted one. By design; those projects are skipped |
| Build is rate limited | The classifier retries with backoff; lower `--limit` or retry later |
| Port already in use | Another API or dev server is running. Stop it, or change the port and set `SCHOLIA_API` for the web proxy |
| Colours look wrong after changing `tailwind.config.js` | Restart `pnpm dev`; Vite does not reload that file |
| Windows: "An Application Control policy has blocked this file" | Smart App Control blocked an unsigned launcher. Use the module forms shown above, or `scripts\py.cmd <args>`, which runs uv's base interpreter with the project's packages. Do not turn Smart App Control off |
| `pnpm` not found in Git Bash on Windows | Run `pnpm` from PowerShell |

## 11. Run with Docker (alternative to steps 3 to 7)

A compose file runs the whole stack in containers: the API, the web app behind nginx, and Ollama.

```bash
cp .env.example .env                       # set GEMINI_API_KEY and GEMINI_MODEL
docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5-coder:3b   # once; stored in a volume
```

Open **http://localhost:8080**. Everything is published on `127.0.0.1` only (web 8080, API 8000), because the API has no authentication.

Build problems inside the API container (the volumes keep them between runs):

```bash
docker compose exec api python -m corpus.build --tier 0 --source swebench --limit 15
docker compose exec api python -m corpus.build --tier 0 --source bugsinpy --limit 15
docker compose exec api python -m corpus.build --tier 2 --source planted --limit 10   # runs doctests, see the corpus guide
docker compose restart api                 # re-index (not needed after the first build)
```

Notes:

- **Data** lives in three named volumes: `scholia-data` (database, logs, caches, tokenizer), `scholia-problems` (published problems) and `ollama-models`. `docker compose down` keeps them; `docker compose down -v` deletes them.
- **GPU:** for an NVIDIA GPU, uncomment the `deploy` block under `ollama` in `docker-compose.yml` (needs the NVIDIA Container Toolkit). Without it the local model runs on CPU.
- **Configuration** comes from `.env`; compose sets `OLLAMA_BASE_URL`, `DB_PATH` and `PROBLEMS_DIR` for the container paths.
- The API image runs as a non-root user and has a health check on `/api/health`. The web image is a static bundle served by nginx, which forwards `/api` to the API with a 300-second read timeout.
- To use an Ollama already running on your machine instead of the container, remove the `ollama` service and set `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` for `api`.

## 12. Resetting and cleaning up

- **Forget your progress:** Profiles page, **Reset stats** (keeps sessions) or **Delete** (removes the profile and its sessions).
- **Start completely fresh:** stop the API, delete `data/scholia.db`. Problems in `problems/` are kept and re-indexed on the next start.
- **Free disk space:** `data/repos/` is a cache and is safe to delete; it is re-fetched on the next build.
- **Back up:** copy `data/scholia.db` and `problems/`.
