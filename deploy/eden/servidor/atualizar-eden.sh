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

# Pasta do seu Éden: a do próprio script, a não ser que EDEN_DIR diga outra.
EDEN_DIR="${EDEN_DIR:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")}"
export EDEN_DIR
TESTE="${EDEN_MODO_TESTE:-0}"
cd "$EDEN_DIR"
grep -qx 'name: eden' docker-compose.yml || { echo "ERRO: $EDEN_DIR não é o Éden principal" >&2; exit 1; }
dc() { docker compose -p eden "$@"; }

responde() {  # responde [PORTA]
  for _ in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:${1:-8000}/health" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}

# Os Édens de outras pessoas (nova-pessoa.sh) usam a mesma imagem: depois de
# atualizar o seu, cada um recebe o docker-compose.yml e os scripts novos
# (com o nome e a porta dele), faz o próprio backup e liga na versão nova.
# Só pastas com nome de pessoa (eden-ana, eden-pai): "eden-ana.desligado-…"
# fica de fora. Se o backup de uma pessoa falhar, ela fica como estava.
atualizar_outros() {
  local d nome projeto porta falhou=0 base
  base="$(basename "$EDEN_DIR")"
  for d in "$EDEN_DIR"-*/; do
    d="${d%/}"
    [[ "$(basename "$d")" =~ ^${base}-([a-z][a-z0-9]{1,15})$ ]] || continue
    nome="${BASH_REMATCH[1]}"
    projeto="$base-$nome"
    [ -f "$d/docker-compose.yml" ] && [ -f "$d/.env" ] || continue
    porta="$(sed -n 's/.*"127\.0\.0\.1:\(800[1-5]\):8000".*/\1/p' "$d/docker-compose.yml" | head -1 || true)"
    if ! grep -qx "name: $projeto" "$d/docker-compose.yml" || [ -z "$porta" ]; then
      echo "  pulei $d: o docker-compose.yml não é o do Éden de \"$nome\""
      falhou=1
      continue
    fi
    echo "Atualizando o Éden de \"$nome\"…"
    sed -e "s/^name: eden\$/name: $projeto/" \
      -e "s/\"127\\.0\\.0\\.1:8000:8000\"/\"127.0.0.1:$porta:8000\"/" \
      "$EDEN_DIR/docker-compose.yml" > "$d/docker-compose.yml.novo"
    if grep -qx "name: $projeto" "$d/docker-compose.yml.novo" \
      && grep -q "\"127.0.0.1:$porta:8000\"" "$d/docker-compose.yml.novo"; then
      chmod 644 "$d/docker-compose.yml.novo"
      mv "$d/docker-compose.yml.novo" "$d/docker-compose.yml"
    else
      rm -f "$d/docker-compose.yml.novo"
      echo "  pulei \"$nome\": não consegui montar o docker-compose.yml novo"
      falhou=1
      continue
    fi
    install -m 755 "$EDEN_DIR/backup-eden.sh" "$EDEN_DIR/restaurar-eden.sh" "$d/"
    if ! EDEN_DIR="$d" "$d/backup-eden.sh" --tipo auto --manter 5; then
      echo "  o backup de \"$nome\" não deu certo: o Éden dele ficou como estava"
      falhou=1
      continue
    fi
    (cd "$d" && docker compose -p "$projeto" up -d --no-build) || falhou=1
    if responde "$porta"; then
      echo "  ok: \"$nome\""
    else
      echo "  \"$nome\" não respondeu: veja com: cd $d && sudo docker compose logs --tail 40 eden"
      falhou=1
    fi
  done
  return "$falhou"
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
  dc up -d --no-build
else
  dc build eden
  dc up -d
fi

if responde; then
  echo "Pronto! Éden atualizado."
  atualizar_outros || exit 1
  exit 0
fi

echo "A versão nova não respondeu."
dc logs --tail 40 eden || true
if [ "$tem_anterior" = 1 ]; then
  echo "Voltando para a versão anterior…"
  docker tag eden:anterior eden:local
  dc up -d --no-build --force-recreate eden
  if responde; then
    echo "Éden voltou na versão anterior. Mande as linhas acima para o Claude."
  else
    echo "A versão anterior também não respondeu. Mande as linhas acima para o Claude."
  fi
fi
exit 1
