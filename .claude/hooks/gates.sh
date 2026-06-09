#!/usr/bin/env bash
# Deterministic gates. In Phase 1 these are wired as Claude Code hooks so they
# run and block automatically. For now they are runnable by hand or by the orchestrator.
set -e
SKILL="$(cd "$(dirname "$0")/../skills/salt-input-builder" && pwd)"
# Pick whichever interpreter this machine exposes. Some boxes (e.g. Windows
# with the python.org installer) only put `python` on PATH, not `python3`.
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else echo "[gate] no python interpreter on PATH (need python3 or python)" >&2; exit 1; fi
echo "[gate] running the test suite (must stay green before any skill change ships)"
"$PY" "$SKILL/tests/run_tests.py"
