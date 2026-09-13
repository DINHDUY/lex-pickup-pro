#!/bin/sh
set -eu
alembic upgrade head
if [ "${DEMO_ENABLED:-false}" = "true" ]; then
    python -m app.seed --demo
else
    python -m app.seed
fi
exec "$@"
