#!/usr/bin/env bash
# Éden (servidor): faz um backup dos dados (conversas, gastos, perfil,
# memória; nunca chaves) na pasta /opt/eden/backups.
#
#   sudo /opt/eden/backup-eden.sh                            backup manual
#   sudo /opt/eden/backup-eden.sh --tipo diario --manter 14  (o backup diário usa assim)
#
# Pode rodar com o Éden ligado.
set -euo pipefail

EDEN_DIR="${EDEN_DIR:-/opt/eden}"
tipo="manual"
manter=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tipo) tipo="${2:?}"; shift 2 ;;
    --manter) manter="${2:?}"; shift 2 ;;
    *) echo "uso: backup-eden.sh [--tipo manual|auto|diario] [--manter N]" >&2; exit 2 ;;
  esac
done

cd "$EDEN_DIR"
[ -d backups ] || install -d -m 700 -o 10001 -g 10001 backups
args=(criar /backups --tipo "$tipo" --hora "$(date +%Y%m%d-%H%M%S)")
if [ -n "$manter" ]; then args+=(--manter "$manter"); fi
docker compose run --rm -T backup "${args[@]}"
