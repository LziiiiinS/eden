#!/usr/bin/env bash
# Éden: prepara um servidor Ubuntu 24.04 novo (ex.: Hetzner CX23) e liga o Éden.
#
# Uso, no servidor, como root (o LEIA-ME.md explica passo a passo):
#   curl -fsSL https://raw.githubusercontent.com/LziiiiinS/eden/main/deploy/eden/servidor/instalar.sh -o instalar.sh
#   bash instalar.sh
#
# O que ele faz:
#   1. atualiza o sistema e liga as atualizações automáticas de segurança;
#   2. acerta o fuso (São Paulo) e cria 2 GB de memória extra (swap);
#   3. instala o Docker (do site oficial) com limite de tamanho dos registros;
#   4. instala o Tailscale e conecta o servidor à sua rede privada;
#   5. firewall: só SSH e a rede privada entram; SSH só com chave;
#   6. copia os arquivos do Éden para /opt/eden e cria a chave de acesso;
#   7. agenda o backup diário (03:30, ficam 14 dias);
#   8. monta e liga o Éden (na primeira vez demora bastante);
#   9. publica o Éden só na rede privada, com HTTPS (tailscale serve).
#
# Pode rodar de novo quantas vezes quiser: não apaga dados nem troca chaves.
# Nunca mostra as chaves das IAs.
set -euo pipefail

EDEN_DIR="${EDEN_DIR:-/opt/eden}"
REPO="${EDEN_REPO:-LziiiiinS/eden}"
RAMO="${EDEN_RAMO:-main}"
# Pasta local com o conteúdo de deploy/eden (usada nos testes); vazio = baixa
# do GitHub.
ORIGEM="${EDEN_ORIGEM:-}"
# Testes automáticos: não mexe em SSH, swap, firewall ativo nem login do
# Tailscale, e usa a imagem já montada.
TESTE="${EDEN_MODO_TESTE:-0}"
NOME="${EDEN_NOME:-eden-servidor}"
UID_EDEN=10001

passo() { printf '\n== %s ==\n' "$*"; }
falhar() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || falhar "rode como root: sudo bash instalar.sh"
# shellcheck disable=SC1091
. /etc/os-release
[ "${ID:-}" = ubuntu ] || falhar "este script é para Ubuntu (achei: ${ID:-?})"
[ "${VERSION_ID:-}" = "24.04" ] || echo "Aviso: feito e testado para o Ubuntu 24.04 (achei ${VERSION_ID:-?})."
export DEBIAN_FRONTEND=noninteractive

passo "1/9 Atualizando o sistema"
apt-get update -q
if [ "$TESTE" != 1 ]; then apt-get -y -q upgrade; fi
apt-get install -y -q ca-certificates curl git ufw unattended-upgrades openssl python3

passo "2/9 Fuso horário, atualizações de segurança e memória extra"
timedatectl set-timezone America/Sao_Paulo || echo "Aviso: não consegui acertar o fuso."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
# Se uma atualização de segurança pedir reinício, reinicia de madrugada.
# O Éden volta sozinho (restart: unless-stopped).
cat > /etc/apt/apt.conf.d/52eden-reinicio <<'CONF'
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:45";
CONF
if [ "$TESTE" != 1 ] && ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

passo "3/9 Docker"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
if [ ! -f /etc/docker/daemon.json ]; then
  # Registros dos contêineres com limite de tamanho (não enchem o disco).
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
CONF
  systemctl restart docker
fi
systemctl enable --now docker >/dev/null
docker compose version >/dev/null 2>&1 || falhar "o Docker Compose não foi instalado"

passo "4/9 Tailscale (rede privada)"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.noarmor.gpg" \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${VERSION_CODENAME}.tailscale-keyring.list" \
    -o /etc/apt/sources.list.d/tailscale.list
  apt-get update -q
  apt-get install -y -q tailscale
fi
systemctl enable --now tailscaled >/dev/null
if [ "$TESTE" != 1 ] && ! tailscale status >/dev/null 2>&1; then
  echo
  echo "Vai aparecer um link. Abra no navegador, entre na sua conta do Tailscale"
  echo "(a mesma do notebook e dos celulares) e autorize este servidor."
  tailscale up --ssh --hostname "$NOME"
fi

passo "5/9 Firewall e SSH"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow in on tailscale0 >/dev/null
if [ ! -f "$EDEN_DIR/.ssh-publico-fechado" ]; then
  ufw allow 22/tcp >/dev/null
fi
if [ "$TESTE" != 1 ]; then
  ufw --force enable >/dev/null
  if [ -s /root/.ssh/authorized_keys ]; then
    cat > /etc/ssh/sshd_config.d/10-eden.conf <<'CONF'
# Éden: entrar no servidor só com chave (nunca com senha).
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
    if sshd -t; then
      systemctl reload ssh || true
    else
      rm -f /etc/ssh/sshd_config.d/10-eden.conf
      echo "Aviso: não mudei o SSH (a configuração não passou na conferência)."
    fi
  else
    echo "Aviso: não achei chave SSH do root; deixei o SSH como estava."
  fi
fi
echo "Entrada liberada: rede privada (Tailscale)$([ -f "$EDEN_DIR/.ssh-publico-fechado" ] || echo ' e SSH (porta 22)')."
echo "O Éden em si só escuta dentro do servidor (127.0.0.1:8000)."

passo "6/9 Arquivos do Éden em $EDEN_DIR"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if [ -n "$ORIGEM" ]; then
  cp -r "$ORIGEM"/. "$tmp"/
else
  curl -fsSL "https://codeload.github.com/$REPO/tar.gz/refs/heads/$RAMO" \
    | tar xz -C "$tmp" --strip-components=3 --wildcards '*/deploy/eden/*'
fi
for f in docker-compose.yml .env.exemplo servidor/backup-eden.sh servidor/restaurar-eden.sh \
  servidor/atualizar-eden.sh servidor/fechar-ssh-publico.sh servidor/LEIA-ME.md; do
  [ -f "$tmp/$f" ] || falhar "faltou o arquivo $f no pacote do Éden"
done
install -d -m 755 "$EDEN_DIR"
install -m 644 "$tmp/docker-compose.yml" "$tmp/.env.exemplo" "$EDEN_DIR/"
install -m 755 "$tmp/servidor/backup-eden.sh" "$tmp/servidor/restaurar-eden.sh" \
  "$tmp/servidor/atualizar-eden.sh" "$tmp/servidor/fechar-ssh-publico.sh" "$EDEN_DIR/"
install -m 644 "$tmp/servidor/LEIA-ME.md" "$EDEN_DIR/LEIA-ME.md"
# Backups: só o usuário do contêiner (10001) e o root leem.
install -d -m 700 -o "$UID_EDEN" -g "$UID_EDEN" "$EDEN_DIR/backups"

if [ ! -f "$EDEN_DIR/.env" ]; then
  install -m 600 "$EDEN_DIR/.env.exemplo" "$EDEN_DIR/.env"
  echo "Criei $EDEN_DIR/.env (só o root lê)."
fi
chown root:root "$EDEN_DIR/.env"
chmod 600 "$EDEN_DIR/.env"
if ! grep -qE '^OPENJARVIS_API_KEY=[^[:space:]]+' "$EDEN_DIR/.env"; then
  chave="oj_sk_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
  if grep -q '^OPENJARVIS_API_KEY=' "$EDEN_DIR/.env"; then
    sed -i "s|^OPENJARVIS_API_KEY=.*|OPENJARVIS_API_KEY=$chave|" "$EDEN_DIR/.env"
  else
    printf 'OPENJARVIS_API_KEY=%s\n' "$chave" >> "$EDEN_DIR/.env"
  fi
  unset chave
  echo "Criei a chave de acesso do Éden (fica só no .env)."
fi

passo "7/9 Backup diário"
for unidade in "$tmp"/servidor/eden-*.service "$tmp"/servidor/eden-*.timer; do
  sed "s|/opt/eden|$EDEN_DIR|g" "$unidade" > "/etc/systemd/system/$(basename "$unidade")"
  chmod 644 "/etc/systemd/system/$(basename "$unidade")"
done
systemctl daemon-reload
systemctl enable --now eden-backup.timer >/dev/null
echo "Backup todo dia às 03:30 em $EDEN_DIR/backups (ficam os 14 mais novos)."
echo "Atualização automática do Éden: desligada (atualize com: sudo $EDEN_DIR/atualizar-eden.sh)."

if ! grep -qE '^(OPENAI|ANTHROPIC)_API_KEY=[^[:space:]]+' "$EDEN_DIR/.env"; then
  echo
  echo "Falta a chave de pelo menos uma IA."
  echo "  1. Abra o arquivo:   nano $EDEN_DIR/.env"
  echo "  2. Cole a chave depois de OPENAI_API_KEY= (e/ou ANTHROPIC_API_KEY=), sem espaços."
  echo "  3. Salve: Ctrl+O, Enter, Ctrl+X."
  echo "  4. Rode de novo:     bash instalar.sh"
  exit 3
fi

passo "8/9 Montando e ligando o Éden"
cd "$EDEN_DIR"
if [ "$TESTE" = 1 ]; then
  docker compose up -d --no-build
else
  echo "Na primeira vez demora bastante (pode passar de 20 minutos). Pode deixar rodando."
  docker compose up -d --build
fi
pronto=0
for _ in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then pronto=1; break; fi
  sleep 2
done
if [ "$pronto" != 1 ]; then
  echo "O Éden não respondeu. Últimas linhas do registro (sem chaves):"
  docker compose logs --tail 40 eden || true
  exit 1
fi
echo "Éden ligado."

passo "9/9 Endereço na rede privada (HTTPS)"
if [ "$TESTE" = 1 ]; then
  echo "(modo de teste: sem tailscale serve)"
else
  tailscale serve --bg 8000 >/dev/null
  endereco="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
  echo "Pronto! Nos aparelhos com Tailscale, abra: https://$endereco"
fi
echo
echo "Para ver a chave de acesso (não tire print):"
echo "  sudo grep '^OPENJARVIS_API_KEY=' $EDEN_DIR/.env | cut -d= -f2"
echo "Depois que o Tailscale funcionar, feche o SSH público: sudo $EDEN_DIR/fechar-ssh-publico.sh"
