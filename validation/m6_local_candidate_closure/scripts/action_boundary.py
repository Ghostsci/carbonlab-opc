#!/usr/bin/env python3
"""The only executable action boundary shipped by the M6 local candidate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from release_guard import Rejection, authorize


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: action_boundary.py REQUEST.json", file=sys.stderr)
        return 2
    package_root = Path(__file__).resolve().parent.parent
    try:
        authorization = authorize(Path(sys.argv[1]), package_root)
    except Rejection as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, sort_keys=True))
        return 42

    # There is deliberately no arbitrary subprocess, shell, network, remote, or
    # production dispatcher. The allowlist has one read-only local verification
    # action and its implementation is the successful verification above.
    result = {
        "decision": "LOCAL_ACTION_COMPLETED",
        "executed_action": authorization["action"],
        "side_effects": [],
        "target": authorization["target"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
