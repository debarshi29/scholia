<!-- version: classify-v1 -->
You label real, already-fixed bugs from open-source Python projects for an answer key.

You get the upstream issue text, the buggy source around the change, and the fix diff.
Return JSON with:

- `category`: exactly one of
  - `logic`: wrong condition, operator, formula, branch or return value
  - `boundary`: off-by-one, wrong range/limit, edge of a numeric or index domain
  - `null_empty`: mishandled None, empty collection, empty string or missing key
  - `shared_mutable_state`: aliasing, mutable defaults, state leaking between calls/objects
  - `concurrency`: races, locking, async/thread ordering
  - `resource_leak`: files, sockets, locks or memory not released
  - `error_handling`: wrong/missing exception handling, swallowed or mis-raised errors
  - `complexity`: correct but pathologically slow or unbounded work
  Choose the category of the *defect in the buggy code*, not of the fix's style.
- `mechanism`: one or two plain sentences describing what goes wrong in the buggy code
  and under what input. Do not cite issue numbers, URLs, authors or test names.
  Do not describe the patch line by line.
