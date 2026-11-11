import pytest
from pydantic import BaseModel, ValidationError

from api.jsonout import parse_model_json, strip_fence


class M(BaseModel):
    n: int


@pytest.mark.parametrize(
    "raw",
    [
        '{"n": 1}',
        '```json\n{"n": 1}\n```',
        '```\n{"n": 1}\n```',
        '  ```JSON\n{\n "n": 1\n}\n```\n',
        '{"n": 1}\n```',  # closing fence only: seen from the configured model
        '```json\n{"n": 1}',
        '```json\r\n{"n": 1}\r\n```',
    ],
)
def test_accepts_plain_and_fenced_json(raw: str) -> None:
    assert parse_model_json(raw, M).n == 1


@pytest.mark.parametrize(
    "raw",
    [
        'Sure! {"n": 1}',
        '{"n": 1} Hope that helps.',
        '```json\n{"n": "x"}\n```',
        "",
        "```",
        '{"n": 1} {"n": 2}',
        'Here you go:\n```json\n{"n": 1}\n```',
    ],
)
def test_rejects_everything_else(raw: str) -> None:
    with pytest.raises(ValidationError):
        parse_model_json(raw, M)


def test_strip_fence_leaves_inner_backticks() -> None:
    assert strip_fence('{"s": "a ``` b"}') == '{"s": "a ``` b"}'
