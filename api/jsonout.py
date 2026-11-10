"""Strict parsing of model JSON output.

Some models wrap JSON in a Markdown code fence even in JSON mode. The fence is removed;
anything else that is not exactly one valid object of the expected shape is an error.
Nothing is repaired or guessed.
"""

import re

from pydantic import BaseModel

_FENCE = re.compile(r"^```(?:json)?\s*\n(?P<body>.*?)\n?```$", re.DOTALL | re.IGNORECASE)


def strip_fence(raw: str) -> str:
    text = raw.strip()
    m = _FENCE.match(text)
    return m["body"].strip() if m else text


def parse_model_json[T: BaseModel](raw: str, model: type[T]) -> T:
    """Validate ``raw`` as ``model``. Raises ``pydantic.ValidationError`` when it does not fit."""
    return model.model_validate_json(strip_fence(raw))
