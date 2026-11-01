import json
import logging

from api.log import JsonFormatter


def test_json_formatter_includes_extras() -> None:
    record = logging.makeLogRecord(
        {"name": "scholia.test", "levelname": "INFO", "msg": "hello %s", "args": ("world",)}
    )
    record.session_id = "s1"
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hello world"
    assert out["level"] == "INFO"
    assert out["session_id"] == "s1"
    assert "args" not in out
