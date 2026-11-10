"""SWE-bench Lite (``princeton-nlp/SWE-bench_Lite``, ``test`` split).

Rows are read from the Hugging Face dataset viewer's JSON API with ``httpx`` and cached
under ``data/repos/_datasets/``. The ``datasets`` package is not used: it needs
``pyarrow``, whose native library Windows Smart App Control blocks on the owner's machine.

Fields checked against the dataset (Nov 2026): ``repo``, ``instance_id``,
``base_commit``, ``patch``, ``test_patch``, ``problem_statement``, ``hints_text``,
``created_at``, ``version``, ``FAIL_TO_PASS`` and ``PASS_TO_PASS`` (both JSON-encoded
string lists), ``environment_setup_commit``. The dataset card declares no licence;
each upstream repo's licence is checked separately during the build.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from corpus.sources.base import Candidate
from schema import Source

DATASET = "princeton-nlp/SWE-bench_Lite"
CONFIG = "default"
SPLIT = "test"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100
"""The API's maximum page size."""


class DatasetError(RuntimeError):
    pass


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


def fetch_rows(client: httpx.Client) -> list[dict[str, Any]]:
    """Every row of the split, in dataset order. Fails loudly on truncated or missing data."""
    rows: list[dict[str, Any]] = []
    total: int | None = None
    while total is None or len(rows) < total:
        resp = client.get(
            ROWS_URL,
            params={
                "dataset": DATASET,
                "config": CONFIG,
                "split": SPLIT,
                "offset": len(rows),
                "length": PAGE,
            },
        )
        resp.raise_for_status()
        page = resp.json()
        total = int(page["num_rows_total"])
        if page.get("partial"):
            raise DatasetError("the dataset viewer only has a partial copy of the split")
        if not page["rows"]:
            raise DatasetError(f"no rows at offset {len(rows)} of {total}")
        for item in page["rows"]:
            if item.get("truncated_cells"):
                raise DatasetError(f"row {item.get('row_idx')} has truncated cells")
            rows.append(item["row"])
    return rows


class SWEBenchLite:
    source = Source.SWEBENCH

    def __init__(self, cache_dir: Path) -> None:
        self.cache = cache_dir / "swebench_lite_test.json"

    def rows(self) -> list[dict[str, Any]]:
        if self.cache.is_file():
            cached: list[dict[str, Any]] = json.loads(self.cache.read_text(encoding="utf-8"))
            return cached
        with httpx.Client(timeout=60.0) as client:
            rows = fetch_rows(client)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        self.cache.write_text(json.dumps(rows), encoding="utf-8")
        return rows

    def candidates(self) -> Iterator[Candidate]:
        for row in self.rows():
            yield to_candidate(row)
