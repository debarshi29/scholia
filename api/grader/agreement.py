"""Judge agreement check for the M5 dogfood gate.

    python -m api.grader.agreement export data/agreement.csv
    python -m api.grader.agreement check  data/agreement.csv

``export`` writes one row per matched finding of every graded session, with the answer
key, the finding and the judge's scores, plus two empty columns: ``hand_mechanism`` and
``hand_fix``. The owner fills those in (0-2 each). ``check`` then reports how often the
judge's scores equal the hand grades and lists every disagreement.

Only submitted, graded sessions are read, so this never opens a key for a live session.
"""

import asyncio
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from api.config import get_settings
from api.db import FindingRow, OutcomeRow, SessionRow, make_engine
from corpus.publish import load_answer

FIELDS = [
    "session_id",
    "problem_id",
    "bug_id",
    "key_mechanism",
    "your_explanation",
    "your_fix",
    "judge_mechanism",
    "judge_fix",
    "judge_notes",
    "prompt_version",
    "hand_mechanism",
    "hand_fix",
]


@dataclass(frozen=True)
class Pair:
    label: str
    judge: int
    hand: int


@dataclass(frozen=True)
class Agreement:
    n: int
    exact: int
    within_one: int
    mean_abs_diff: float
    disagreements: tuple[Pair, ...]

    @property
    def exact_rate(self) -> float:
        return self.exact / self.n if self.n else 0.0


def compare(pairs: list[Pair]) -> Agreement:
    diffs = [abs(p.judge - p.hand) for p in pairs]
    return Agreement(
        n=len(pairs),
        exact=sum(d == 0 for d in diffs),
        within_one=sum(d <= 1 for d in diffs),
        mean_abs_diff=sum(diffs) / len(diffs) if diffs else 0.0,
        disagreements=tuple(p for p in pairs if p.judge != p.hand),
    )


def _score(raw: str, column: str, line: int) -> int | None:
    text = raw.strip()
    if not text:
        return None
    if text not in {"0", "1", "2"}:
        raise ValueError(f"line {line}: {column} must be 0, 1 or 2, got {text!r}")
    return int(text)


def read_pairs(path: Path) -> tuple[list[Pair], list[Pair], int]:
    """Mechanism pairs, fix pairs and the number of rows skipped for lack of a score."""
    mechanism: list[Pair] = []
    fix: list[Pair] = []
    skipped = 0
    with path.open(newline="", encoding="utf-8") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            label = f"{row['session_id'][:8]} {row['problem_id']} {row['bug_id']}"
            scores = [
                _score(row.get(name, ""), name, line)
                for name in ("judge_mechanism", "hand_mechanism", "judge_fix", "hand_fix")
            ]
            jm, hm, jf, hf = scores
            if jm is None or hm is None or jf is None or hf is None:
                skipped += 1  # ungraded by the judge, or not hand-graded yet
                continue
            mechanism.append(Pair(label, jm, hm))
            fix.append(Pair(label, jf, hf))
    return mechanism, fix, skipped


def report(name: str, result: Agreement) -> str:
    lines = [
        f"{name}: {result.exact}/{result.n} exact ({result.exact_rate:.0%}), "
        f"{result.within_one}/{result.n} within one point, "
        f"mean difference {result.mean_abs_diff:.2f}"
    ]
    lines += [f"  {p.label}: judge {p.judge}, you {p.hand}" for p in result.disagreements]
    return "\n".join(lines)


async def export(path: Path) -> int:
    settings = get_settings()
    engine = make_engine(settings.db_url)
    rows: list[dict[str, object]] = []
    try:
        async with AsyncSession(engine) as db:
            stmt = (
                select(OutcomeRow, SessionRow, FindingRow)
                .join(SessionRow, col(SessionRow.id) == col(OutcomeRow.session_id))
                .join(FindingRow, col(FindingRow.id) == col(OutcomeRow.finding_id))
                .where(col(OutcomeRow.bug_id).is_not(None), col(SessionRow.graded_at).is_not(None))
                .order_by(col(SessionRow.started_at), col(OutcomeRow.id))
            )
            for outcome, session, finding in (await db.exec(stmt)).all():
                answer = load_answer(
                    settings.problems_dir, session.problem_id, session.problem_version
                )
                bug = next(b for b in answer.bugs if b.id == outcome.bug_id)
                rows.append(
                    {
                        "session_id": session.id,
                        "problem_id": session.problem_id,
                        "bug_id": outcome.bug_id,
                        "key_mechanism": bug.mechanism,
                        "your_explanation": finding.explanation,
                        "your_fix": finding.fix,
                        "judge_mechanism": outcome.judge_mechanism,
                        "judge_fix": outcome.judge_fix,
                        "judge_notes": outcome.judge_notes,
                        "prompt_version": outcome.prompt_version,
                        "hand_mechanism": "",
                        "hand_fix": "",
                    }
                )
    finally:
        await engine.dispose()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in {"export", "check"}:
        print("usage: python -m api.grader.agreement export|check <file.csv>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if argv[0] == "export":
        if path.exists():
            print(f"{path} already exists; not overwriting your hand grades", file=sys.stderr)
            return 1
        count = asyncio.run(export(path))
        print(f"wrote {count} matched findings to {path}; fill in hand_mechanism and hand_fix")
        return 0
    try:
        mechanism, fix, skipped = read_pairs(path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(report("mechanism", compare(mechanism)))
    print(report("fix", compare(fix)))
    if skipped:
        print(f"{skipped} rows skipped (no judge score, or not hand-graded yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
