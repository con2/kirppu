#!/bin/sh

if [ -n "$NODE_PATH" ]; then
    PATH="$PATH:$NODE_PATH/.bin"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
