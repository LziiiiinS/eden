#!/usr/bin/env bash
# Éden: testa backup e restauração do jeito do notebook — o docker-compose da
# pasta deploy/eden, com o serviço "backup" — usando chaves de teste (nenhuma
# IA é chamada).
#
# Confere: o backup traz conversas e perfil de volta; o estado de antes da
# restauração fica guardado e também volta; um backup adulterado é recusado
# sem mexer em nada; o contêiner de backup não recebe as chaves do .env e
# fica sem rede.
set -euo pipefail

IMAGEM="${1:-eden:teste}"
KEY="oj_sk_teste_$(date +%s)"
BASE="http://127.0.0.1:8000"

docker tag "$IMAGEM" eden:local
cd deploy/eden
cp .env.exemplo .env
sed -i "s|^OPENJARVIS_API_KEY=.*|OPENJARVIS_API_KEY=$KEY|; s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=sk-teste-falsa|" .env
mkdir -p backups
# No Linux, o contêiner roda com o usuário 10001 (no Windows não importa).
chmod 777 backups

dc() { docker compose "$@"; }

limpar() {
  echo "--- registro do Éden (final) ---"
  dc logs --tail 40 eden 2>&1 || true
  dc down -v >/dev/null 2>&1 || true
  rm -rf backups
  cp .env.exemplo .env
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

salvar() {
  local agora
  agora=$(date +%s%3N)
  com_chave -X PUT -H 'Content-Type: application/json' \
    -d "{\"id\":\"$1\",\"title\":\"Teste $1\",\"model\":\"eden-auto\",\"createdAt\":$agora,\"updatedAt\":$agora,\"messages\":[{\"id\":\"m-$1\",\"role\":\"user\",\"content\":\"oi\",\"timestamp\":$agora}]}" \
    "$BASE/v1/eden/conversations/$1" >/dev/null
}

tem() { com_chave "$BASE/v1/eden/conversations" | grep -q "\"id\":\"$1\""; }

perfil() { dc exec -T eden cat /dados/USER.md; }

restaurar() {
  dc stop eden >/dev/null
  dc run --rm -T backup restaurar "/backups/$1" --hora "$2"
  dc up -d --no-build >/dev/null
  esperar
}

dc up -d --no-build
esperar
echo "ok: Éden ligado pelo docker-compose"

salvar c1
dc exec -T eden sh -c 'echo perfil-antes > /dados/USER.md'

saida=$(dc run --rm -T backup criar /backups --hora 20261015-030000)
echo "$saida"
echo "$saida" | grep -q "Backup criado: eden-backup-manual-20261015-030000.tar.gz" \
  || { echo "error: o backup não foi criado"; exit 1; }
echo "$saida" | grep -q "conversations.db" || { echo "error: backup sem as conversas"; exit 1; }
echo "ok: backup criado com o Éden ligado"

salvar c2
dc exec -T eden sh -c 'echo perfil-depois > /dados/USER.md'

restaurar eden-backup-manual-20261015-030000.tar.gz 20261015-040000
tem c1 || { echo "error: conversa c1 não voltou"; exit 1; }
if tem c2; then echo "error: c2 (feita depois do backup) devia ter saído"; exit 1; fi
[ "$(perfil)" = "perfil-antes" ] || { echo "error: perfil não voltou"; exit 1; }
echo "ok: restauração trouxe conversas e perfil do backup"

restaurar eden-backup-antes-de-restaurar-20261015-040000.tar.gz 20261015-050000
tem c1 && tem c2 || { echo "error: o estado de antes da restauração não voltou"; exit 1; }
[ "$(perfil)" = "perfil-depois" ] || { echo "error: perfil de antes da restauração não voltou"; exit 1; }
echo "ok: o backup 'antes-de-restaurar' desfaz a restauração"

# Backup adulterado (caminho para fora da pasta de dados): recusado, nada muda.
python3 - backups/eden-backup-manual-20261015-060000.tar.gz <<'PY'
import hashlib, io, json, sys, tarfile
conteudo = b"invadido"
nome = "dados/../../etc/eden-invadido"
manifesto = {"formato": 1, "app": "eden", "arquivos": [
    {"caminho": nome, "bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}]}
with tarfile.open(sys.argv[1], "w:gz") as tar:
    for n, dados in (("manifesto.json", json.dumps(manifesto).encode()), (nome, conteudo)):
        info = tarfile.TarInfo(n)
        info.size = len(dados)
        tar.addfile(info, io.BytesIO(dados))
PY
dc stop eden >/dev/null
if dc run --rm -T backup restaurar /backups/eden-backup-manual-20261015-060000.tar.gz; then
  echo "error: backup adulterado foi aceito"; exit 1
fi
dc up -d --no-build >/dev/null
esperar
tem c1 && tem c2 || { echo "error: dados mudaram depois de um backup recusado"; exit 1; }
echo "ok: backup adulterado recusado sem mexer nos dados"

if dc run --rm -T --entrypoint env backup | grep -q -E "OPENJARVIS_API_KEY|OPENAI_API_KEY"; then
  echo "error: o contêiner de backup recebeu chaves"; exit 1
fi
echo "ok: contêiner de backup sem chaves"

if dc run --rm -T --entrypoint python backup -c \
  "import socket; socket.create_connection(('1.1.1.1', 443), timeout=3)" >/dev/null 2>&1; then
  echo "error: o contêiner de backup tem rede"; exit 1
fi
echo "ok: contêiner de backup sem rede"

echo "Backup e restauração: tudo certo"
