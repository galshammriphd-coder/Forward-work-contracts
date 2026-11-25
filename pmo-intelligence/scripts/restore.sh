#!/usr/bin/env bash
# Restore a backup made by backup.sh. This REPLACES the current database and documents.
#   ./scripts/restore.sh ./backups/20270101-020000
set -euo pipefail
src="${1:?usage: restore.sh <backup-folder>}"
( cd "$src" && sha256sum -c SHA256SUMS )
read -r -p "This replaces the current database and documents. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "Cancelled."; exit 1; }
docker compose stop app
docker compose exec -T db pg_restore -U pmo -d pmo --clean --if-exists < "$src/pmo.dump"
docker compose run --rm -T --entrypoint sh app -c "rm -rf /data/documents && tar -C /data -xzf -" < "$src/documents.tar.gz"
docker compose start app
echo "Restore complete."
