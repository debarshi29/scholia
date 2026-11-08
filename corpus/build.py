"""Corpus build CLI.

    uv run python -m corpus.build --tier 0 --source swebench --limit 20

``--limit`` is the number of problems to *publish*; candidates are scanned in dataset
order until it is reached. Every candidate seen is accounted for in the build log
written to ``data/logs/`` (kept, or dropped with a reason).

Order matters: all cheap, deterministic checks run first; the Gemini classification
pass runs last and only for code whose licence is on the allowlist (invariant 7).
"""

import argparse
import asyncio
import json
import logging
import sys
import urllib.error
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from google.genai import errors as genai_errors

from api.config import Settings, get_settings
from api.db import init_db, make_engine
from api.log import configure_logging
from corpus.classify import (
    Classifier,
    ClassifyError,
    ClassifyInput,
    GeminiClassifier,
    numbered_context,
)
from corpus.filters import (
    DropReason,
    check_file_set,
    check_line_counts,
    is_allowed_licence,
    is_test_path,
)
from corpus.patch import FilePatch, PatchError, parse_patch
from corpus.publish import Draft, Published, find_by_upstream, publish, register
from corpus.repos import CheckoutError, LicenceResolver, RepoCache
from corpus.sanitise import SanitiseError, sanitise
from corpus.sources.base import Candidate, CandidateSource
from corpus.text import split_lines
from schema import Bug, CategorySource, Source

log = logging.getLogger("corpus.build")


class Dropped(Exception):
    def __init__(self, reason: DropReason, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Prepared:
    candidate: Candidate
    licence: str
    patches: list[FilePatch]
    """Source-file sections of the gold patch, in patch order."""
    originals: dict[str, str]
    regions: dict[str, list[tuple[int, int]]]
    sanitised: dict[str, str]


@dataclass
class BuildLog:
    source: str
    tier: int
    limit: int
    dry_run: bool
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str = ""
    prompt_version: str | None = None
    candidates_seen: int = 0
    kept: list[dict[str, str]] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "candidates": self.candidates_seen,
            "kept": len(self.kept),
            "dropped": dict(Counter(d["reason"] for d in self.dropped).most_common()),
        }

    def write(self, logs_dir: Path) -> Path:
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.replace(":", "").replace("-", "")[:15]
        path = logs_dir / f"build-{self.source}-{stamp}.json"
        payload = {"summary": self.summary(), **asdict(self)}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path


def prepare(
    cand: Candidate, problems_dir: Path, repos: RepoCache, licences: LicenceResolver
) -> Prepared:
    """All deterministic checks. Raises ``Dropped`` with the first failing reason."""
    if find_by_upstream(problems_dir, cand.source, cand.upstream_id):
        raise Dropped(DropReason.ALREADY_PUBLISHED)
    try:
        all_patches = parse_patch(cand.patch)
    except PatchError as exc:
        raise Dropped(DropReason.PATCH_UNPARSEABLE, str(exc)) from exc
    patches = [fp for fp in all_patches if not is_test_path(fp.path)]
    if any(fp.is_new or fp.is_deleted for fp in patches):
        raise Dropped(DropReason.PATCH_ADDS_FILE)
    if reason := check_file_set([fp.path for fp in patches]):
        raise Dropped(reason, ", ".join(fp.path for fp in patches))
    try:
        cand = replace(cand, commit=repos.resolve(cand.repo, cand.commit))
    except CheckoutError as exc:
        raise Dropped(DropReason.CHECKOUT_FAILED, str(exc)) from exc

    try:
        licence = licences.resolve(cand.repo, cand.commit)
    except (urllib.error.URLError, CheckoutError) as exc:
        raise Dropped(DropReason.LICENCE_UNKNOWN, str(exc)) from exc
    if licence is None:
        raise Dropped(DropReason.LICENCE_UNKNOWN, cand.repo)
    if not is_allowed_licence(licence):
        raise Dropped(DropReason.LICENCE_NOT_ALLOWED, f"{cand.repo}: {licence}")

    try:
        originals = {fp.path: repos.read_text(cand.repo, cand.commit, fp.path) for fp in patches}
    except CheckoutError as exc:
        raise Dropped(DropReason.CHECKOUT_FAILED, str(exc)) from exc
    if reason := check_line_counts(list(originals.values())):
        sizes = {p: len(split_lines(t)) for p, t in originals.items()}
        raise Dropped(reason, json.dumps(sizes))

    try:
        regions = {fp.path: fp.changed_regions(originals[fp.path]) for fp in patches}
    except PatchError as exc:
        raise Dropped(DropReason.PATCH_UNPARSEABLE, str(exc)) from exc
    try:
        sanitised = {path: sanitise(text, regions[path]).text for path, text in originals.items()}
    except SanitiseError as exc:
        raise Dropped(DropReason.SOURCE_UNPARSEABLE, str(exc)) from exc
    return Prepared(cand, licence, patches, originals, regions, sanitised)


def classify_input(p: Prepared) -> ClassifyInput:
    context = "\n\n".join(
        f"# file: {fp.path}\n"
        + numbered_context(split_lines(p.originals[fp.path]), p.regions[fp.path])
        for fp in p.patches
    )
    return ClassifyInput(
        issue=p.candidate.issue,
        buggy_context=context,
        fix_diff="".join(fp.diff for fp in p.patches),
    )


def to_draft(p: Prepared, classifier: Classifier, tier: int) -> Draft:
    try:
        result = classifier.classify(classify_input(p))
    except (ClassifyError, genai_errors.APIError) as exc:
        raise Dropped(DropReason.CLASSIFY_FAILED, str(exc)) from exc

    cand = p.candidate
    bugs: list[Bug] = []
    for fp in p.patches:
        for start, end in p.regions[fp.path]:
            bugs.append(
                Bug(
                    id=f"b{len(bugs) + 1}",
                    file=fp.path,
                    lines=(start, end),
                    category=result.category,
                    category_source=CategorySource.LLM,
                    mechanism=result.mechanism,
                    fix_diff=fp.diff,
                    killing_test=cand.failing_tests[0] if cand.failing_tests else None,
                )
            )
    tests: dict[str, str] = {"failing_tests.json": json.dumps(cand.failing_tests, indent=2)}
    if cand.test_patch:
        tests["test_patch.diff"] = cand.test_patch
    return Draft(
        tier=tier,
        source=cand.source,
        upstream_id=cand.upstream_id,
        origin_repo=cand.repo,
        commit=cand.commit,
        licence=p.licence,
        files=p.sanitised,
        bugs=bugs,
        tests=tests,
    )


def run(
    candidates: Iterable[Candidate],
    *,
    build_log: BuildLog,
    problems_dir: Path,
    repos: RepoCache,
    licences: LicenceResolver,
    classifier: Classifier | None,
) -> list[Published]:
    """Scan candidates until ``build_log.limit`` are kept. ``classifier=None`` is a dry run."""
    published: list[Published] = []
    for cand in candidates:
        if len(build_log.kept) >= build_log.limit:
            break
        build_log.candidates_seen += 1
        try:
            prepared = prepare(cand, problems_dir, repos, licences)
            if classifier is None:
                build_log.kept.append({"upstream_id": cand.upstream_id, "problem_id": "(dry-run)"})
                continue
            pub = publish(problems_dir, to_draft(prepared, classifier, build_log.tier))
        except Dropped as d:
            build_log.dropped.append(
                {"upstream_id": cand.upstream_id, "reason": d.reason.value, "detail": d.detail}
            )
            log.info("dropped", extra={"upstream_id": cand.upstream_id, "reason": d.reason.value})
            continue
        published.append(pub)
        build_log.kept.append({"upstream_id": cand.upstream_id, "problem_id": pub.meta.problem_id})
        log.info("published", extra={"upstream_id": cand.upstream_id, "id": pub.meta.problem_id})
    return published


def source_for(name: str, data_dir: Path) -> CandidateSource:
    if name == Source.SWEBENCH:
        from corpus.sources.swebench import SWEBenchLite

        return SWEBenchLite()
    if name == Source.BUGSINPY:
        from corpus.sources.bugsinpy import BugsInPy

        return BugsInPy(data_dir / "repos" / "_datasets" / "BugsInPy")
    raise SystemExit(f"unknown source: {name}")


async def _register(settings: Settings, published: list[Published]) -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.db_url)
    try:
        await init_db(engine)
        await register(engine, published)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m corpus.build")
    parser.add_argument("--tier", type=int, choices=[0], required=True)
    parser.add_argument("--source", choices=[s.value for s in Source], required=True)
    parser.add_argument("--limit", type=int, default=20, help="problems to publish")
    parser.add_argument(
        "--dry-run", action="store_true", help="run deterministic checks only; publish nothing"
    )
    args = parser.parse_args(argv)
    configure_logging()
    settings = get_settings()

    classifier: Classifier | None = None
    if not args.dry_run:
        if settings.gemini_api_key is None or not settings.judge_model:
            print(
                "GEMINI_API_KEY and JUDGE_MODEL must be set in .env for the classification "
                "pass (or use --dry-run).",
                file=sys.stderr,
            )
            return 2
        classifier = GeminiClassifier(
            settings.gemini_api_key.get_secret_value(), settings.judge_model
        )

    data_dir = settings.db_path.parent
    repos = RepoCache(data_dir / "repos")
    build_log = BuildLog(
        source=args.source,
        tier=args.tier,
        limit=args.limit,
        dry_run=args.dry_run,
        prompt_version=classifier.prompt_version if classifier else None,
    )
    published = run(
        source_for(args.source, data_dir).candidates(),
        build_log=build_log,
        problems_dir=settings.problems_dir,
        repos=repos,
        licences=LicenceResolver(data_dir / "repos", repos),
        classifier=classifier,
    )
    build_log.finished_at = datetime.now(UTC).isoformat()
    if published:
        asyncio.run(_register(settings, published))
    path = build_log.write(data_dir / "logs")
    print(json.dumps(build_log.summary(), indent=2))
    print(f"build log: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
