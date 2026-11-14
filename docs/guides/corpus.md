# The problem corpus

How Scholia's practice problems are made, what they look like on disk, and how to add more.

## What a problem is

One published version of a problem is a folder:

```
problems/P-0042/v1/
  src/            files the user sees, sanitised, repo-relative paths kept
  answer.json     the answer key (never served before submit)
  meta.json       tier, source, upstream id, origin repo, commit, licence, counts
  tests/          verifying tests and the upstream test patch (never served)
```

`answer.json` holds one bug for Tier 0 and planted problems:

```json
{
  "problem_id": "P-0042",
  "version": 1,
  "bugs": [{
    "id": "b1",
    "file": "pkg/module.py",
    "lines": [120, 124],
    "category": "boundary",
    "category_source": "llm",
    "severity": "medium",
    "mechanism": "The loop stops one element early, so the last item is never processed.",
    "fix_diff": "diff --git a/pkg/module.py b/pkg/module.py\n...",
    "killing_test": "tests/test_module.py::test_last_item"
  }],
  "design_notes": []
}
```

Problems are **immutable**: a correction publishes `v2`, and sessions keep pointing at the version they used.

## Sources

| Source | Tier | What it provides | Executes repo code? |
|---|---|---|---|
| `swebench` | 0 | SWE-bench Lite instances: the gold patch and failing tests for real GitHub issues in popular Python projects, read through the Hugging Face dataset-viewer API | No |
| `bugsinpy` | 0 | BugsInPy: curated real bugs with patches and test commands, from a shallow clone of the BugsInPy repository | No |
| `planted` | 2 | A deterministic mutation planted in an algorithm file, kept only if its doctests then fail | **Yes** (doctests, with a timeout) |

Tier 0 relies on the upstream dataset's own verification (the instance's tests fail before the fix and pass after it). Planted bugs are verified by this repository's build: doctests pass on the clean file and fail on the mutant.

## Filters

A candidate is published only if all of these hold. Every drop is logged with its reason (`DropReason`).

| Check | Drop reason |
|---|---|
| Not already published | `already_published` |
| Patch parses | `patch_unparseable` |
| 1-2 non-test source files, all `.py`, none added or deleted | `no_source_files`, `too_many_files`, `non_python`, `patch_adds_file` |
| Licence resolves to an allowlisted one (MIT, BSD-2/3, Apache-2.0, ISC, PSF-2.0) | `licence_unknown`, `licence_not_allowed` |
| Each file is 150-500 lines (planted: 60-500) | `too_short`, `too_long` |
| The fix is **one region** in one file (changed lines at most 10 apart; import-only changes ignored) | `fix_not_localised` |
| The source parses | `source_unparseable` |
| Commit fetched | `checkout_failed` |
| Gemini classification succeeded | `classify_failed` |

Large projects (for example Django, sympy) lose most candidates to `too_long`: v1 never crops files, because that would change line numbers and context.

## Sanitising

`corpus/sanitise.py` removes what would give the answer away, without changing code or line numbers:

- comments that mention the fix,
- TODO, FIXME and XXX comments on the bug's lines,
- issue and pull request numbers.

A removed comment line becomes an empty line. The result must still parse.

## Classification

A single Gemini call per candidate returns the bug **category** and a one-sentence **mechanism**, given the buggy code around the change and the fix diff (and the issue text when there is one). The category is stored with `category_source: "llm"` so it can be audited. The taxonomy is fixed:

`logic`, `boundary`, `null_empty`, `shared_mutable_state`, `concurrency`, `resource_leak`, `error_handling`, `complexity`.

Only open-source code is sent, after the licence check.

## Topics

`corpus/topics.py` maps each upstream project to a topic, and `LIBRARY_TOPICS` selects which topics are built and shown (default `ml,scientific,math,dsa`). Add any new project to `REPO_TOPICS`; unknown projects count as `other` and are skipped by default.

## Commands

```bash
# checks only: no Gemini, nothing published
uv run python -m corpus.build --tier 0 --source swebench --limit 20 --dry-run

# publish up to N new problems
uv run python -m corpus.build --tier 0 --source swebench --limit 20
uv run python -m corpus.build --tier 0 --source bugsinpy --limit 20
uv run python -m corpus.build --tier 2 --source planted  --limit 10

# override the topic filter
uv run python -m corpus.build --tier 0 --source bugsinpy --limit 20 --topics all
```

- `--limit` counts problems **published** (or that would be, in a dry run).
- Candidates are scanned **round-robin across repositories**, so a small build spans many projects.
- Re-running is safe: published candidates are skipped.
- Each run prints a summary and writes `data/logs/build-<source>-<timestamp>.json`.

## Planted bugs in detail

For each algorithm file with at least three passing doctests, the build:

1. enumerates single-edit mutants from the AST: a comparison flipped by one step (`<` to `<=`), `+` swapped with `-`, a `0`, `1` or `2` constant raised by one;
2. keeps only mutants that still parse;
3. runs `python -m doctest` on the mutant (20-second timeout) and keeps one where at least one doctest **fails**;
4. emits a candidate whose gold patch is the **reverse** of the mutation.

A seeded random generator picks files and mutants, so the same seed gives the same problems. Mutations are minimal on purpose: the interesting skill is finding a one-character bug by reading.

## Adding a source

1. Write a class in `corpus/sources/` that yields `Candidate(source, upstream_id, repo, commit, patch, issue, failing_tests, ...)`. If the buggy text does not exist upstream, pass it in `buggy_files`; if files are short, set `min_lines`.
2. Add the source to the `Source` enum in `schema/problem.py` and to `source_for` in `corpus/build.py`.
3. Map its repositories in `corpus/topics.py`.
4. Add tests next to the existing ones in `tests/corpus/`.
5. Document it here and in the decision log.

## Quality notes

- Some SWE-bench instances are missing features rather than bugs you can spot by reading. Note their ids while practising and exclude them.
- Most Tier 0 problems are classified `logic`; expect lopsided weak-spot bars until more categories are represented.
- Tier 0 problems have no reference design notes, so design notes are not scored for them.
