#!/bin/sh
set -e

# Ensure files and logs directories exist
mkdir -p /app/files /app/logs

# Fix permissions so 'app' user can read/write mounted volumes
chown -R app:app /app/files /app/logs 2>/dev/null || true
chmod -R u+rwX,g+rwX /app/files /app/logs 2>/dev/null || true

# Execute CMD as non-root 'app' user
exec su-exec app "$@"
