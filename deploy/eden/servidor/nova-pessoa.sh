#!/usr/bin/env bash
# Éden (servidor): um Éden separado para outra pessoa (ex.: namorada, pai).
#
#   sudo /opt/eden/nova-pessoa.sh NOME          (ex.: sudo /opt/eden/nova-pessoa.sh ana)
#
# Cada pessoa ganha o PRÓPRIO Éden, ao lado do seu:
#   - pasta própria (/opt/eden-NOME), com .env próprio (só o root lê);
#   - chave de acesso própria (a sua não abre o Éden dela, e a dela não abre
#     o seu);
#   - dados próprios (projeto e volume próprios no Docker, com o nome escrito
#     no docker-compose.yml da pasta dela) e backup diário próprio;
#   - as chaves de IA são as DA PESSOA (nunca copiadas do seu .env);
#   - endereço próprio na rede privada: https://SERVIDOR.ts.net:8443 (a 1ª
#     pessoa), :8444 (a 2ª)…
#
# Quem administra o servidor (root) consegue ver tudo de todos: diga isso à
# pessoa antes.
#
# Pode rodar de novo quantas vezes quiser: não apaga dados nem troca a chave.
# Precisa do Éden principal já instalado (instalar.sh). Para tirar uma
# pessoa: remover-pessoa.sh.
set -euo pipefail
export LC_ALL=C

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
COMPOSE="$EDEN_DIR/docker-compose.yml"
[ -f "$COMPOSE" ] && [ -f "$EDEN_DIR/.env.exemplo" ] && [ -f "$EDEN_DIR/.env" ] \
  || falhar "não achei o Éden principal em $EDEN_DIR (rode o instalar.sh antes)"
grep -qx 'name: eden' "$COMPOSE" && grep -q '"127.0.0.1:8000:8000"' "$COMPOSE" \
  || falhar "o docker-compose.yml de $EDEN_DIR não é o esperado (rode o instalar.sh de novo)"
docker image inspect eden:local >/dev/null 2>&1 \
  || falhar "a imagem do Éden ainda não foi montada (rode o instalar.sh antes)"

# Um nova-pessoa por vez (dois ao mesmo tempo pegariam a mesma porta).
exec 9>/run/lock/eden-nova-pessoa.lock
flock -n 9 || falhar "já tem outro nova-pessoa rodando; espere ele terminar"

DIR="$EDEN_DIR-$NOME"
PROJETO="$(basename "$EDEN_DIR")-$NOME"

valor() { grep -E "^$1=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- || true; }
# Chaves iguais às de outro Éden deste servidor (ex.: pasta copiada): recusa.
igual_a_outro() {  # igual_a_outro CHAVE
  local meu outro env
  meu="$(valor "$1" "$DIR/.env")"
  [ -n "$meu" ] || return 1
  for env in "$EDEN_DIR/.env" "$EDEN_DIR"-*/.env; do
    [ -f "$env" ] && [ "$env" != "$DIR/.env" ] || continue
    outro="$(valor "$1" "$env")"
    if [ -n "$outro" ] && [ "$outro" = "$meu" ]; then return 0; fi
  done
  return 1
}
for k in OPENJARVIS_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  if [ -f "$DIR/.env" ] && igual_a_outro "$k"; then
    falhar "o .env de $NOME tem a mesma $k de outro Éden deste servidor. Cada pessoa precisa da própria: apague essa linha em $DIR/.env e rode de novo."
  fi
done

porta_de() {  # porta_de PASTA → 8001…8005 (ou nada)
  sed -n 's/.*"127\.0\.0\.1:\(800[1-5]\):8000".*/\1/p' "$1/docker-compose.yml" 2>/dev/null | head -1 || true
}

# Número da pessoa (1 a 5): o mesmo de antes, ou o primeiro livre.
usados=" "
for d in "$EDEN_DIR"-*/; do
  d="${d%/}"
  [ "$d" != "$DIR" ] || continue
  [[ "$(basename "$d")" =~ ^$(basename "$EDEN_DIR")-[a-z][a-z0-9]{1,15}$ ]] || continue
  p="$(porta_de "$d")"
  if [ -n "$p" ]; then usados+="${p#800} "; fi
done
n=""
p="$(porta_de "$DIR")"
if [ -n "$p" ] && [[ "$usados" != *" ${p#800} "* ]]; then n="${p#800}"; fi
if [ -z "$n" ]; then
  for i in $(seq 1 "$MAX_PESSOAS"); do
    if [[ "$usados" != *" $i "* ]]; then n="$i"; break; fi
  done
  [ -n "$n" ] || falhar "já existem $MAX_PESSOAS Édens extras neste servidor"
fi
PORTA="800$n"
PORTA_HTTPS="$((8442 + n))"

echo "== Éden de \"$NOME\" em $DIR (porta interna $PORTA, endereço :$PORTA_HTTPS) =="

# Cópia do docker-compose.yml com o nome e a porta dela escritos no próprio
# arquivo (não dependem de nenhuma linha do .env).
copiar_compose() {
  install -d -m 755 "$DIR"
  sed -e "s/^name: eden\$/name: $PROJETO/" -e "s/\"127\\.0\\.0\\.1:8000:8000\"/\"127.0.0.1:$PORTA:8000\"/" \
    "$COMPOSE" > "$DIR/docker-compose.yml.novo"
  if ! grep -qx "name: $PROJETO" "$DIR/docker-compose.yml.novo" \
    || ! grep -q "\"127.0.0.1:$PORTA:8000\"" "$DIR/docker-compose.yml.novo"; then
    rm -f "$DIR/docker-compose.yml.novo"
    falhar "não consegui montar o docker-compose.yml de $NOME"
  fi
  chmod 644 "$DIR/docker-compose.yml.novo"
  mv "$DIR/docker-compose.yml.novo" "$DIR/docker-compose.yml"
}
copiar_compose
install -m 644 "$EDEN_DIR/.env.exemplo" "$DIR/"
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

definir() {  # definir CHAVE (o valor vem pela entrada, nunca pela linha de comando)
  python3 -c '
import os, sys
caminho, chave = sys.argv[1], sys.argv[2]
valor = sys.stdin.read().strip()
linhas = open(caminho, encoding="utf-8").read().splitlines()
novas, achou = [], False
for linha in linhas:
    if linha.startswith(chave + "="):
        if not achou:
            novas.append(f"{chave}={valor}")
        achou = True
    else:
        novas.append(linha)
if not achou:
    novas.append(f"{chave}={valor}")
tmp = caminho + ".novo"
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write("\n".join(novas) + "\n")
os.replace(tmp, caminho)
' "$DIR/.env" "$1"
}
# Linhas antigas que já não decidem nada (o nome e a porta estão no compose).
for velha in COMPOSE_PROJECT_NAME EDEN_PORTA; do
  if grep -q "^$velha=" "$DIR/.env"; then
    sed -i "/^$velha=/d" "$DIR/.env"
  fi
done

if ! grep -qE '^OPENJARVIS_API_KEY=[^[:space:]]+' "$DIR/.env"; then
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n' | sed 's/^/oj_sk_/' | definir OPENJARVIS_API_KEY
  echo "Criei a chave de acesso do Éden de \"$NOME\" (fica só no .env dele)."
fi

# Backup diário próprio (alguns minutos depois do principal).
servico="eden-backup-$NOME"
for u in service timer; do
  [ -f "/etc/systemd/system/eden-backup.$u" ] \
    || falhar "não achei o backup diário do Éden principal (rode o instalar.sh antes)"
done
sed "s|$EDEN_DIR/|$DIR/|g; s|EDEN_DIR=$EDEN_DIR\$|EDEN_DIR=$DIR|; s|Éden: backup|Éden ($NOME): backup|" \
  "/etc/systemd/system/eden-backup.service" > "/etc/systemd/system/$servico.service"
grep -q "^Environment=EDEN_DIR=$DIR\$" "/etc/systemd/system/$servico.service" \
  && grep -q "^ExecStart=$DIR/backup-eden.sh " "/etc/systemd/system/$servico.service" \
  || { rm -f "/etc/systemd/system/$servico.service"; falhar "não consegui montar o backup diário de $NOME"; }
sed "s|03:30:00|03:$((40 + n)):00|; s|às 03:30|às 03:$((40 + n))|; s|Éden: backup|Éden ($NOME): backup|" \
  "/etc/systemd/system/eden-backup.timer" > "/etc/systemd/system/$servico.timer"
chmod 644 "/etc/systemd/system/$servico.service" "/etc/systemd/system/$servico.timer"
systemctl daemon-reload
systemctl enable --now "$servico.timer" >/dev/null
echo "Backup todo dia às 03:$((40 + n)) em $DIR/backups."

if ! grep -qE '^(OPENAI|ANTHROPIC)_API_KEY=[^[:space:]]+' "$DIR/.env"; then
  if [ "$TESTE" != 1 ] && [ -t 0 ]; then
    echo
    echo "Falta a chave de IA DA PESSOA (a conta dela, com o limite dela)."
    echo "A pessoa pode colar aqui (não aparece na tela). Enter vazio = deixar para depois."
    read -r -s -p "Chave da OpenAI (sk-…) ou da Anthropic (sk-ant-…): " chave_ia
    echo
    case "$chave_ia" in
      "") ;;
      sk-ant-*) printf '%s' "$chave_ia" | definir ANTHROPIC_API_KEY ;;
      sk-*) printf '%s' "$chave_ia" | definir OPENAI_API_KEY ;;
      *) echo "Isso não parece uma chave de IA; não guardei." ;;
    esac
    unset chave_ia
  fi
  if ! grep -qE '^(OPENAI|ANTHROPIC)_API_KEY=[^[:space:]]+' "$DIR/.env"; then
    echo
    echo "Falta a chave de IA DA PESSOA. Rode de novo quando ela estiver junto:"
    echo "  sudo $0 $NOME"
    echo "(ou cole em $DIR/.env depois de OPENAI_API_KEY= ou ANTHROPIC_API_KEY=)."
    echo "O limite de gastos dela: EDEN_LIMITE_OPENAI / EDEN_LIMITE_ANTHROPIC no mesmo .env."
    exit 3
  fi
  for k in OPENAI_API_KEY ANTHROPIC_API_KEY; do
    if igual_a_outro "$k"; then
      falhar "essa chave de IA já é de outro Éden deste servidor; use a da pessoa"
    fi
  done
fi

cd "$DIR"
docker compose -p "$PROJETO" up -d --no-build
pronto=0
for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1; then pronto=1; break; fi
  sleep 2
done
if [ "$pronto" != 1 ]; then
  echo "O Éden de \"$NOME\" não respondeu. Últimas linhas do registro (sem chaves):"
  docker compose -p "$PROJETO" logs --tail 40 eden || true
  exit 1
fi
echo "Éden de \"$NOME\" ligado."

if [ "$TESTE" = 1 ]; then
  echo "(modo de teste: sem tailscale serve)"
else
  tailscale serve --bg --https="$PORTA_HTTPS" "$PORTA" >/dev/null
  endereco="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip(".").lower())')"
  if [[ "$endereco" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net$ ]]; then
    printf '%s' "https://$endereco:$PORTA_HTTPS" | definir EDEN_ENDERECO_CELULAR
    docker compose -p "$PROJETO" up -d >/dev/null
    echo "Endereço do Éden de \"$NOME\": https://$endereco:$PORTA_HTTPS"
  fi
fi
echo
echo "Para ligar o celular da pessoa: abra o Éden DELA (endereço acima) numa"
echo "janela anônima do notebook, entre com a chave dela, mostre o QR code das"
echo "Configurações na frente do aparelho e feche a janela. A chave dela (não"
echo "tire print, não mande por mensagem):"
echo "  sudo grep '^OPENJARVIS_API_KEY=' $DIR/.env | cut -d= -f2"
echo "O celular dela precisa entrar na sua rede do Tailscale: de preferência"
echo "compartilhando só o servidor (feito na conta do Tailscale)."
echo "Para tirar este Éden: sudo $EDEN_DIR/remover-pessoa.sh $NOME"
