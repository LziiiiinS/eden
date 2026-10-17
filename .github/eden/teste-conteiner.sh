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

# Página de privacidade (pedida pelo Google para publicar o app): pública.
curl -fsS "$BASE/privacidade.html" | grep -q 'Política de privacidade' \
  || { echo "error: página de privacidade não abriu"; exit 1; }
echo "ok: página de privacidade (sem chave)"

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

# Documentos: um PDF de verdade, lido no processo separado (com limites)
# dentro do contêiner só-leitura e sem permissões.
python3 - <<'PY' > /tmp/eden-teste.pdf
import io, sys
conteudo = b"BT /F1 12 Tf 72 720 Td (Documento de teste do Eden) Tj ET"
objetos = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream",
]
s = io.BytesIO(); s.write(b"%PDF-1.4\n"); pos = []
for i, o in enumerate(objetos, 1):
    pos.append(s.tell()); s.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
x = s.tell(); s.write(f"xref\n0 {len(objetos)+1}\n0000000000 65535 f \n".encode())
for p in pos: s.write(f"{p:010d} 00000 n \n".encode())
s.write(f"trailer\n<< /Size {len(objetos)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode())
sys.stdout.buffer.write(s.getvalue())
PY
resposta=$(com_chave -X POST -H 'X-Eden-Nome: teste.pdf' -H 'Content-Type: application/pdf' \
  --data-binary @/tmp/eden-teste.pdf "$BASE/v1/eden/documentos?espaco=pessoal")
echo "$resposta" | grep -q 'Documento de teste do Eden' \
  || { echo "error: o PDF não foi lido no contêiner: $resposta"; exit 1; }
echo "ok: documento PDF lido (processo separado, contêiner só-leitura)"

# Pesquisa na internet: sem a chave da Anthropic, recusa sem chamar ninguém.
com_chave "$BASE/v1/eden/pesquisa/status" | grep -q '"disponivel":false' \
  || { echo "error: a pesquisa diz que está disponível sem a chave"; exit 1; }
codigo=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $KEY" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"teste"}]}' "$BASE/v1/eden/pesquisa")
[ "$codigo" = "409" ] || { echo "error: pesquisa sem chave devolveu $codigo"; exit 1; }
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"teste"}]}' "$BASE/v1/eden/pesquisa")
[ "$codigo" = "401" ] || { echo "error: pesquisa sem a chave de acesso devolveu $codigo"; exit 1; }
echo "ok: pesquisa na internet protegida e desligada sem a chave da Anthropic"

# Notion: sem a NOTION_API_KEY, fica desligado e não chama ninguém.
com_chave "$BASE/v1/eden/notion/status" | grep -q '"configurado":false' \
  || { echo "error: o Notion diz que está configurado sem a chave"; exit 1; }
codigo=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $KEY" \
  "$BASE/v1/eden/notion/buscar?q=teste")
[ "$codigo" = "409" ] || { echo "error: Notion sem chave devolveu $codigo"; exit 1; }
echo "ok: Notion desligado sem a chave"

# Voz: protegida pela chave de acesso; o status responde (sem chamar a OpenAI).
com_chave "$BASE/v1/eden/voz/status" | grep -q '"modelo":"gpt-4o-mini-tts"' \
  || { echo "error: status da voz não respondeu"; exit 1; }
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"texto":"oi"}' "$BASE/v1/eden/voz")
[ "$codigo" = "401" ] || { echo "error: voz sem a chave de acesso devolveu $codigo"; exit 1; }
echo "ok: voz protegida pela chave de acesso"

docker restart eden-teste >/dev/null
esperar
com_chave "$BASE/v1/eden/conversations/c1" | grep -q '"m1"' || { echo "error: conversa sumiu depois de reiniciar"; exit 1; }
echo "ok: conversa continua depois de reiniciar"

echo "Éden no contêiner: tudo certo"
