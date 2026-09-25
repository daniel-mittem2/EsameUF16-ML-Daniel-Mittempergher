"""Validate the hook JSON file and test the run_unit_tests.py script."""
import json
import subprocess
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # .kiro/scripts/ → .kiro/ → repo root

# ── 1. Schema validation ─────────────────────────────────────────────────────
hook_file = ROOT / ".kiro" / "hooks" / "unit-tests-on-save.json"
with open(hook_file) as f:
    d = json.load(f)

assert d.get("version") == "v1", f"version must be v1, got {d.get('version')}"
hooks = d.get("hooks", [])
assert len(hooks) == 1, f"expected 1 hook, got {len(hooks)}"
h = hooks[0]
assert h.get("name"), "name missing"
assert h.get("trigger") == "PostFileSave", f"trigger is {h.get('trigger')!r}"
assert h.get("matcher"), "matcher missing"
assert h["action"]["type"] == "command", "action type must be command"
assert h["action"]["command"], "command missing"
print("1. Schema validation: OK")
print(f"   version : {d['version']}")
print(f"   trigger : {h['trigger']}")
print(f"   matcher : {h['matcher']}")
print(f"   command : {h['action']['command']}")

# ── 2. Matcher regex compiles and matches expected paths ─────────────────────
pattern = re.compile(h["matcher"])
test_paths = [
    # should match
    (True,  r"C:\Users\x\Exam\techconf-exam\services\user-service\app\routes.py"),
    (True,  r"C:\Users\x\Exam\techconf-exam\services\event-service\routes.py"),
    (True,  "Exam/techconf-exam/services/user-service/app/routes.py"),
    # should NOT match
    (False, r"C:\Users\x\Exam\techconf-exam\contracts\openapi\user-service.yaml"),
    (False, r"C:\Users\x\Exam\techconf-exam\tests\integration\test_user.py"),
    (False, r"C:\Users\x\unrelated\file.py"),
]
errors = []
for expected, path in test_paths:
    got = bool(pattern.search(path))
    status = "OK" if got == expected else "FAIL"
    if status == "FAIL":
        errors.append(f"   {status}: expected={expected}, path={path!r}")
    print(f"   {status}: match={got} expected={expected}  {path[:60]}")
assert not errors, "\n".join(errors)
print("2. Matcher test: OK")

# ── 3. Script syntax check ───────────────────────────────────────────────────
script = ROOT / ".kiro" / "scripts" / "run_unit_tests.py"
result = subprocess.run([sys.executable, "-m", "py_compile", str(script)], capture_output=True, text=True)
assert result.returncode == 0, f"Syntax error:\n{result.stderr}"
print("3. Script syntax: OK")

# ── 4. Dry-run: empty stdin (no file path) ───────────────────────────────────
r = subprocess.run([sys.executable, str(script)], input="", capture_output=True, text=True, cwd=str(ROOT))
assert r.returncode == 0, f"dry-run (empty stdin) exited {r.returncode}"
assert "skipping" in r.stdout.lower(), f"expected skip message, got: {r.stdout!r}"
print(f"4. Dry-run empty stdin: OK — {r.stdout.strip()!r}")

# ── 5. Dry-run: path outside services/ ──────────────────────────────────────
payload = json.dumps({"file": str(ROOT / "README.md")})
r = subprocess.run([sys.executable, str(script)], input=payload, capture_output=True, text=True, cwd=str(ROOT))
assert r.returncode == 0, f"out-of-scope path exited {r.returncode}"
# no output expected (silent skip)
print(f"5. Dry-run out-of-scope path: OK — stdout={r.stdout.strip()!r}")

# ── 6. Real service path: run existing unit tests ────────
service_path = str(ROOT / "Exam" / "techconf-exam" / "services" / "user-service" / "app" / "routes.py")
payload = json.dumps({"file": service_path})
r = subprocess.run([sys.executable, str(script)], input=payload, capture_output=True, text=True, cwd=str(ROOT))
assert r.returncode == 0, f"service unit tests exited {r.returncode}"
print(f"6. Service path: actual unit tests: OK — stdout={r.stdout.strip()!r}")

print()
print("All hook checks passed.")
print()
print("MANUAL VERIFICATION REQUIRED (cannot automate from terminal):")
print("  Open Kiro IDE → Explorer panel → 'Agent Hooks' section.")
print("  Confirm 'Run Unit Tests on Python Save' is listed and enabled (toggle ON).")
print("  To test activation: save any .py file under services/user-service/ after")
print("  scaffolding and observe the hook output in the Kiro hook log panel.")
