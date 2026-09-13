#!/bin/sh
# Disposable demo data. Never points at the developer's database.
set -eu
cd "$(dirname "$0")"
test_dir=$(mktemp -d "${TMPDIR:-/tmp}/lex-e2e.XXXXXX")
api_pid=
cleanup() {
    if [ -n "$api_pid" ]; then kill "$api_pid" 2>/dev/null || true; fi
    rm -rf "$test_dir"
}
trap cleanup EXIT INT TERM
export DATABASE_URL="sqlite:///$test_dir/club.db"
export APP_ENV=test DEMO_ENABLED=true COOKIE_SECURE=false
export FRONTEND_URL=http://127.0.0.1:5187
export CORS_ORIGINS='["http://127.0.0.1:5187","http://localhost:5187"]'
uv run alembic upgrade head
uv run python -m app.seed --demo
uv run uvicorn app.main:app --host 127.0.0.1 --port 8017 &
api_pid=$!
wait "$api_pid"
