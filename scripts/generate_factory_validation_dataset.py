#!/usr/bin/env python3
"""Generate the versioned synthetic factory candidate dataset and output schema."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.validation.synthetic_factory import (  # noqa: E402
    write_dataset,
    write_output_schema,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "validation" / "datasets" / "synthetic_factory_v1",
    )
    args = parser.parse_args()
    manifest = write_dataset(args.output)
    write_output_schema(
        ROOT
        / "validation"
        / "llm"
        / "schemas"
        / "factory_document_extraction_v1.json"
    )
    print(
        f"generated {manifest['scenario_count']} scenarios "
        f"with dataset_sha256={manifest['dataset_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
