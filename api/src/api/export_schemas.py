"""Write contracts/schemas/*.json from the contract models: `python -m api.export_schemas`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from api.contract import Discovery, Forecast, Heatmap, Sphere, StarTarget

MODELS: dict[str, type[BaseModel]] = {
    "Sphere": Sphere,
    "StarTarget": StarTarget,
    "Discovery": Discovery,
    "Forecast": Forecast,
    "heatmap": Heatmap,
}

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "contracts" / "schemas"


def render() -> dict[str, str]:
    return {
        f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        + "\n"
        for name, model in MODELS.items()
    }


def main() -> int:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, text in render().items():
        (SCHEMA_DIR / filename).write_text(text)
        print(f"wrote {SCHEMA_DIR / filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
