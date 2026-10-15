#!/usr/bin/env bash
# Éden: testa o pacote do servidor numa máquina Ubuntu 24.04 do GitHub, em
# modo de teste (sem mexer em SSH, swap, firewall ativo nem login do
# Tailscale; usa a imagem já montada; chaves falsas, nenhuma IA chamada).
#
# Confere: o instalar para pedindo a chave das IAs, cria o .env protegido e a
# chave de acesso; roda de novo sem trocar a chave; liga o Éden; agenda o
# backup diário (e deixa a atualização automática desligada); o backup pelo
# systemd, a restauração (inclusive de um arquivo trazido de fora) e a
# atualização funcionam.
set -euo pipefail

IMAGEM="${1:-eden:teste}"
DIR=/opt/eden-teste
RAIZ="$(pwd)"
BASE="http://127.0.0.1:8000"

docker tag "$IMAGEM" eden:local

instalar() {
  sudo env EDEN_MODO_TESTE=1 EDEN_DIR="$DIR" EDEN_ORIGEM="$RAIZ/deploy/eden" \
    bash "$RAIZ/deploy/eden/servidor/instalar.sh"
}

limpar() {
  echo "--- registro do Éden (final) ---"
  (cd "$DIR" 2>/dev/null && sudo docker compose logs --tail 40 eden) || true
  (cd "$DIR" 2>/dev/null && sudo docker compose down -v >/dev/null 2>&1) || true
  sudo systemctl disable --now eden-backup.timer >/dev/null 2>&1 || true
  sudo rm -f /etc/systemd/system/eden-*.service /etc/systemd/system/eden-*.timer
  sudo systemctl daemon-reload || true
  sudo rm -rf "$DIR"
}
trap limpar EXIT

chave() { sudo grep '^OPENJARVIS_API_KEY=' "$DIR/.env" | cut -d= -f2; }

# 1ª vez: sem chave de IA, o instalar para (código 3) depois de preparar tudo.
set +e
instalar
codigo=$?
set -e
[ "$codigo" = 3 ] || { echo "error: sem chave de IA o instalar devia parar com código 3 (deu $codigo)"; exit 1; }
[ "$(sudo stat -c '%a %U' "$DIR/.env")" = "600 root" ] || { echo "error: .env sem a proteção 600/root"; exit 1; }
[ "$(sudo stat -c '%a %u' "$DIR/backups")" = "700 10001" ] || { echo "error: pasta de backups com dono/permissão errados"; exit 1; }
k1="$(chave)"
[[ "$k1" =~ ^oj_sk_[A-Za-z0-9_-]{40,}$ ]] || { echo "error: chave de acesso não foi criada"; exit 1; }
echo "ok: 1ª vez preparou tudo e pediu a chave das IAs"

sudo sed -i 's|^OPENAI_API_KEY=.*|OPENAI_API_KEY=sk-teste-falsa|' "$DIR/.env"
instalar
[ "$(chave)" = "$k1" ] || { echo "error: rodar de novo trocou a chave de acesso"; exit 1; }
curl -fsS "$BASE/health" >/dev/null || { echo "error: Éden não respondeu"; exit 1; }
echo "ok: 2ª vez ligou o Éden sem trocar a chave"

[ "$(systemctl is-enabled eden-backup.timer)" = enabled ] || { echo "error: backup diário não agendado"; exit 1; }
[ "$(systemctl is-enabled eden-atualizar.timer 2>/dev/null || true)" = disabled ] \
  || { echo "error: atualização automática devia estar desligada"; exit 1; }
sudo systemd-analyze verify /etc/systemd/system/eden-backup.service /etc/systemd/system/eden-backup.timer \
  /etc/systemd/system/eden-atualizar.service /etc/systemd/system/eden-atualizar.timer
echo "ok: backup diário agendado; atualização automática desligada"

# Uma conversa, depois o backup pelo próprio systemd.
agora=$(date +%s%3N)
curl -fsS -H "Authorization: Bearer $k1" -X PUT -H 'Content-Type: application/json' \
  -d "{\"id\":\"s1\",\"title\":\"Servidor\",\"model\":\"eden-auto\",\"createdAt\":$agora,\"updatedAt\":$agora,\"messages\":[{\"id\":\"m1\",\"role\":\"user\",\"content\":\"oi\",\"timestamp\":$agora}]}" \
  "$BASE/v1/eden/conversations/s1" >/dev/null
sudo systemctl start eden-backup.service
diario="$(sudo find "$DIR/backups" -name 'eden-backup-diario-*.tar.gz' -printf '%f\n' | head -1)"
[ -n "$diario" ] || { echo "error: o backup diário não criou arquivo"; sudo journalctl -u eden-backup.service --no-pager | tail -20; exit 1; }
echo "ok: backup diário pelo systemd ($diario)"

# Restaurar um backup "trazido do notebook" (fora da pasta de backups).
sudo cp "$DIR/backups/$diario" /root/eden-backup-manual-20261015-070000.tar.gz
curl -fsS -H "Authorization: Bearer $k1" -X PUT -H 'Content-Type: application/json' \
  -d "{\"id\":\"s2\",\"title\":\"Depois\",\"model\":\"eden-auto\",\"createdAt\":$agora,\"updatedAt\":$agora,\"messages\":[{\"id\":\"m2\",\"role\":\"user\",\"content\":\"oi\",\"timestamp\":$agora}]}" \
  "$BASE/v1/eden/conversations/s2" >/dev/null
sudo env EDEN_DIR="$DIR" "$DIR/restaurar-eden.sh" --sim /root/eden-backup-manual-20261015-070000.tar.gz
lista="$(curl -fsS -H "Authorization: Bearer $k1" "$BASE/v1/eden/conversations")"
echo "$lista" | grep -q '"id":"s1"' || { echo "error: s1 não voltou"; exit 1; }
if echo "$lista" | grep -q '"id":"s2"'; then echo "error: s2 devia ter saído"; exit 1; fi
sudo test -f "$DIR/backups/eden-backup-manual-20261015-070000.tar.gz" || { echo "error: backup de fora não foi copiado"; exit 1; }
sudo find "$DIR/backups" -name 'eden-backup-antes-de-restaurar-*.tar.gz' | grep -q . \
  || { echo "error: faltou o backup antes-de-restaurar"; exit 1; }
echo "ok: restauração de um arquivo trazido de fora"

# Arquivo danificado: recusado, nada muda.
echo "isto nao e backup" | sudo tee /root/eden-backup-manual-20261015-080000.tar.gz >/dev/null
if sudo env EDEN_DIR="$DIR" "$DIR/restaurar-eden.sh" --sim /root/eden-backup-manual-20261015-080000.tar.gz; then
  echo "error: arquivo danificado foi aceito"; exit 1
fi
curl -fsS -H "Authorization: Bearer $k1" "$BASE/v1/eden/conversations" | grep -q '"id":"s1"' \
  || { echo "error: dados mudaram depois de um arquivo recusado"; exit 1; }
echo "ok: arquivo danificado recusado sem mexer nos dados"

sudo env EDEN_DIR="$DIR" EDEN_MODO_TESTE=1 "$DIR/atualizar-eden.sh"
sudo docker image inspect eden:anterior >/dev/null || { echo "error: atualizar não guardou a versão anterior"; exit 1; }
sudo find "$DIR/backups" -name 'eden-backup-auto-*.tar.gz' | grep -q . || { echo "error: atualizar não fez backup"; exit 1; }
echo "ok: atualizar faz backup, guarda a versão anterior e liga"

sudo rm -f /root/eden-backup-manual-2026101*.tar.gz
echo "Pacote do servidor: tudo certo"
