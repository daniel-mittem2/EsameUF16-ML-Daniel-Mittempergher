#!/usr/bin/env python
"""
Hook script: run unit tests for the affected service when a .py file is saved.

Kiro PostFileSave hooks receive context on stdin as JSON:
    {"file": "<absolute path of saved file>", ...}

The script:
1. Reads the saved file path from stdin.
2. Derives the service root directory (the first ancestor whose name ends with
   '-service' under the techconf-exam/services/ tree).
3. Runs `py -3.12 -m pytest tests/unit/ -v --tb=short` from that service root.
4. Exits with the pytest return code so Kiro can surface failures.

Windows notes:
- Paths from Kiro may use either forward or back slashes; both are normalised.
- The script is invoked by the hook with an explicit interpreter to avoid
  relying on PATH resolution: `py -3.12 .kiro/scripts/run_unit_tests.py`
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _find_service_dir(file_path: str) -> Path | None:
    """
    Walk up from `file_path` until we find a directory that looks like a
    service root: it must sit under .../techconf-exam/services/ and contain
    an `app/` sub-directory.

    Returns the service root Path, or None if not found.
    """
    p = Path(file_path).resolve()
    # Normalise to forward slashes for matching
    parts = p.parts

    for i, part in enumerate(parts):
        if part == "services" and i + 1 < len(parts):
            svc_dir = Path(*parts[: i + 2])
            # Sanity: must have an app/ package (or we haven't scaffolded yet)
            # We still run even if app/ doesn't exist yet, so tests/unit/ can
            # be created first — just check that the dir itself exists.
            if svc_dir.is_dir():
                return svc_dir
    return None


def main() -> int:
    # Read Kiro hook context from stdin
    raw = sys.stdin.read().strip()
    file_path: str = ""
    if raw:
        try:
            data = json.loads(raw)
            file_path = data.get("file", "")
        except json.JSONDecodeError:
            # stdin not JSON: fall through with empty path
            pass

    if not file_path:
        print("[hook] No file path received — skipping.", flush=True)
        return 0

    svc_dir = _find_service_dir(file_path)
    if svc_dir is None:
        # File is not inside a service directory; nothing to run.
        return 0

    tests_dir = svc_dir / "tests" / "unit"
    if not tests_dir.is_dir():
        print(
            f"[hook] Unit tests not found at {tests_dir} — skipping.",
            flush=True,
        )
        return 0

    svc_name = svc_dir.name
    print(f"[hook] Running unit tests for: {svc_name}", flush=True)

    result = subprocess.run(
        ["py", "-3.12", "-m", "pytest", str(tests_dir), "-v", "--tb=short", "-q"],
        cwd=str(svc_dir),
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
