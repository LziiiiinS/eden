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

DIR_ANA="$DIR-ana"
BASE_ANA="http://127.0.0.1:8001"

limpar() {
  echo "--- registro do Éden (final) ---"
  (cd "$DIR" 2>/dev/null && sudo docker compose logs --tail 40 eden) || true
  (cd "$DIR_ANA" 2>/dev/null && sudo docker compose logs --tail 20 eden) || true
  (cd "$DIR_ANA" 2>/dev/null && sudo docker compose down -v >/dev/null 2>&1) || true
  (cd "$DIR" 2>/dev/null && sudo docker compose down -v >/dev/null 2>&1) || true
  sudo systemctl disable --now eden-backup.timer eden-backup-ana.timer >/dev/null 2>&1 || true
  sudo rm -f /etc/systemd/system/eden-*.service /etc/systemd/system/eden-*.timer
  sudo systemctl daemon-reload || true
  sudo rm -rf "$DIR" "$DIR_ANA"
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

# Éden de outra pessoa (nova-pessoa.sh): pasta, chave, dados e backup
# próprios; nenhuma chave de IA copiada do Éden principal.
nova_pessoa() {
  sudo env EDEN_MODO_TESTE=1 EDEN_DIR="$DIR" "$DIR/nova-pessoa.sh" "$@"
}
set +e
nova_pessoa ana
codigo=$?
set -e
[ "$codigo" = 3 ] || { echo "error: sem chave de IA o nova-pessoa devia parar com código 3 (deu $codigo)"; exit 1; }
[ "$(sudo stat -c '%a %U' "$DIR_ANA/.env")" = "600 root" ] || { echo "error: .env da pessoa sem a proteção 600/root"; exit 1; }
if sudo grep -qE '^(OPENAI|ANTHROPIC)_API_KEY=[^[:space:]]+' "$DIR_ANA/.env"; then
  echo "error: o nova-pessoa copiou uma chave de IA do Éden principal"; exit 1
fi
ka="$(sudo grep '^OPENJARVIS_API_KEY=' "$DIR_ANA/.env" | cut -d= -f2)"
[[ "$ka" =~ ^oj_sk_[A-Za-z0-9_-]{40,}$ ]] && [ "$ka" != "$k1" ] \
  || { echo "error: a pessoa não ganhou uma chave de acesso própria"; exit 1; }
sudo grep -qx 'COMPOSE_PROJECT_NAME=eden-teste-ana' "$DIR_ANA/.env" || { echo "error: projeto do Docker da pessoa"; exit 1; }
sudo grep -qx 'EDEN_PORTA=8001' "$DIR_ANA/.env" || { echo "error: porta da pessoa"; exit 1; }
if nova_pessoa 'Ana;rm' >/dev/null 2>&1; then echo "error: nome inválido aceito"; exit 1; fi
echo "ok: pessoa nova preparada (chave própria, sem chave de IA copiada)"

sudo sed -i 's|^OPENAI_API_KEY=.*|OPENAI_API_KEY=sk-teste-falsa-ana|' "$DIR_ANA/.env"
nova_pessoa ana
nova_pessoa ana  # de novo: mesma chave, mesma porta
[ "$(sudo grep '^OPENJARVIS_API_KEY=' "$DIR_ANA/.env" | cut -d= -f2)" = "$ka" ] \
  || { echo "error: rodar de novo trocou a chave da pessoa"; exit 1; }
[ "$(sudo grep -c '^EDEN_PORTA=' "$DIR_ANA/.env")" = 1 ] || { echo "error: porta repetida no .env"; exit 1; }
curl -fsS "$BASE_ANA/health" >/dev/null || { echo "error: Éden da pessoa não respondeu"; exit 1; }
[ "$(systemctl is-enabled eden-backup-ana.timer)" = enabled ] || { echo "error: backup da pessoa não agendado"; exit 1; }
sudo systemd-analyze verify /etc/systemd/system/eden-backup-ana.service /etc/systemd/system/eden-backup-ana.timer

# Separados de verdade: chave de um não abre o outro, dados não se misturam.
codigo=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $k1" "$BASE_ANA/v1/eden/conversations")
[ "$codigo" = 401 ] || { echo "error: a sua chave abriu o Éden da pessoa ($codigo)"; exit 1; }
codigo=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $ka" "$BASE/v1/eden/conversations")
[ "$codigo" = 401 ] || { echo "error: a chave da pessoa abriu o seu Éden ($codigo)"; exit 1; }
if curl -fsS -H "Authorization: Bearer $ka" "$BASE_ANA/v1/eden/conversations" | grep -q '"id":"s1"'; then
  echo "error: a pessoa vê a sua conversa"; exit 1
fi
curl -fsS -H "Authorization: Bearer $ka" -X PUT -H 'Content-Type: application/json' \
  -d "{\"id\":\"a1\",\"title\":\"ConversaDaAna\",\"model\":\"eden-auto\",\"createdAt\":$agora,\"updatedAt\":$agora,\"messages\":[{\"id\":\"ma1\",\"role\":\"user\",\"content\":\"oi\",\"timestamp\":$agora}]}" \
  "$BASE_ANA/v1/eden/conversations/a1" >/dev/null
if curl -fsS -H "Authorization: Bearer $k1" "$BASE/v1/eden/conversations" | grep -q '"id":"a1"'; then
  echo "error: você vê a conversa da pessoa"; exit 1
fi
sudo docker ps --filter label=com.docker.compose.project=eden-teste-ana -q | grep -q . \
  || { echo "error: o contêiner da pessoa não está no projeto dela"; exit 1; }
sudo systemctl start eden-backup-ana.service
backup_ana="$(sudo find "$DIR_ANA/backups" -name 'eden-backup-diario-*.tar.gz' | head -1)"
[ -n "$backup_ana" ] || { echo "error: o backup da pessoa não criou arquivo"; exit 1; }
sudo tar -xzOf "$backup_ana" | grep -ac 'ConversaDaAna' >/dev/null \
  || { echo "error: o backup da pessoa não tem os dados dela"; exit 1; }
if sudo tar -xzOf "$backup_ana" | grep -ac 'Servidor' >/dev/null; then
  echo "error: o backup da pessoa tem dados do Éden principal"; exit 1
fi
[ "$(sudo find "$DIR/backups" -name 'eden-backup-diario-*.tar.gz' | wc -l)" = 1 ] \
  || { echo "error: o backup da pessoa caiu na sua pasta"; exit 1; }
echo "ok: Éden da pessoa separado (chave, conversas e backup próprios)"

sudo env EDEN_DIR="$DIR" EDEN_MODO_TESTE=1 "$DIR/atualizar-eden.sh"
curl -fsS "$BASE_ANA/health" >/dev/null || { echo "error: Éden da pessoa não voltou depois de atualizar"; exit 1; }
curl -fsS -H "Authorization: Bearer $ka" "$BASE_ANA/v1/eden/conversations" | grep -q '"id":"a1"' \
  || { echo "error: a conversa da pessoa sumiu depois de atualizar"; exit 1; }
sudo find "$DIR_ANA/backups" -name 'eden-backup-auto-*.tar.gz' | grep -q . \
  || { echo "error: atualizar não fez o backup da pessoa"; exit 1; }
echo "ok: atualizar liga também o Éden da pessoa, com backup antes"

sudo docker image inspect eden:anterior >/dev/null || { echo "error: atualizar não guardou a versão anterior"; exit 1; }
sudo find "$DIR/backups" -name 'eden-backup-auto-*.tar.gz' | grep -q . || { echo "error: atualizar não fez backup"; exit 1; }
echo "ok: atualizar faz backup, guarda a versão anterior e liga"

sudo rm -f /root/eden-backup-manual-2026101*.tar.gz
echo "Pacote do servidor: tudo certo"
