#!/bin/sh
set -eu
case "${DATABASE_PROVIDER:-sql}" in
    sql) alembic upgrade head ;;
    cosmos) python -m app.storage.cosmos.manage check ;;
    *) echo "Unsupported DATABASE_PROVIDER" >&2; exit 2 ;;
esac
if [ "${DEMO_ENABLED:-false}" = "true" ]; then
    python -m app.seed --demo
else
    python -m app.seed
fi
exec "$@"
