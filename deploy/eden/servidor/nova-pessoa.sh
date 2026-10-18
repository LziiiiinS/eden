#!/usr/bin/env bash
# Éden (servidor): um Éden separado para outra pessoa (ex.: namorada, pai).
#
#   sudo /opt/eden/nova-pessoa.sh NOME          (ex.: sudo /opt/eden/nova-pessoa.sh ana)
#
# Cada pessoa ganha o PRÓPRIO Éden, ao lado do seu, sem nada compartilhado:
#   - pasta própria (/opt/eden-NOME), com .env próprio (só o root lê);
#   - chave de acesso própria (a sua não abre o Éden dela, e a dela não abre
#     o seu);
#   - dados próprios (volume próprio do Docker) e backup diário próprio;
#   - as chaves de IA são as DA PESSOA (nunca copiadas do seu .env), com o
#     limite de gastos dela;
#   - endereço próprio na rede privada: https://SERVIDOR.ts.net:8443 (a 1ª
#     pessoa), :8444 (a 2ª)…
#
# Pode rodar de novo quantas vezes quiser: não apaga dados nem troca a chave.
# Precisa do Éden principal já instalado (instalar.sh). Para tirar uma pessoa,
# veja o LEIA-ME ("Outra pessoa").
set -euo pipefail

EDEN_DIR="${EDEN_DIR:-/opt/eden}"
TESTE="${EDEN_MODO_TESTE:-0}"
MAX_PESSOAS=5
UID_EDEN=10001

falhar() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || falhar "rode como root: sudo $0 NOME"
NOME="${1:-}"
[[ "$NOME" =~ ^[a-z][a-z0-9]{1,15}$ ]] \
  || falhar "nome inválido. Use só letras minúsculas e números, começando com letra (ex.: ana, pai)."
case "$NOME" in
  teste|backups|anterior|local) falhar "esse nome é reservado; escolha outro" ;;
esac
[ -f "$EDEN_DIR/docker-compose.yml" ] && [ -f "$EDEN_DIR/.env.exemplo" ] \
  || falhar "não achei o Éden principal em $EDEN_DIR (rode o instalar.sh antes)"
docker image inspect eden:local >/dev/null 2>&1 \
  || falhar "a imagem do Éden ainda não foi montada (rode o instalar.sh antes)"

DIR="$EDEN_DIR-$NOME"
PROJETO="$(basename "$EDEN_DIR")-$NOME"

valor() { grep -E "^$1=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- || true; }

# Número da pessoa (1 a 5): o mesmo de antes, ou o primeiro livre.
n=""
if [ -f "$DIR/.env" ]; then
  porta="$(valor EDEN_PORTA "$DIR/.env")"
  [[ "$porta" =~ ^800[1-9]$ ]] && n="${porta#800}"
fi
if [ -z "$n" ]; then
  usados=" "
  for env in "$EDEN_DIR"-*/.env; do
    [ -f "$env" ] || continue
    p="$(valor EDEN_PORTA "$env")"
    [[ "$p" =~ ^800[1-9]$ ]] && usados+="${p#800} "
  done
  for i in $(seq 1 "$MAX_PESSOAS"); do
    if [[ "$usados" != *" $i "* ]]; then n="$i"; break; fi
  done
  [ -n "$n" ] || falhar "já existem $MAX_PESSOAS Édens extras neste servidor"
fi
PORTA="800$n"
PORTA_HTTPS="$((8442 + n))"

echo "== Éden de \"$NOME\" em $DIR (porta interna $PORTA, endereço :$PORTA_HTTPS) =="

# Arquivos: os mesmos do Éden principal (a imagem também é a mesma).
install -d -m 755 "$DIR"
install -m 644 "$EDEN_DIR/docker-compose.yml" "$EDEN_DIR/.env.exemplo" "$DIR/"
for s in backup-eden.sh restaurar-eden.sh; do
  install -m 755 "$EDEN_DIR/$s" "$DIR/"
done
[ -f "$EDEN_DIR/LEIA-ME.md" ] && install -m 644 "$EDEN_DIR/LEIA-ME.md" "$DIR/"
install -d -m 700 -o "$UID_EDEN" -g "$UID_EDEN" "$DIR/backups"

# .env próprio: NUNCA copia o seu (as chaves de IA são as da pessoa).
if [ ! -f "$DIR/.env" ]; then
  install -m 600 "$DIR/.env.exemplo" "$DIR/.env"
  echo "Criei $DIR/.env (só o root lê)."
fi
chown root:root "$DIR/.env"
chmod 600 "$DIR/.env"

definir() {  # definir CHAVE VALOR (troca ou acrescenta no .env da pessoa)
  if grep -q "^$1=" "$DIR/.env"; then
    sed -i "s|^$1=.*|$1=$2|" "$DIR/.env"
  else
    printf '%s=%s\n' "$1" "$2" >> "$DIR/.env"
  fi
}
if ! grep -qE '^OPENJARVIS_API_KEY=[^[:space:]]+' "$DIR/.env"; then
  chave="oj_sk_$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n')"
  definir OPENJARVIS_API_KEY "$chave"
  unset chave
  echo "Criei a chave de acesso do Éden de \"$NOME\" (fica só no .env dele)."
fi
# Nome do projeto no Docker (contêiner e dados separados) e porta própria.
definir COMPOSE_PROJECT_NAME "$PROJETO"
definir EDEN_PORTA "$PORTA"

# Backup diário próprio (alguns minutos depois do principal).
servico="eden-backup-$NOME"
sed "s|$EDEN_DIR/|$DIR/|g; s|EDEN_DIR=$EDEN_DIR\$|EDEN_DIR=$DIR|; s|Éden: backup|Éden ($NOME): backup|" \
  "/etc/systemd/system/eden-backup.service" > "/etc/systemd/system/$servico.service" 2>/dev/null \
  || falhar "não achei o backup diário do Éden principal (rode o instalar.sh antes)"
sed "s|03:30:00|03:$((40 + n)):00|; s|às 03:30|às 03:$((40 + n))|; s|Éden: backup|Éden ($NOME): backup|" \
  "/etc/systemd/system/eden-backup.timer" > "/etc/systemd/system/$servico.timer"
chmod 644 "/etc/systemd/system/$servico.service" "/etc/systemd/system/$servico.timer"
systemctl daemon-reload
systemctl enable --now "$servico.timer" >/dev/null
echo "Backup todo dia às 03:$((40 + n)) em $DIR/backups."

if ! grep -qE '^(OPENAI|ANTHROPIC)_API_KEY=[^[:space:]]+' "$DIR/.env"; then
  echo
  echo "Falta a chave de IA DA PESSOA (a conta dela, com o limite dela)."
  echo "  1. Abra o arquivo:   nano $DIR/.env"
  echo "  2. Cole a chave dela depois de OPENAI_API_KEY= (e/ou ANTHROPIC_API_KEY=)."
  echo "     Ajuste também EDEN_LIMITE_OPENAI / EDEN_LIMITE_ANTHROPIC, se quiser."
  echo "  3. Salve: Ctrl+O, Enter, Ctrl+X."
  echo "  4. Rode de novo:     sudo $0 $NOME"
  exit 3
fi

cd "$DIR"
docker compose up -d --no-build
pronto=0
for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1; then pronto=1; break; fi
  sleep 2
done
if [ "$pronto" != 1 ]; then
  echo "O Éden de \"$NOME\" não respondeu. Últimas linhas do registro (sem chaves):"
  docker compose logs --tail 40 eden || true
  exit 1
fi
echo "Éden de \"$NOME\" ligado."

if [ "$TESTE" = 1 ]; then
  echo "(modo de teste: sem tailscale serve)"
else
  tailscale serve --bg --https="$PORTA_HTTPS" "$PORTA" >/dev/null
  endereco="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip(".").lower())')"
  if [[ "$endereco" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net$ ]]; then
    definir EDEN_ENDERECO_CELULAR "https://$endereco:$PORTA_HTTPS"
    docker compose up -d >/dev/null
    echo "Endereço do Éden de \"$NOME\": https://$endereco:$PORTA_HTTPS"
  fi
fi
echo
echo "Para ligar o celular da pessoa: abra o Éden DELA (endereço acima) no"
echo "notebook com a chave dela e use o QR code das Configurações, na frente"
echo "do aparelho. A chave dela (não tire print, não mande por mensagem):"
echo "  sudo grep '^OPENJARVIS_API_KEY=' $DIR/.env | cut -d= -f2"
echo "O celular dela precisa estar na sua rede do Tailscale (convite ou"
echo "compartilhar só o servidor): isso é feito na conta do Tailscale."
