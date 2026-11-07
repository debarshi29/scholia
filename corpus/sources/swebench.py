"""SWE-bench Lite (``princeton-nlp/SWE-bench_Lite``, ``test`` split).

Fields checked against the dataset (Nov 2026): ``repo``, ``instance_id``,
``base_commit``, ``patch``, ``test_patch``, ``problem_statement``, ``hints_text``,
``created_at``, ``version``, ``FAIL_TO_PASS`` and ``PASS_TO_PASS`` (both JSON-encoded
string lists), ``environment_setup_commit``. The dataset card declares no licence;
each upstream repo's licence is checked separately during the build.
"""

import json
from collections.abc import Iterator
from typing import Any

from corpus.sources.base import Candidate
from schema import Source

DATASET = "princeton-nlp/SWE-bench_Lite"
SPLIT = "test"


def to_candidate(row: dict[str, Any]) -> Candidate:
    return Candidate(
        source=Source.SWEBENCH,
        upstream_id=row["instance_id"],
        repo=row["repo"],
        commit=row["base_commit"],
        patch=row["patch"],
        issue=row["problem_statement"],
        test_patch=row["test_patch"],
        failing_tests=list(json.loads(row["FAIL_TO_PASS"] or "[]")),
    )


class SWEBenchLite:
    source = Source.SWEBENCH

    def candidates(self) -> Iterator[Candidate]:
        from datasets import load_dataset  # heavy import, only when building

        for row in load_dataset(DATASET, split=SPLIT):
            yield to_candidate(row)
