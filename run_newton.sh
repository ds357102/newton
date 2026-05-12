#!/usr/bin/env bash
# Newton local quickstart.
# Creates a venv if needed, upgrades pip, installs runtime deps, starts uvicorn.
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "→ creating .venv"
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
. .venv/bin/activate

echo "→ upgrading pip"
python -m pip install --quiet --upgrade pip setuptools wheel 2>&1 | tail -1 || true

echo "→ installing dependencies (first run only takes ~30s)"
python -m pip install --quiet \
  "fastapi>=0.115" \
  "uvicorn[standard]>=0.30" \
  "pydantic>=2.7" \
  "pydantic-settings>=2.4" \
  "httpx>=0.27" \
  "feedparser>=6.0" \
  "anthropic>=0.34" \
  "structlog>=24.1" \
  "python-multipart" 2>&1 | tail -3

# Load .env if present
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

echo
echo "Newton starting on http://localhost:8080"
echo "  · UI:        http://localhost:8080/"
echo "  · API docs:  http://localhost:8080/docs"
echo "  · health:    http://localhost:8080/healthz"
echo

export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
exec python -m uvicorn newton.main:app --host 0.0.0.0 --port 8080 --reload
