#!/bin/bash

set -ueo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Allow setting either DATABASE_URL (takes precedence) or POSTGRES_*
POSTGRES_USERNAME="${POSTGRES_USERNAME:-infokala}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-secret}"
POSTGRES_HOSTNAME="${POSTGRES_HOSTNAME:-postgres}"
POSTGRES_DATABASE="${POSTGRES_DATABASE:-infokala}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_EXTRAS="${POSTGRES_EXTRAS-}"
export DATABASE_URL="${DATABASE_URL:-psql://$POSTGRES_USERNAME:$POSTGRES_PASSWORD@$POSTGRES_HOSTNAME:$POSTGRES_PORT/$POSTGRES_DATABASE}${POSTGRES_EXTRAS}"

# Wait for postgres to be up before continuing
"$DIR/wait-for-it.sh" -s -t 60 "$POSTGRES_HOSTNAME:$POSTGRES_PORT"

exec "$@"
