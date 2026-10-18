#!/usr/bin/env bash
# Éden (servidor): faz um backup dos dados (conversas, gastos, perfil,
# memória; nunca chaves) na pasta backups ao lado deste script.
#
#   sudo /opt/eden/backup-eden.sh                            backup manual
#   sudo /opt/eden/backup-eden.sh --tipo diario --manter 14  (o backup diário usa assim)
#
# Pode rodar com o Éden ligado.
set -euo pipefail

# Pasta deste Éden: a do próprio script (o Éden de outra pessoa tem a cópia
# dele em /opt/eden-NOME), a não ser que EDEN_DIR diga outra.
EDEN_DIR="${EDEN_DIR:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")}"
# Nome do projeto no Docker e porta: os do docker-compose.yml desta pasta. O
# nome vai sempre com -p, então nenhuma linha do .env consegue trocar de Éden.
PROJETO="$(sed -n 's/^name: *\([a-z0-9][a-z0-9_-]*\) *$/\1/p' "$EDEN_DIR/docker-compose.yml" 2>/dev/null | head -1 || true)"
[ -n "$PROJETO" ] || { echo "ERRO: não achei o nome do Éden em $EDEN_DIR/docker-compose.yml" >&2; exit 1; }
PORTA="$(sed -n 's/.*"127\.0\.0\.1:\([0-9]\{4\}\):8000".*/\1/p' "$EDEN_DIR/docker-compose.yml" | head -1 || true)"
PORTA="${PORTA:-8000}"
dc() { docker compose -p "$PROJETO" "$@"; }
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
echo "Backup do Éden \"$PROJETO\" ($EDEN_DIR)…"
[ -d backups ] || install -d -m 700 -o 10001 -g 10001 backups
args=(criar /backups --tipo "$tipo" --hora "$(date +%Y%m%d-%H%M%S)")
if [ -n "$manter" ]; then args+=(--manter "$manter"); fi
dc run --rm -T backup "${args[@]}"
