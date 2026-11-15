# Contributing to Scholia

Thanks for helping. Scholia is a small codebase with a few hard rules; following them keeps the training value of the product intact.

## Ground rules

1. **Read the invariants.** [`CLAUDE.md`](CLAUDE.md#5-core-invariants-never-break-these) lists ten invariants (answer key never reaches the client before submit; the proxy is the only path to a model; matching is deterministic; problems are immutable; only open-source code goes to Gemini; ...). A change that breaks one is wrong even if it looks like an improvement.
2. **Serve the skill.** The product trains reading code and verifying an AI. If a change makes the assistant more helpful or reveals the answer more easily, it needs the owner's explicit approval.
3. **Ask before** adding a dependency outside the stack, changing the bug taxonomy, or building something listed as out of scope.
4. **Keep the spec honest.** If you change behaviour that `CLAUDE.md` describes, update it in the same pull request.

## Setup

Follow [docs/guides/setup.md](docs/guides/setup.md). You do not need Ollama or a Gemini key to run the tests: every model call is faked.

## Workflow

- Branch from `main` with a descriptive name (`feat/...`, `fix/...`, `docs/...`).
- Make **small, focused commits** with conventional prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, optionally scoped (`feat(api):`).
- Open a small pull request. CI must be green before merge.
- Do **not** commit `.env`, `data/`, generated `problems/`, or secrets.

## Quality gates

Run these before you push; CI runs the same.

```bash
uv run ruff check . && uv run ruff format --check .
uv run python -m mypy schema api/grader      # strict
uv run pytest -q --cov                       # fails below 85% coverage
cd web && pnpm typecheck && pnpm lint && pnpm build
```

Dependency audits (run them before a release and after adding a dependency):

```bash
uv audit                              # Python packages
cd web && pnpm audit --prod           # web packages
```

A transitive advisory is fixed with an override in `web/pnpm-workspace.yaml` (pnpm 12 reads overrides from there, not from `package.json`). Currently `dompurify` is pinned to `>=3.4.17`, because Monaco pulls it in.

If you change the API's request or response models, regenerate the web client:

```bash
uv run python -m api.openapi web/openapi.json
cd web && pnpm gen:api
```

## Conventions

**Python**

- Full type hints; Pydantic models at every boundary; no bare `except`.
- `async` for all I/O in `api/`. Use the async session from `get_db` and eager-load relationships.
- Structured logging through the JSON formatter.
- Model names, caps and budgets come only from `Settings`.
- Shared types live in `schema/` only.

**API**

- Errors use the `{"error": {"code", "message"}}` envelope. Assistant refusals are `200` with `refused: true`.
- Nothing a live session can call may return answer data. If you add a route, extend the answer-leak test.

**Frontend**

- Use the colour tokens (`bg-bg`, `text-ink`, `border-line`, `text-cyan`, ...), never hard-coded hex or `white/..`: they must work in both themes.
- Real buttons and labels, visible focus, `aria-*` where needed. Respect `prefers-reduced-motion`.
- After editing `tailwind.config.js`, restart `pnpm dev`.
- Keep content separated by rules rather than boxes.

**Tests**

- At least one test per invariant. Mock LLM calls; mark real-call tests `@pytest.mark.live`.
- Grader changes need a case in `tests/fixtures/graded/` or a table-driven unit test.
- Corpus changes need a test in `tests/corpus/`.

**Prompts**

- Prompts live in `api/grader/prompts/` with a version header. Changing a rubric means bumping the version; scores store it.

## Adding things

See the extension table in the [LLD](docs/architecture/lld.md#14-extension-points) for what to touch when adding a bug source, topic, backend, rubric, mutation operator or page.

## Documentation

Docs live in `docs/` and use Mermaid diagrams (rendered by GitHub). Keep diagrams and tables in step with the code; the [decision log](docs/architecture/decisions.md) gets a new entry for any significant choice.

## Reporting problems

- Bugs and ideas: open an issue with steps to reproduce, expected and actual behaviour, and your OS and versions.
- Security issues: see [SECURITY.md](SECURITY.md). Do not file them as public issues.
