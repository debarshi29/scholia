"""Gemini classification pass: assigns ``category`` and ``mechanism`` to a Tier 0 bug.

Results are stored with ``category_source: "llm"`` so they can be reviewed later.
Only open-source, allowlisted code reaches this module (invariant 7): the build
checks the licence before calling it.
"""

import logging
import re
from dataclasses import dataclass
from importlib import resources
from typing import Protocol

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from api.backends.gemini import TRANSPORT_ERRORS, transient
from api.jsonout import parse_model_json
from schema import BugCategory

log = logging.getLogger(__name__)

MAX_ISSUE_CHARS = 6000
MAX_CONTEXT_CHARS = 12000


class Classification(BaseModel):
    category: BugCategory
    mechanism: str = Field(min_length=10, max_length=800)


class ClassifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClassifyInput:
    issue: str
    """Upstream issue / problem statement."""
    buggy_context: str
    """Buggy source around the changed regions, with line numbers."""
    fix_diff: str


class Classifier(Protocol):
    prompt_version: str

    def classify(self, item: ClassifyInput) -> Classification: ...


def load_prompt() -> tuple[str, str]:
    text = resources.files("corpus").joinpath("prompts/classify.md").read_text("utf-8")
    m = re.match(r"<!-- version: (\S+) -->\n", text)
    if not m:
        raise ClassifyError("classify prompt is missing its version header")
    return m[1], text[m.end() :]


def render(item: ClassifyInput) -> str:
    return (
        "## Issue\n"
        f"{item.issue[:MAX_ISSUE_CHARS]}\n\n"
        "## Buggy source (line numbers are the buggy version's)\n"
        f"```python\n{item.buggy_context[:MAX_CONTEXT_CHARS]}\n```\n\n"
        "## Fix diff\n"
        f"```diff\n{item.fix_diff[:MAX_CONTEXT_CHARS]}\n```\n"
    )


class GeminiClassifier:
    def __init__(self, api_key: str, model: str) -> None:
        if not model:
            raise ClassifyError("JUDGE_MODEL is not set")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self.prompt_version, self._system = load_prompt()

    @retry(
        retry=retry_if_exception(transient),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _call(self, prompt: str) -> str:
        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=self._system,
                response_mime_type="application/json",
                response_schema=Classification,
                temperature=0,
            ),
        )
        return resp.text or ""

    def classify(self, item: ClassifyInput) -> Classification:
        prompt = render(item)
        last: Exception | None = None
        for _attempt in range(2):  # one retry on malformed output, then give up
            try:
                raw = self._call(prompt)
            except TRANSPORT_ERRORS as exc:
                raise ClassifyError(f"gemini unreachable: {type(exc).__name__}") from exc
            try:
                return parse_model_json(raw, Classification)
            except ValidationError as exc:
                log.warning("classifier output invalid", extra={"raw": raw[:500]})
                last = exc
        raise ClassifyError(f"invalid classifier output after retry: {last}")


def numbered_context(source_lines: list[str], regions: list[tuple[int, int]], pad: int = 15) -> str:
    """Buggy lines around each region, prefixed with their line numbers."""
    keep: set[int] = set()
    for a, b in regions:
        keep.update(range(max(1, a - pad), min(len(source_lines), b + pad) + 1))
    out: list[str] = []
    prev = 0
    for n in sorted(keep):
        if prev and n != prev + 1:
            out.append("...")
        out.append(f"{n:5d}  {source_lines[n - 1]}")
        prev = n
    return "\n".join(out)
