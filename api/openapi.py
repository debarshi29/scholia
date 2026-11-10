"""Write the API's OpenAPI document, for the frontend client generator (``pnpm gen:api``).

uv run python -m api.openapi web/openapi.json
"""

import json
import sys
from pathlib import Path

from api.main import create_app


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m api.openapi <output.json>", file=sys.stderr)
        return 2
    Path(argv[0]).write_text(json.dumps(create_app().openapi(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
