## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] Small, focused change with conventional commit messages
- [ ] No invariant in `CLAUDE.md` section 5 is broken (answer key, proxy, determinism, immutability, licence)
- [ ] `ruff`, `mypy` (strict on `schema/` and `api/grader/`) and `pytest` pass
- [ ] Web `typecheck`, `lint` and `build` pass if `web/` changed; `pnpm gen:api` run if the API changed
- [ ] Tests added or updated (one per invariant touched; LLM calls mocked)
- [ ] Docs updated (`CLAUDE.md`, `docs/`) if behaviour or design changed
- [ ] No secrets, `.env`, `data/` or generated `problems/` committed

## Notes for the reviewer

<!-- Trade-offs, follow-ups, screenshots for UI changes (light and dark). -->
