import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from corpus.sources.swebench import PAGE, DatasetError, SWEBenchLite, fetch_rows, to_candidate
from schema import Source


def _row(i: int) -> dict[str, Any]:
    return {
        "instance_id": f"org__repo-{i}",
        "repo": "org/repo",
        "base_commit": "c" * 40,
        "patch": "diff --git a/a.py b/a.py\n",
        "test_patch": "diff --git a/tests/test_a.py b/tests/test_a.py\n",
        "problem_statement": "It breaks.",
        "FAIL_TO_PASS": json.dumps(["tests/test_a.py::test_x"]),
    }


def _client(total: int, **page_extra: Any) -> tuple[httpx.Client, list[int]]:
    offsets: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        offset = int(req.url.params["offset"])
        offsets.append(offset)
        assert req.url.params["dataset"] == "princeton-nlp/SWE-bench_Lite"
        rows = [
            {"row_idx": i, "row": _row(i), "truncated_cells": []}
            for i in range(offset, min(offset + PAGE, total))
        ]
        return httpx.Response(200, json={"rows": rows, "num_rows_total": total, **page_extra})

    return httpx.Client(transport=httpx.MockTransport(handler)), offsets


def test_fetch_rows_pages_in_order() -> None:
    client, offsets = _client(250)
    rows = fetch_rows(client)
    assert offsets == [0, 100, 200]
    assert [r["instance_id"] for r in rows] == [f"org__repo-{i}" for i in range(250)]


def test_partial_split_is_an_error() -> None:
    client, _ = _client(5, partial=True)
    with pytest.raises(DatasetError, match="partial"):
        fetch_rows(client)


def test_truncated_cells_are_an_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        item = {"row_idx": 0, "row": _row(0), "truncated_cells": ["patch"]}
        return httpx.Response(200, json={"rows": [item], "num_rows_total": 1})

    with pytest.raises(DatasetError, match="truncated"):
        fetch_rows(httpx.Client(transport=httpx.MockTransport(handler)))


def test_to_candidate_decodes_failing_tests() -> None:
    cand = to_candidate(_row(7))
    assert cand.source is Source.SWEBENCH
    assert (cand.upstream_id, cand.repo) == ("org__repo-7", "org/repo")
    assert cand.failing_tests == ["tests/test_a.py::test_x"]


def test_cached_rows_need_no_network(tmp_path: Path) -> None:
    (tmp_path / "swebench_lite_test.json").write_text(json.dumps([_row(1), _row(2)]))
    ids = [c.upstream_id for c in SWEBenchLite(tmp_path).candidates()]
    assert ids == ["org__repo-1", "org__repo-2"]
