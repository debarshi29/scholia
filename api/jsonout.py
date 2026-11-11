"""Strict parsing of model JSON output.

Some models wrap JSON in a Markdown code fence even in JSON mode, or end it with a
stray closing fence. A leading fence line and a trailing fence are removed; anything
else that is not exactly one valid object of the expected shape is an error.
Nothing is repaired or guessed.
"""

import re

from pydantic import BaseModel

_OPEN = re.compile(r"^```(?:json)?[ \t]*\r?\n", re.IGNORECASE)
_CLOSE = re.compile(r"\r?\n?```$")


def strip_fence(raw: str) -> str:
    text = raw.strip()
    text = _OPEN.sub("", text, count=1)
    return _CLOSE.sub("", text, count=1).strip()


def parse_model_json[T: BaseModel](raw: str, model: type[T]) -> T:
    """Validate ``raw`` as ``model``. Raises ``pydantic.ValidationError`` when it does not fit."""
    return model.model_validate_json(strip_fence(raw))
