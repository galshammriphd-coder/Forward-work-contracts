#!/usr/bin/env bash
# Back up the database and the document store of a docker-compose deployment.
#   ./scripts/backup.sh [target-dir]        (run from the pmo-intelligence folder)
set -euo pipefail
out="${1:-./backups}/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
docker compose exec -T db pg_dump -U pmo -Fc pmo > "$out/pmo.dump"
docker compose exec -T app tar -C /data -czf - documents > "$out/documents.tar.gz"
( cd "$out" && sha256sum pmo.dump documents.tar.gz > SHA256SUMS )
echo "Backup written to $out"
