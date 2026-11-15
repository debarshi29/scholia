"""Run a Python file's doctests in a scratch directory, with a timeout.

Used by the planted-bug corpus build (to verify a mutation is caught) and by the grader (to
run a submitted fix against the same tests). The file is the only thing in the directory.
It executes Python, so callers must only pass code the user is entitled to run locally.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT_S = 20
_RESULT = re.compile(r"(\d+) passed and (\d+) failed")


def doctest_result(name: str, text: str) -> tuple[int, int] | None:
    """``(passed, failed)`` of the file's doctests, or ``None`` if they could not run."""
    with tempfile.TemporaryDirectory(prefix="scholia-planted-") as tmp:
        (Path(tmp) / name).write_text(text, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "doctest", "-v", name],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return None
    found = _RESULT.findall(proc.stdout)
    if not found:
        return None
    passed, failed = found[-1]
    return int(passed), int(failed)
