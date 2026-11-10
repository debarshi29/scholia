# Scholia

A single-user, local-first platform for practising **AI-assisted code comprehension interview rounds**.

You get an unfamiliar 150-500 line Python codebase and 60 minutes. You find bugs and write design notes with help from a deliberately weak local assistant (Qwen2.5-Coder via Ollama). Then you get a graded debrief against a test-verified answer key.

See [`CLAUDE.md`](CLAUDE.md) for the full spec, invariants and milestones.

## Status

| Milestone | State |
|---|---|
| M0: skeleton, schema, config, DB, tooling | done |
| M1: Tier 0 corpus importer | built; real publish needs a Gemini key |
| M2: Session API + Library/Session pages | not started |
| M3: Assistant proxy + backends | not started |
| M4: Grader + tracker + Debrief | not started |
| M5: Dogfood gate | not started |

## Setup

```bash
uv venv --python 3.12      # creates .venv
uv sync                    # installs deps into .venv
cp .env.example .env       # then add GEMINI_API_KEY
ollama pull qwen2.5-coder:3b
```

## Build the corpus

```bash
uv run python -m corpus.build --tier 0 --source swebench --limit 20 --dry-run  # checks only
uv run python -m corpus.build --tier 0 --source swebench --limit 20            # needs GEMINI_API_KEY + JUDGE_MODEL
uv run python -m corpus.build --tier 0 --source bugsinpy --limit 20
```

Each run writes a build log to `data/logs/`.

## Quality checks

```bash
uv run ruff check . && uv run ruff format --check .
uv run python -m mypy schema api/grader
uv run pytest -q
```


```
