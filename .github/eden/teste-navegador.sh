#!/usr/bin/env bash
# Éden: liga a imagem com chaves de teste e roda o teste no navegador
# (Chromium, pelo Playwright). Sem chamar nenhuma IA de verdade.
# Uso: bash .github/eden/teste-navegador.sh eden:teste
set -euo pipefail

IMAGEM="${1:-eden:local}"
KEY="oj_sk_navegador_$(date +%s)"
BASE="http://127.0.0.1:8000"
AQUI="$(cd "$(dirname "$0")" && pwd)"

docker volume create eden-navegador >/dev/null
docker run -d --name eden-navegador -p 127.0.0.1:8000:8000 \
  --read-only --tmpfs /tmp:rw,size=128m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -e OPENJARVIS_HOME=/dados \
  -e OPENJARVIS_API_KEY="$KEY" \
  -e OPENAI_API_KEY=sk-teste-falsa \
  -v eden-navegador:/dados \
  --entrypoint sh "$IMAGEM" /app/deploy/eden/iniciar-no-conteiner.sh >/dev/null

limpar() {
  echo "--- registro do contêiner (final) ---"
  docker logs --tail 40 eden-navegador 2>&1 || true
  docker rm -f eden-navegador >/dev/null 2>&1 || true
  docker volume rm eden-navegador >/dev/null 2>&1 || true
}
trap limpar EXIT

for _ in $(seq 1 90); do
  if curl -fsS "$BASE/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "$BASE/health" >/dev/null || { echo "error: o Éden não respondeu em /health"; exit 1; }

EDEN_CHAVE="$KEY" EDEN_BASE="$BASE" python "$AQUI/teste_navegador.py"
