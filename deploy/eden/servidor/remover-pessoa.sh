#!/usr/bin/env bash
# Éden (servidor): desliga e tira o Éden de outra pessoa (criado pelo
# nova-pessoa.sh), sem apagar os dados dela.
#
#   sudo /opt/eden/remover-pessoa.sh NOME
#
# O que faz:
#   1. faz um último backup (fica em /opt/eden-NOME.desligado-DATA/backups);
#   2. para e tira o contêiner dela (os dados ficam no volume do Docker);
#   3. tira o backup diário dela e o endereço dela no Tailscale;
#   4. renomeia a pasta para /opt/eden-NOME.desligado-DATA (o atualizar-eden
#      não liga mais).
# Para ligar de novo: renomeie a pasta de volta e rode o nova-pessoa.sh NOME.
# Apagar os dados de vez não é feito aqui (não dá para desfazer): o final
# deste script mostra os dois comandos, para você rodar se tiver certeza.
set -euo pipefail
export LC_ALL=C

EDEN_DIR="${EDEN_DIR:-/opt/eden}"
TESTE="${EDEN_MODO_TESTE:-0}"

falhar() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || falhar "rode como root: sudo $0 NOME"
NOME="${1:-}"
[[ "$NOME" =~ ^[a-z][a-z0-9]{1,15}$ ]] || falhar "nome inválido"
DIR="$EDEN_DIR-$NOME"
PROJETO="$(basename "$EDEN_DIR")-$NOME"
[ -f "$DIR/docker-compose.yml" ] || falhar "não achei o Éden de \"$NOME\" em $DIR"
grep -qx "name: $PROJETO" "$DIR/docker-compose.yml" \
  || falhar "o docker-compose.yml de $DIR não é de \"$NOME\"; nada foi mudado"
PORTA="$(sed -n 's/.*"127\.0\.0\.1:\(800[1-5]\):8000".*/\1/p' "$DIR/docker-compose.yml" | head -1 || true)"
[ -n "$PORTA" ] || falhar "não achei a porta do Éden de \"$NOME\"; nada foi mudado"
PORTA_HTTPS="$((8442 + ${PORTA#800}))"

if [ "$TESTE" != 1 ] && [ -t 0 ]; then
  read -r -p "Desligar o Éden de \"$NOME\"? Os dados ficam guardados. Digite SIM: " ok
  [ "$ok" = SIM ] || [ "$ok" = sim ] || { echo "Cancelado. Nada foi mudado."; exit 0; }
fi

echo "Último backup do Éden de \"$NOME\"…"
EDEN_DIR="$DIR" "$DIR/backup-eden.sh" --tipo auto \
  || falhar "o backup não deu certo; nada mais foi mudado"

echo "Desligando…"
(cd "$DIR" && docker compose -p "$PROJETO" down)
systemctl disable --now "eden-backup-$NOME.timer" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/eden-backup-$NOME.service" "/etc/systemd/system/eden-backup-$NOME.timer"
systemctl daemon-reload
if [ "$TESTE" != 1 ]; then
  tailscale serve --https="$PORTA_HTTPS" off >/dev/null 2>&1 \
    || echo "Aviso: confira o endereço :$PORTA_HTTPS com: sudo tailscale serve status"
fi
destino="$DIR.desligado-$(date +%Y%m%d-%H%M%S)"
mv "$DIR" "$destino"

echo
echo "Pronto: o Éden de \"$NOME\" está desligado. Pasta (com o .env e os backups dela):"
echo "  $destino"
echo "Tire também o acesso do celular dela no painel do Tailscale."
echo
echo "Para APAGAR os dados dela de vez (não dá para desfazer), só se tiver certeza:"
echo "  sudo docker volume rm ${PROJETO}_eden-dados"
echo "  sudo rm -rf $destino"
