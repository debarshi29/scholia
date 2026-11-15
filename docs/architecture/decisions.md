# Decision log

Architecture decisions for Scholia, in the order they were made. Each entry states the context, the decision, the alternatives that were weighed, and the consequences. Decisions marked **owner** were made by the project owner as explicit requests; they sometimes override the original scope in `CLAUDE.md`, and each is recorded there as an exception.

Format: *Context* (why a decision was needed), *Decision*, *Alternatives*, *Consequences*.

---

## D1. Matching is deterministic; the LLM only scores

- **Context.** A grader that asks a model "did this finding match the bug?" is unreproducible, drifts with model versions, and can be talked into agreeing.
- **Decision.** A finding matches a bug when the file is equal and the line ranges overlap after widening the bug by 3 lines. Assignment is one-to-one, greedy by overlap size. The judge scores the *quality* of a matched finding (mechanism 0-2, fix 0-2) and can lower it to `partial`; it can never change a match.
- **Alternatives.** Pure LLM matching (rejected: nondeterministic); exact line equality (rejected: too strict for multi-line bugs); fuzzy text similarity of explanations (rejected: models explanations, not locations).
- **Consequences.** Matching is unit-testable with tables. Judge outages degrade only the quality scores, never the found/missed result. The tolerance is a config value.

## D2. The assistant proxy is the only path to a model, and the assistant is weak on purpose

- **Context.** The skill being trained is verifying an AI. A helpful assistant removes the need to verify.
- **Decision.** Every model call during a session goes through one proxy. In Constrained mode it sends only the numbered selected lines and the question, with a token cap (default 3072) and a question budget (default 12). The system prompt never mentions bugs or interviews. A local 3B model is the default.
- **Alternatives.** Let the frontend call models directly (rejected: limits become advisory); a strong cloud model for all sessions (rejected: defeats the purpose); client-side limits (rejected: bypassable).
- **Consequences.** All constraints are testable in one module. Refusals are logged and cost nothing, which keeps the budget meaningful. A Realistic mode exists for practising with a strong assistant.

## D3. The answer key never reaches the client before submit

- **Context.** The key is the most sensitive artifact; a single leaky endpoint ruins every problem.
- **Decision.** `ProblemStore` can read only `src/` and `meta.json`. `answer.json` and `tests/` are read only by the grader and the debrief route, and only after `submitted_at`. Library cards omit the upstream id and commit (which lead straight to the fix). A test walks every live-session route and asserts no key text appears.
- **Alternatives.** Trust each route to filter (rejected: easy to regress); encrypt the key (rejected: the server must read it anyway).
- **Consequences.** A structural guarantee plus a regression test. The one exception is **owner**-approved (D14): library cards carry bug categories.

## D4. Problems are immutable and versioned

- **Context.** A debrief must show what the user actually saw, even after the corpus improves.
- **Decision.** A published problem version is never edited. A fix publishes `vN+1`. Sessions pin `(problem_id, version)`. The `problems` table is an index rebuilt from the folder on each start.
- **Alternatives.** Mutable rows with an audit trail (rejected: complexity, and the code on disk is the real artifact).
- **Consequences.** Old sessions stay debriefable. Disk usage grows with versions (negligible).

## D5. Tier 0 problems have exactly one bug

- **Context.** Upstream fixes often touch several places, which makes "find the bug" ill-defined and hard to grade.
- **Decision.** Import-only changes are ignored; the remaining changed lines must form one region (at most 10 lines apart) in one file, otherwise the instance is dropped as `fix_not_localised`. Files must be 150-500 lines (60-500 for planted algorithm files).
- **Alternatives.** Multi-bug problems (deferred); cropping files (rejected for v1: it alters line numbers and context).
- **Consequences.** Clean grading and a clean answer key, at the cost of discarding many candidates (most drops are `too_long`).

## D6. Hunk location by content, not header numbers

- **Context.** Patch hunk headers can be off from `base_commit`; git tolerates offsets.
- **Decision.** Changed lines are located by matching hunk content in the buggy source. Lines split on `\n` only, because `str.splitlines` also breaks on form feeds and would shift numbers relative to git and the editor.
- **Consequences.** Robust mapping to buggy-version line numbers; a dedicated `corpus/text.py` owns line semantics.

## D7. Sanitise comments, keep line numbers

- **Context.** Comments such as "fix for #1234" give the answer away.
- **Decision.** Remove comments that mention the fix, TODO/FIXME/XXX on the bug's lines and issue numbers, replacing each with an empty line. Never alter code. Verify the result still parses.
- **Consequences.** The answer key's line numbers stay valid; some residual hints may remain (an accepted risk, reviewed while dogfooding).

## D8. Grading always completes

- **Context.** The judge is a free-tier network call; it will fail.
- **Decision.** Grading runs in a background task. If the judge is unreachable, unconfigured, returns invalid JSON twice, or the licence is not allowlisted, the item is `ungraded`; deterministic parts still complete. `POST .../regrade` re-runs it.
- **Alternatives.** Fail the submit (rejected: loses the user's work); score 0 on failure (rejected: lies).
- **Consequences.** A user never loses a session to a flaky dependency. Never guessing a score keeps the data honest.

## D9. Gemini only for open-source code

- **Context.** Sending code to a third party needs a licence basis.
- **Decision.** A problem's licence must be on an SPDX allowlist (MIT, BSD-2/3, Apache-2.0, ISC, PSF-2.0) before any of it goes to Gemini. The corpus build resolves licences (GitHub API, falling back to licence-text detection) and drops unknown ones. Nothing outside `problems/` is ever sent.
- **Consequences.** Some popular projects are excluded (`licence_unknown`). The user's own reports and the assistant logs stay local unless the problem is allowlisted, in which case the judge sees the relevant code and the report.

## D10. Async end to end, including SQLite

- **Decision (owner).** The database layer is async (SQLAlchemy asyncio with `aiosqlite`) alongside async backends and routes, so a slow model call never blocks other requests.
- **Consequences.** Relationships must be eagerly loaded (lazy loads fail under async). Tests use anyio. A real database server would be a drop-in change of URL.

## D11. SWE-bench rows over HTTP, not the `datasets` package

- **Context.** `datasets` needs `pyarrow`, which Windows Smart App Control blocks on the author's machine.
- **Decision.** Read SWE-bench Lite through the Hugging Face dataset-viewer JSON API with `httpx`, caching pages under `data/repos/_datasets/`.
- **Consequences.** No heavy dependency; works offline after the first fetch.

## D12. Tailwind 3, a router in 40 lines, Monaco bundled locally

- **Context.** Tailwind 4's native scanner is blocked by Smart App Control; a four-page app does not justify a router library; a CDN editor would break local-first.
- **Decision.** Tailwind 3 (pure JS), a small History API router, Monaco trimmed to Python and bundled.
- **Consequences.** Fewer dependencies and fully offline UI. Restart the dev server after editing `tailwind.config.js`.

## D13. One bug category per problem, assigned by an LLM and labelled as such

- **Decision.** A Gemini pass assigns `category` and `mechanism` during the build, stored with `category_source: llm` so it can be audited. Changing the taxonomy is a migration and needs an explicit decision.
- **Consequences.** Cheap, scalable labelling; most Tier 0 problems classify as `logic`, so early statistics are lopsided. Human review is the planned mitigation.

## D14. Library grouped by bug category (owner exception)

- **Decision (owner).** The Library groups problems by bug category (with a switch to group by project). With one bug per problem this names the kind of bug before the session, which the owner accepted.
- **Consequences.** `GET /api/problems` carries `categories`; the leak test allows that field on that endpoint only. Nothing else from the key may be added.

## D15. Topics: AI/ML and numerical code first (owner)

- **Decision (owner).** `corpus/topics.py` maps each upstream project to a topic (`ml`, `scientific`, `math`, `dsa`, `web`, `tooling`, `other`). `LIBRARY_TOPICS` filters what the build examines and what the Library, picker and session start offer. Other problems stay on disk and their sessions stay readable.
- **Consequences.** A new upstream project must be added to the map or it counts as `other`.

## D16. Fix mode: users can repair the code, not only report it (owner)

- **Decision (owner).** The editor has a Read/Fix switch. Edited files are submitted as `patches`, stored as diffs, checked for location and syntax, and scored by the judge against the reference fix. A bug whose lines were fixed counts as located in the stats.
- **Alternatives.** Run the problem's tests on the fix for every problem (deferred: needs a sandbox; see D21 for the part that is done).
- **Consequences.** Fix quality is judged by the model, plus doctests for algorithm problems (D21). Findings use original line numbers, so edits that add or remove lines shift the editor against them; "Reset file" restores the original.

## D17. Planted bugs for DSA/CP problems (owner)

- **Decision (owner).** For algorithm files with doctests, apply one deterministic AST mutation and keep it only if the doctests pass before and fail after. The answer key is the reverse of the mutation. No model writes bugs.
- **Alternatives.** LLM-planted bugs (rejected: unverifiable and could be subtle in the wrong way); hand curation (rejected: does not scale).
- **Consequences.** Every planted bug is caught by a real test. The build executes the repo's doctests locally, so it is an explicit, opt-in command with a timeout.

## D18. Local profiles without authentication (owner)

- **Decision (owner).** Several named profiles on one machine, each with its own sessions, stats and defaults, selected by an `X-Profile` header. No login.
- **Alternatives.** One profile (rejected by the owner); real accounts (a much larger change and unnecessary for a local tool).
- **Consequences.** Profiles separate progress, they do not protect it. The default profile holds all pre-existing data via an in-place migration. See the security note in the HLD.

## D19. Paper theme with light and dark modes (owner)

- **Decision (owner).** A warm paper design with a teal accent; colours are RGB-channel CSS variables mapped to the Tailwind names; light and dark themes with a toggle; content separated by rules rather than boxes.
- **Consequences.** Components must use colour tokens, never hard-coded hex or `white/..`. Monaco has matching themes. `@fontsource/newsreader` was added for headings.

## D20. Smart App Control is never disabled

- **Context.** Windows Smart App Control blocks unsigned launchers (`uvicorn.exe`, `mypy.exe`) and sometimes `.venv\Scripts\python.exe`.
- **Decision.** Run tools as modules, use `scripts/py.cmd` (uv's base interpreter with the venv's packages) when `uv run` is blocked, and rely on CI for mypy. Never change or disable the protection.
- **Consequences.** Slightly unusual commands on that machine; everything works on other machines with the standard commands.

## D21. Verify fixes to algorithm problems by running their doctests (owner)

- **Context.** Fix mode was judged only by an LLM. Planted-bug problems already have an executable oracle: the file's own doctests, which pass on the clean file and fail on the mutant.
- **Decision (owner: "finish off whatever is left").** After submit, grading runs the user's edited file against its doctests for `planted` problems and stores `passed`, `failed` or `error` in `fix_results.tests`. The runner is shared with the corpus build (`corpus/doctests.py`): a scratch directory, `python -m doctest`, a 20-second timeout, off the event loop. A syntax error is reported without running.
- **Alternatives.** A Docker verifier for all problems (M6, still deferred); running nothing (leaves fixes judged only by a model).
- **Consequences.** A fix to an algorithm problem now has an objective result. It executes the user's own edited code on their own machine without a sandbox, which is acceptable for a single-user local tool and is documented in the security notes. It never runs during a session and never for upstream-bug problems.

## D22. A finding outside the key can be marked "a fair point" (owner)

- **Context.** "Extra" findings are not in the key but may be correct (a second real bug, a fair design point). The debrief had no way to say so.
- **Decision.** The user can mark an extra as a fair point after the debrief (stored as `findings.marked_valid`, with an in-place column migration). It is a personal note: matching, judge scores and the category stats never change.
- **Alternatives.** Let a mark change the stats (rejected: the test-verified key must stay the only authority, otherwise the tracker can be gamed); an LLM re-judge of extras (rejected: cost and an invariant-9 risk).
- **Consequences.** Users can keep an honest record without weakening the grading. Only extras can be marked; a regrade keeps the mark.

## D23. Container packaging and a coverage floor (owner)

- **Context.** "Production grade" for a local tool means anyone can run it reproducibly and regressions are caught.
- **Decision (owner).** Two images (API on `python:3.12-slim` with locked dependencies and `git`, running as a non-root user with a health check; web built with Node and served by nginx, which forwards `/api`), plus a compose file that adds Ollama with named volumes and publishes only on `127.0.0.1`. CI enforces an 85% coverage floor (`pytest-cov`, a new dev dependency approved by the owner), runs a dependency-audit job also on a weekly schedule, and Dependabot proposes updates.
- **Alternatives.** A single image serving the SPA from the API (rejected: couples the API to static hosting); publishing on all interfaces (rejected: the API has no authentication).
- **Consequences.** The images were built and exercised (health check, SPA routing, the nginx proxy and a corpus dry run inside the container). The full stack was also run end to end: the Ollama container pulled `qwen2.5-coder:3b`, a problem was built inside the API container, and a Constrained question went through nginx, the API, the in-container tokenizer and the Ollama container and returned a reply. Coverage was 87% when the floor was set at 85%.
