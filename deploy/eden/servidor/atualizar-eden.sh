#!/usr/bin/env bash
# Éden (servidor): atualiza para a versão mais nova do GitHub (branch main).
#
#   sudo /opt/eden/atualizar-eden.sh
#
# 1. faz um backup automático (ficam os 5 mais novos);
# 2. guarda a versão atual da imagem (eden:anterior);
# 3. monta a nova e liga;
# 4. se a nova não responder, volta sozinho para a anterior.
set -euo pipefail

EDEN_DIR="${EDEN_DIR:-/opt/eden}"
TESTE="${EDEN_MODO_TESTE:-0}"
cd "$EDEN_DIR"

responde() {
  for _ in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

echo "Backup antes de atualizar…"
"$EDEN_DIR/backup-eden.sh" --tipo auto --manter 5

tem_anterior=0
if docker image inspect eden:local >/dev/null 2>&1; then
  docker tag eden:local eden:anterior
  tem_anterior=1
fi

echo "Montando a versão nova (pode demorar)…"
if [ "$TESTE" = 1 ]; then
  docker compose up -d --no-build
else
  docker compose build eden
  docker compose up -d
fi

if responde; then
  echo "Pronto! Éden atualizado."
  exit 0
fi

echo "A versão nova não respondeu."
docker compose logs --tail 40 eden || true
if [ "$tem_anterior" = 1 ]; then
  echo "Voltando para a versão anterior…"
  docker tag eden:anterior eden:local
  docker compose up -d --no-build --force-recreate eden
  if responde; then
    echo "Éden voltou na versão anterior. Mande as linhas acima para o Claude."
  else
    echo "A versão anterior também não respondeu. Mande as linhas acima para o Claude."
  fi
fi
exit 1
