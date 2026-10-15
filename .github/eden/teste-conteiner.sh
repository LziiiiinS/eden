#!/usr/bin/env bash
# Éden: liga a imagem do jeito do notebook/servidor (com chaves de teste, sem
# chamar nenhuma IA de verdade) e confere o básico: chave de acesso, conversas
# guardadas, modos do Éden, gastos, página do app e dados que sobrevivem a um
# reinício.
set -euo pipefail

IMAGEM="${1:-eden:local}"
KEY="oj_sk_teste_$(date +%s)"
BASE="http://127.0.0.1:8000"

docker volume create eden-teste >/dev/null
# Igual ao docker-compose: programa só-leitura, /tmp na memória.
docker run -d --name eden-teste -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:rw,size=128m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -e OPENJARVIS_HOME=/dados \
  -e OPENJARVIS_API_KEY="$KEY" \
  -e OPENAI_API_KEY=sk-teste-falsa \
  -v eden-teste:/dados \
  --entrypoint sh "$IMAGEM" /app/deploy/eden/iniciar-no-conteiner.sh >/dev/null

limpar() {
  echo "--- registro do contêiner (final) ---"
  docker logs --tail 60 eden-teste 2>&1 || true
  docker rm -f eden-teste >/dev/null 2>&1 || true
  docker volume rm eden-teste >/dev/null 2>&1 || true
}
trap limpar EXIT

esperar() {
  for _ in $(seq 1 90); do
    if curl -fsS "$BASE/health" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "error: o Éden não respondeu em /health"
  return 1
}

com_chave() { curl -fsS -H "Authorization: Bearer $KEY" "$@"; }

esperar
echo "ok: /health"

code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/v1/eden/conversations")
[ "$code" = 401 ] || { echo "error: sem chave devia dar 401, deu $code"; exit 1; }
echo "ok: sem chave, recusado (401)"

com_chave "$BASE/v1/models" | grep -q '"eden-auto"' || { echo "error: modos do Éden não aparecem em /v1/models"; exit 1; }
echo "ok: modos do Éden em /v1/models"

agora=$(date +%s%3N)
com_chave -X PUT -H 'Content-Type: application/json' \
  -d "{\"id\":\"c1\",\"title\":\"Teste\",\"model\":\"eden-auto\",\"createdAt\":$agora,\"updatedAt\":$agora,\"messages\":[{\"id\":\"m1\",\"role\":\"user\",\"content\":\"oi\",\"timestamp\":$agora}]}" \
  "$BASE/v1/eden/conversations/c1" >/dev/null
com_chave "$BASE/v1/eden/conversations/c1" | grep -q '"m1"' || { echo "error: conversa salva não voltou"; exit 1; }
echo "ok: conversa salva e lida"

com_chave "$BASE/v1/eden/gastos" | grep -q '"models"' || { echo "error: /v1/eden/gastos sem modelos"; exit 1; }
echo "ok: gastos do mês"

curl -fsS "$BASE/" | grep -qi '<html' || { echo "error: página do app não abriu"; exit 1; }
echo "ok: página do app"

com_chave "$BASE/v1/eden/espacos" | grep -q '"pessoal"' || { echo "error: espaços não responderam"; exit 1; }
echo "ok: organização pessoal (espaços)"

com_chave "$BASE/v1/eden/push/chave" | grep -q '"chave"' || { echo "error: chave dos avisos não respondeu"; exit 1; }
docker exec eden-teste sh -c 'test "$(stat -c %a /dados/eden/push-vapid.key)" = 600' \
  || { echo "error: chave dos avisos sem a proteção 600"; exit 1; }
echo "ok: avisos no aparelho (chave do servidor protegida)"

docker exec eden-teste sh -c 'test -s /dados/SOUL.md && test -f /dados/USER.md && grep -q "^\[eden" /dados/config.toml' \
  || { echo "error: configuração/personalidade do Éden não estão em /dados"; exit 1; }
echo "ok: configuração e personalidade em /dados"

if docker exec eden-teste sh -c 'touch /app/eden/teste 2>/dev/null'; then
  echo "error: o programa do Éden devia ser só-leitura"; exit 1
fi
docker exec eden-teste sh -c 'touch /tmp/teste && touch /dados/teste && rm /tmp/teste /dados/teste' \
  || { echo "error: /tmp e /dados deviam aceitar gravação"; exit 1; }
echo "ok: programa só-leitura; dados e /tmp graváveis"

docker restart eden-teste >/dev/null
esperar
com_chave "$BASE/v1/eden/conversations/c1" | grep -q '"m1"' || { echo "error: conversa sumiu depois de reiniciar"; exit 1; }
echo "ok: conversa continua depois de reiniciar"

echo "Éden no contêiner: tudo certo"
