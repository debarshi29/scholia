# Scholia

A single-user, local-first platform for practising **AI-assisted code comprehension interview rounds**.

You get an unfamiliar 150-500 line Python file and 60 minutes. You find the bug and write design notes, with help from a deliberately weak local assistant (Qwen2.5-Coder via Ollama) that sees only the lines you select. Then you get a graded debrief against an answer key built from the real upstream fix.

The skill being trained is reading code and checking what an AI tells you. See [`CLAUDE.md`](CLAUDE.md) for the full spec, invariants and decisions.

## Status

| Milestone | State |
|---|---|
| M0: skeleton, schema, config, DB, tooling | done |
| M1: Tier 0 corpus importer (SWE-bench Lite, BugsInPy) | done |
| M2: Session API, Library and Session pages | done |
| M3: Assistant proxy, Ollama and Gemini backends | done |
| M4: Grader, tracker, Debrief page | done |
| M5: Dogfood gate | yours to run: see [Dogfooding](#dogfooding-m5) |

## Setup

```bash
uv venv --python 3.12            # creates .venv
uv sync                          # installs Python deps into .venv
cd web && pnpm install && cd ..  # run pnpm from PowerShell, not Git Bash
ollama pull qwen2.5-coder:3b
cp .env.example .env             # then set GEMINI_API_KEY and GEMINI_MODEL
```

`GEMINI_MODEL` is used for the judge, the corpus classifier and Realistic mode. Set `JUDGE_MODEL` or `REALISTIC_MODEL` to use a different model for one of them.

## Run

Two terminals:

```bash
uv run python -m uvicorn api.main:app --port 8000
```

```powershell
cd web; pnpm dev        # http://localhost:5173, proxies /api to :8000
```

Open http://localhost:5173, pick a problem (or let the picker choose by your weak spots) and start a session.

## A session

1. **Read the code.** Select lines to see how much of the context window they use.
2. **Ask the assistant** about the selected lines. In Constrained mode it sees only those lines, has a token cap and a question budget, and it can be wrong. Refused questions cost nothing.
3. **Flag as bug** on the lines you think are wrong, then write what goes wrong and a fix.
4. **Submit.** The server owns the clock; a late submit is accepted and marked overtime.
5. **Debrief.** Line matching is deterministic. The Gemini judge only scores your explanation and fix, and audits what the assistant told you. If the judge is down, items show as ungraded and you can grade again.

## Build the corpus

```bash
uv run python -m corpus.build --tier 0 --source swebench --limit 20 --dry-run  # checks only, no Gemini
uv run python -m corpus.build --tier 0 --source swebench --limit 20
uv run python -m corpus.build --tier 0 --source bugsinpy --limit 20
```

Only projects in `LIBRARY_TOPICS` are built and shown (default `ml,scientific,math,dsa`: scikit-learn, keras, spaCy, sympy, astropy, xarray, pandas). Pass `--topics all` to build everything, and set `LIBRARY_TOPICS=` (empty) in `.env` to show everything.

`--limit` is the number of problems to publish. Already published problems are skipped, so running it again adds more. Each run writes a log to `data/logs/` that accounts for every candidate (kept, or dropped with a reason).

## Windows Smart App Control

Smart App Control blocks unsigned programs it does not recognise. On the machine this was built on, it blocks:

- the `uvicorn.exe` and `mypy.exe` launchers uv generates, so those two run as modules (`python -m uvicorn`, `python -m mypy`);
- at times, `.venv\Scripts\python.exe` itself, which makes **every** `uv run ...` command fail with "An Application Control policy has blocked this file".

When `uv run` is blocked, use the wrapper. It runs uv's base interpreter, which is allowed, with this project's installed packages:

```bat
scripts\py.cmd -m uvicorn api.main:app --port 8000
scripts\py.cmd -m corpus.build --tier 0 --source swebench --limit 20
scripts\py.cmd -m pytest -q
```

Nothing here changes or turns off Smart App Control. A lasting alternative is a Python build signed by its publisher (the python.org installer) as the venv's base.

## Quality checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run python -m mypy schema api/grader
uv run pytest -q
uv run pytest -q -m live          # real Ollama, Gemini and tokenizer calls
```

```powershell
cd web; pnpm typecheck; pnpm lint; pnpm build
pnpm gen:api                      # after any API change
```

## Dogfooding (M5)

M5 is done when you have run 5-10 real sessions, hand-graded 10 reports and checked that the judge agrees with you.

```bash
uv run python -m api.grader.agreement export data/agreement.csv   # one row per matched finding
# fill in hand_mechanism (0-2) and hand_fix (0-2) for each row, then:
uv run python -m api.grader.agreement check data/agreement.csv
```

`check` prints how often the judge's scores equal yours and lists every disagreement. If agreement is poor, change the rubric in `api/grader/prompts/` (bump the version header) and use "Grade again" on the debrief.

Things worth watching while you dogfood:

- Some SWE-bench problems are really missing features, not bugs you can spot by reading. Note their ids.
- Tier 0 problems have no reference design notes, so design notes are not scored yet.
- Most published problems are classified `logic`, so the weak-spot bars will be lopsided at first.
