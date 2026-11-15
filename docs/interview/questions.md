# Interview questions about Scholia

Questions an interviewer could reasonably ask about this project, with outlines of strong answers grounded in how the system is actually built. Use them to prepare to present Scholia, or to practise explaining design trade-offs.

**How to use this:** read the question, answer aloud in your own words, then compare against the outline. The outlines are bullet points, not scripts. Difficulty: 🟢 fundamentals, 🟡 design judgment, 🔴 deep or open-ended.

Companion documents: [HLD](../architecture/hld.md) · [LLD](../architecture/lld.md) · [decision log](../architecture/decisions.md).

## Contents

- [Walk-through scripts](#walk-through-scripts)
- [A. Product and problem framing](#a-product-and-problem-framing)
- [B. Architecture and system design](#b-architecture-and-system-design)
- [C. Backend, API and async](#c-backend-api-and-async)
- [D. Data and persistence](#d-data-and-persistence)
- [E. LLM and AI engineering](#e-llm-and-ai-engineering)
- [F. Algorithms and correctness](#f-algorithms-and-correctness)
- [G. Security, privacy and trust](#g-security-privacy-and-trust)
- [H. Frontend](#h-frontend)
- [I. Testing and quality](#i-testing-and-quality)
- [J. Operations and delivery](#j-operations-and-delivery)
- [K. Scaling and evolution](#k-scaling-and-evolution)
- [L. Ownership and behavioural](#l-ownership-and-behavioural)
- [Numbers worth remembering](#numbers-worth-remembering)

---

## Walk-through scripts

**Two minutes.** "Scholia is a local-first practice platform for AI-assisted code-comprehension interviews. You get an unfamiliar file, an hour and a deliberately weak assistant. You find the bug, then get graded against an answer key built from a real upstream fix. The interesting design problem is trust: the answer key must never leak, grading of *where* the bug is must be deterministic, and the LLM is allowed only to score *quality*. The assistant proxy enforces every constraint in one place. Problems are immutable and versioned, so an old debrief always matches what the user saw."

**Ten minutes.** Cover, in order: the goal and what skill it trains → the three user flows (pick, read and ask, debrief) → the context diagram (browser, FastAPI, SQLite, problem folders, Ollama, Gemini) → the ten invariants and which module owns each → the grading pipeline (match, judge, audit, tracker) → the corpus pipeline and its filters → one hard bug or trade-off you hit (token cap bypass via the question, or hunk location by content) → what you would do next (sandboxed test execution).

---

## A. Product and problem framing

**A1 🟢 What problem does Scholia solve, and for whom?**
- Interview rounds now give candidates an AI assistant; the tested skill is reading unfamiliar code and *verifying* the AI.
- Existing platforms train writing code from scratch or have no weak-assistant constraint.
- User: one person practising; local-first because the data is personal and the corpus is open-source.

**A2 🟢 Why is the assistant deliberately weak?**
- A helpful assistant removes the need to verify, which is the skill being trained.
- Constrained mode: a local 3B model, sees only selected lines, token cap, question budget.
- Realistic mode exists to practise with a strong assistant, so both situations are covered.

**A3 🟡 How do you know the platform trains the right thing?**
- Measure agreement between the judge and hand grading (the M5 dogfood gate) so the score means something.
- The audit tracks whether the user *relied on* a wrong assistant claim: the direct signal of verification failure.
- Track miss rate per category over time; the picker targets weak spots.
- Honest limit: no controlled study yet.

**A4 🟡 Why one bug per problem?**
- Upstream fixes often span several places, making "find the bug" ill-defined and grading ambiguous.
- Filtering to a single localised region (changed lines at most 10 apart, imports ignored) gives a clean key.
- Cost: most candidates are dropped, mainly for file length.

**A5 🟡 What are the non-goals, and why?**
- No hosting, no auth, one language, no code execution during a session, no Docker verifier in v1.
- Each would multiply scope (security, sandboxing, per-language tooling) without improving the core skill signal.
- Some were later added at the owner's request (profiles, fix mode, planted bugs), each recorded as an exception.

**A6 🔴 How would you decide whether to add multi-user accounts?**
- Evidence of demand and a security story first: real auth, per-user keys, quotas, hosted DB.
- Profiles already isolate data conceptually, but the header is not a security boundary.
- Prefer a separate hosted product over bending a local tool.

---

## B. Architecture and system design

**B1 🟢 Describe the architecture.**
- React SPA, FastAPI server, SQLite for sessions, plain files for problems, Ollama locally, Gemini optionally.
- A shared `schema` package is the single source of truth; the web types are generated from OpenAPI.

**B2 🟡 Why a single proxy for model calls?**
- One chokepoint makes constraints enforceable and testable: selection, token cap, budget, no-leak prompts, logging.
- If the frontend or several routes called models, limits would be advisory and could regress.
- It also owns refusal semantics (200 with `refused: true`, free of budget).

**B3 🟡 Why are problems immutable files and sessions pinned to a version?**
- Reproducible debriefs; an improved corpus must not rewrite history.
- Files are the source of truth and the DB table is a rebuildable index, so recovery is trivial.
- Trade-off: duplicated versions on disk (negligible).

**B4 🟡 Walk through what happens on submit.**
- Validate finding ranges against real file lengths and patch files; store patches as diffs.
- Set `submitted_at`, compute overtime from the server clock, commit.
- Schedule grading in a background task and return immediately.
- Debrief returns 409 `grading_pending` until done; regrade is available if anything failed.

**B5 🟡 Why a background task rather than grading inline?**
- Judge calls can take many seconds and may need retries; the user should not wait on the submit request.
- Grading is idempotent and restartable, so a crash is recoverable via regrade.
- Alternative for scale: a real queue; unnecessary for one user.

**B6 🟡 How do you keep the answer key from leaking?**
- Structural: the store can only read `src/` and `meta.json`; only the grader and debrief read the key; debrief checks `submitted_at`.
- Library cards omit upstream id and commit (they lead to the fix).
- A test walks all live-session routes and asserts key text never appears.
- The one deliberate exception (categories on cards) is documented and tested as such.

**B7 🟡 Why SQLite? When would you leave it?**
- Single user, one file, trivial backup, no server to run: fits local-first.
- Leave for multi-user or concurrent writers: Postgres via the same SQLAlchemy layer; the async stack already supports it.
- Be able to name SQLite's limits: single writer, no network access, schema alteration limits.

**B8 🔴 Draw the trust boundaries.**
- Browser and model output are untrusted; the API process is trusted; the answer key is secret until submit.
- Model JSON is parsed strictly and schema-validated; the browser's input is validated; file names are checked as safe relative paths.
- External: Gemini only for allowlisted open-source code.

**B9 🟡 How do the web and API stay in sync?**
- Pydantic response models → OpenAPI → `openapi-typescript` → typed client. CI typecheck fails if the contract drifts.

**B10 🔴 What happens if Ollama is down mid-session?**
- The proxy catches the backend error, logs it as a `backend_error` refusal, costs no budget, and returns a refusal to the UI.
- The session continues; reading and reporting do not depend on the assistant.

---

## C. Backend, API and async

**C1 🟢 Why FastAPI and Pydantic v2?**
- Async-first, typed request and response models, automatic OpenAPI, good test story with `httpx` and `ASGITransport`.

**C2 🟡 Why make the DB layer async?**
- A model call or judge call can block for seconds; async I/O keeps the server responsive and consistent with async backends.
- Consequence: no lazy loading (must eager-load), anyio tests, `aiosqlite`.

**C3 🟡 How are errors modelled?**
- One envelope `{error: {code, message}}`; specific codes (`invalid_patch`, `grading_pending`).
- Refusals are *not* errors: they are part of the session, so they are 200 responses.

**C4 🟡 How does the server own the clock?**
- `started_at` is set server-side; remaining time is computed from an injected `now()` (tests replace it).
- The UI timer only displays; late submits are accepted but flagged `overtime`.
- Why accept late submits: do not punish the user's work; record the fact.

**C5 🟡 Explain dependency injection here.**
- FastAPI dependencies build the DB session per request and construct the proxy, grader and store lazily from settings.
- Tests override them with fakes (fake backends, tmp problem dirs), so no network is needed.

**C6 🔴 Design the idempotency of grading and the tracker.**
- Grading deletes and recomputes outcomes, audits and fix results for the session.
- The tracker applies a session once: `stats_delta` stored on the session is the marker; a regrade returns early.
- Failure mode avoided: double-counting misses on retry.

**C7 🟡 How do retries work for external calls?**
- Exponential backoff on 429 and 5xx (tenacity) in the backends.
- The judge additionally retries once on invalid JSON, then marks `ungraded`.

**C8 🟡 How do profiles scope data without changing every table?**
- `sessions.profile_id` (added by an additive migration), a new `profile_stats` table, and an `X-Profile` dependency.
- All list, stats, settings and picker queries filter by it; session ids stay global.

**C9 🔴 How would you add pagination and rate limiting?**
- Cursor pagination on sessions and problems; per-profile limits on `ask` and `submit`.
- For a single user these are not needed, so say what you deliberately omitted and why.

**C10 🟡 How do you validate a code patch on submit?**
- File must exist in the problem; `RelPath` rejects traversal; at most one patch per file; size capped.
- Only files that differ from the original are stored, as a unified diff.

---

## D. Data and persistence

**D1 🟢 Describe the data model.**
- Problems (index), sessions, queries, findings, outcomes, claim audits, patches, fix results, profiles, profile stats.
- Sessions are the hub; everything a session produces hangs off it.

**D2 🟡 How did you add profiles to an existing database?**
- `create_all` never alters tables, so `init_db` adds `sessions.profile_id` with a default, seeds the default profile, and copies the old global stats once.
- Steps are idempotent; seeding runs only when `profiles` is empty so "reset" is not undone on restart.
- Tested by upgrading a synthetic old-schema database.

**D3 🟡 Why store `prompt_version` on outcomes?**
- Scores depend on the rubric; versions make results comparable and let you regrade selectively.

**D4 🟡 Why is `problems` a rebuildable index?**
- The folder is the source of truth (immutability); rebuilding on start removes drift between disk and DB.

**D5 🟡 How are enums stored and migrated?**
- SQLAlchemy stores enum names; the profile migration copies them verbatim.
- Changing `BugCategory` is a real migration (stored values and stats), so it needs an explicit decision.

**D6 🔴 What are SQLite's pitfalls you actually hit or guarded against?**
- Foreign keys are off by default: enable `PRAGMA foreign_keys=ON` per connection.
- Naive datetimes on read: normalise to UTC.
- Alter-table limits: only additive changes.

**D7 🟡 How do you delete a profile safely?**
- Delete dependents in order (audits via queries, then queries, findings, outcomes, patches, fix results, sessions, stats, profile) in one transaction; the default profile is protected.

**D8 🟢 What would you index?**
- `sessions.problem_id`, session foreign keys on child tables; the data is small, so correctness over tuning.

---

## E. LLM and AI engineering

**E1 🟡 What is the LLM allowed to decide, and what not?**
- Allowed: score mechanism and fix quality, score design notes, label assistant claims, classify bug category during corpus build.
- Not allowed: whether a finding matched a bug. That is deterministic (D1).

**E2 🟡 How do you get reliable structured output?**
- Prompts specify strict JSON; `parse_model_json` strips fences and validates against a Pydantic model.
- On failure retry once, then `ungraded`. Never guess a score.

**E3 🔴 How do you know the judge is any good?**
- Hand-grade a sample and compute agreement (`api.grader.agreement export|check`); inspect disagreements; fix the rubric and bump the version.
- Versioned prompts and stored versions make this iterative and auditable.
- Limits: a small sample and a single rater.

**E4 🟡 Describe the token-cap enforcement and a bypass you closed.**
- The cap counts the fully rendered ChatML prompt with the real tokenizer.
- Originally counting only selected lines would let a user paste code into the *question* and enlarge the window; now the question counts too, with a character limit.

**E5 🟡 Why a local small model as the default?**
- Weak by design, private, free, works offline; sized for a 6 GB GPU.
- Constrained context makes selection and verification the skill.

**E6 🟡 What did you do about Gemini "thinking" tokens?**
- Reasoning tokens count against `max_output_tokens`, so long prompts returned empty text. The backend adds a configurable allowance to every limit.

**E7 🔴 How does the audit decide a user "relied on" a wrong claim?**
- A `wrong` claim about lines X, followed by missing a key bug overlapping X, or matching it with a mechanism score below 2.
- It is a heuristic; the doc says to revisit it after dogfooding.

**E8 🟡 Prompt injection: where is it a risk?**
- Source code and the user's report are untrusted text inside judge prompts. Mitigations: sections are separated (key versus candidate), output is schema-validated, the judge cannot change matching, and a wrong score is bounded in impact.
- Be honest that a determined injection could skew a score.

**E9 🟡 Why is the system prompt silent about bugs?**
- Telling the model bugs exist biases it toward inventing them or hinting; the assistant is a generic code helper seeing a fragment.

**E10 🟡 How does the Realistic mode differ?**
- Whole file (or problem) in context to Gemini, no budget, still logged, licence-gated.

**E11 🔴 How would you evaluate whether a smaller or larger local model is "weak enough"?**
- Measure answer correctness on the corpus against keys (the audit already labels replies) and look for a target error rate; the model name is config.

**E12 🟡 How are LLM calls tested?**
- Behind a `ChatBackend` protocol and faked in unit tests; real-call tests are marked `live` and skipped by default.

---

## F. Algorithms and correctness

**F1 🟢 Explain the matching algorithm and its complexity.**
- Widen the bug range by 3, compute overlaps with each finding in the same file, sort by overlap size, assign greedily one-to-one.
- O(B·F log(B·F)); tiny inputs.

**F2 🟡 Why greedy and not optimal assignment?**
- With one bug per problem it is trivially optimal; with several, overlap-greedy is simple and predictable. A Hungarian assignment is the upgrade if ties matter.

**F3 🟡 How is a bug located in the buggy source from a patch?**
- Hunk headers can be off; locate hunk content in the source. Line splitting uses `\n` only (not `splitlines`) so numbers agree with git and the editor.

**F4 🟡 How do you ensure a "single region" fix?**
- Drop import-only change groups, cluster remaining changed lines with a gap of at most 10; require exactly one cluster in one file.

**F5 🔴 Describe how the planted-bug generator works and why it is trustworthy.**
- AST-positioned single-edit mutations (comparison flip, `+`/`-` swap, constant bump); must still parse.
- Verified by execution: doctests pass before and fail after; hangs are rejected by a timeout.
- Deterministic by seed; the key is the reverse of the mutation; no model involved.
- Threat: equivalent mutants (no test notices) are discarded, not published.

**F6 🟡 How does the picker weight problems?**
- `0.1 + sum(miss_rate over the problem's categories)`; unattempted pool first, all problems when none remain; weighted random choice.
- The floor keeps unseen categories reachable.

**F7 🟡 How is a code fix judged "on target"?**
- Diff original versus patched with difflib opcodes, map changed original lines (insertions anchored to the line before), and test overlap with the bug lines widened by the tolerance. Syntax is checked with `ast.parse`.

**F8 🔴 Where could the deterministic matcher be wrong, and what would you do?**
- A correct finding on a distant line implicated by the same root cause scores as `extra`.
- Option: accept multiple key lines (secondary spans). Implemented: the user can mark an extra as "a fair point" after the debrief, as a personal note that deliberately does not change matching, scores or stats, so the key stays the only authority.

---

## G. Security, privacy and trust

**G1 🟢 What data leaves the machine?**
- Only with a Gemini key: open-source problem code and the report for it (judge, Realistic mode, corpus classification), and only for allowlisted licences. Nothing else.

**G2 🟡 Why a licence allowlist?**
- Sending third-party code to a service needs a legal basis; the allowlist (MIT, BSD, Apache-2.0, ISC, PSF) is conservative. Unknown or copyleft licences are dropped at build time and re-checked at call time.

**G3 🟡 What are the risks of the planted-bug build and how are they bounded?**
- It runs a repository's doctests locally. Bounds: explicit opt-in command, per-run timeout, scratch directory with only the file, no network use by the tool itself. Treat like running that project's tests.

**G4 🟡 Is there authentication? Is that acceptable?**
- No, by design: a local single-user tool bound to localhost. Profiles are explicitly not a security boundary. Do not expose it; the docs say so.

**G5 🟡 How do you protect secrets?**
- `.env` is git-ignored; the key is a `SecretStr`; never logged; the docs tell users not to paste it.

**G6 🔴 Threat-model the answer key.**
- Attack surfaces: library endpoint fields, error messages, file listing, debrief before submit, prompts (the assistant could echo hints if given the key), logs.
- Controls: structural read restriction, leak test, system prompt without bug mention, Constrained mode sending only selected lines.

**G7 🟡 Path traversal?**
- `RelPath` rejects absolute paths and `..`; the store resolves under the version directory; patches and findings must name files that exist.

**G8 🟡 How do you treat model output as untrusted?**
- Strict parsing and schema validation; never executed or rendered as HTML; scores clamped by schema ranges.

---

## H. Frontend

**H1 🟢 Why React with Vite and TypeScript?**
- Fast dev loop, type safety end to end with generated API types, large ecosystem; no need for SSR in a local app.

**H2 🟡 Why no router library?**
- Four pages; a 40-line History API router avoids a dependency and is trivially testable.

**H3 🟡 How is state split?**
- Server state in TanStack Query (cached, invalidated on profile switch); client state in Zustand: the report draft per session (persisted so a reload loses nothing), active profile, theme.

**H4 🟡 How does line selection work in Monaco?**
- Click a line number then another to select a range (drag also works); the viewer reports the selection upward, which drives Ask and Flag. Flagged lines get decorations.

**H5 🟡 How is Fix mode implemented?**
- The same editor becomes writable; edits are stored per file in the draft and submitted as patches; opening the file shows the edit; Reset removes it. The viewer is keyed per file so a model switch cannot attribute edits to the wrong file.

**H6 🟡 How does theming work?**
- RGB-channel CSS variables, Tailwind colour names mapped to them (so opacity modifiers still work), `data-theme` set before first paint to avoid a flash, Monaco themes defined to match.

**H7 🟡 Accessibility decisions?**
- Real buttons and labels, visible focus rings, ARIA on menus and toggles, reduced-motion support, contrast checked for text and accents.

**H8 🔴 What does the UI never do?**
- Call a model, hold the answer key, or trust its own timer. All three are server concerns.

---

## I. Testing and quality

**I1 🟢 What is your testing strategy?**
- Table-driven unit tests for pure logic (matcher, filters, patch parsing, mutations); API tests through `ASGITransport` with fakes; invariant tests; opt-in live tests.

**I2 🟡 How do you test an LLM-dependent grader?**
- Fake the backend with canned JSON; hand-graded fixtures with expected outcomes; test failure paths (invalid JSON twice, backend down, licence blocked).

**I3 🟡 Which tests encode invariants?**
- Answer leak, refusal paths and cost accounting, clock and overtime, licence gate, immutability, config-only model names.

**I4 🟡 Static analysis?**
- ruff (lint and format), mypy strict on `schema/` and `api/grader/`, ESLint and the TypeScript compiler on the web.

**I5 🔴 What did CI catch that local runs did not?**
- Example: a variable reused with two types in the grader, caught by mypy in CI because mypy cannot run on the author's machine.

**I6 🟡 How do you keep tests offline and fast?**
- No network in unit tests; tmp directories for problems and DB; fakes for backends and the tokenizer.

---

## J. Operations and delivery

**J1 🟢 How do you run it?**
- API on 8000, web dev server on 5173, Ollama locally; `uv` and `pnpm` with lockfiles.

**J2 🟡 How is the pipeline set up?**
- GitHub Actions on push and pull request: Python (ruff, mypy, pytest) and web (typecheck, lint, build).

**J3 🟡 How do you ship changes?**
- Small conventional commits and small PRs, CI green before merge.

**J4 🟡 Backups and recovery?**
- Copy `data/scholia.db` and `problems/`; `data/repos` is a cache. Problems are regenerable but a rebuild may pick different ones.

**J5 🔴 How would you containerise and host this?**
- API and web images, Ollama as a sidecar, volumes for data and problems, secrets via the platform, an auth proxy in front. Doing so changes the threat model (G4), so add auth first.

---

## K. Scaling and evolution

**K1 🟡 What would break first with many users?**
- No auth, SQLite single writer, local Ollama capacity, the judge's rate limits, per-process tokenizer memory.

**K2 🟡 How would you add execution-based grading?**
- Already done for algorithm problems: the file's doctests run against the user's patch (scratch directory, timeout, off the event loop) and the result is stored in `fix_results.tests`.
- For every other problem: a sandbox (container or microVM) running the upstream tests with CPU, memory, time and network limits, because executing arbitrary project tests is a much larger trust decision.

**K3 🟡 How would you support another language?**
- Language-specific parts: sanitiser (comments, parser), syntax check, Monaco language, prompts, test runner, bug source. The schema and matcher are language-agnostic.

**K4 🟡 How would you reduce judge cost and variance?**
- Cache scores keyed by prompt version and inputs, batch matched findings, use deterministic rubrics where possible, calibrate with hand-graded anchors.

**K5 🔴 How would you detect a bad problem automatically?**
- Signals: nobody ever finds it, the judge and users disagree, the upstream label reads as a feature, equivalent mutation. Add a "report problem" action and quarantine by version.

**K6 🟡 Spaced repetition instead of weights?**
- Schedule by category and time since last miss (SM-2 style), re-surfacing missed problems; stats already store per-category outcomes and per-session deltas.

**K7 🔴 What is the weakest part of the design?**
- Honest candidates: LLM category labels, judge variance, heuristic `relied_on`, the profile header trust, one-bug-only problems.

**K8 🟡 What would you instrument?**
- Time to first flag, questions per session, refusal rate by reason, judge latency and failure rate, agreement with hand grading.

---

## L. Ownership and behavioural

**L1 🟢 What was the hardest technical problem?**
- Pick one and tell it fully: locating bug lines from patches reliably, keeping the key from leaking, or enforcing the token cap against the question bypass. Include what you measured and what you changed.

**L2 🟡 A time you changed your mind about a design.**
- Example: moving to an async DB layer, or replacing boxy card UI with ruled rows after feedback. State the signal that made you change, and the cost.

**L3 🟡 How did you handle scope changes?**
- Features requested later (categories grouping, profiles, fix mode) were recorded as explicit exceptions to the original scope in the spec, with their security or design implications.

**L4 🟡 How did you decide what *not* to build?**
- A written non-goals list tied to the core skill; deferring a verifier, hosting and other languages.

**L5 🟡 What would you do differently starting over?**
- Dogfood earlier to measure judge agreement; introduce profiles and theming from the start; build a problem-quality feedback loop.

---

## Numbers worth remembering

| Fact | Value |
|---|---|
| Session length | 60 minutes (config) |
| Default context cap and question budget | 3072 tokens, 12 questions |
| Reply cap, question cap | 512 tokens, 1000 characters |
| Match tolerance | ±3 lines |
| Score scales | mechanism 0-2, fix 0-2, design 0-3 |
| File size for Tier 0 | 150-500 lines (planted: 60-500) |
| One-region fix gap | changed lines at most 10 apart |
| Picker exploration floor | 0.1 |
| Licence allowlist | MIT, BSD-2, BSD-3, Apache-2.0, ISC, PSF-2.0 |
| Bug categories | 8: logic, boundary, null_empty, shared_mutable_state, concurrency, resource_leak, error_handling, complexity |
| Invariants | 10 (see `CLAUDE.md` section 5) |
| Planted-bug doctest timeout | 20 seconds |
| Profiles | max 20; `default` cannot be deleted |
