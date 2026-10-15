#!/usr/bin/env bash
# Éden (servidor): fecha a porta 22 para a internet. Depois disso, só dá para
# entrar no servidor pela rede privada (Tailscale) — ou pelo console do site
# da Hetzner, em caso de emergência.
#
#   sudo /opt/eden/fechar-ssh-publico.sh
#
# Para abrir de novo: sudo ufw allow 22/tcp && sudo rm /opt/eden/.ssh-publico-fechado
set -euo pipefail

EDEN_DIR="${EDEN_DIR:-/opt/eden}"

if ! tailscale status >/dev/null 2>&1; then
  echo "O Tailscale não está conectado neste servidor. Não fechei nada."
  exit 1
fi

# A chave do servidor no Tailscale expira? Se expirar com a porta 22 fechada,
# o servidor sai da rede privada e só o console da Hetzner entra.
expira="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("Self", {}).get("KeyExpiry", ""))')"
if [ -n "$expira" ]; then
  echo "Atenção: a chave deste servidor no Tailscale expira em $expira."
  echo "Antes de fechar: no painel do Tailscale (Machines), nos três pontinhos do"
  echo "servidor, escolha \"Disable key expiry\". E guarde a senha do root (sudo passwd root)"
  echo "num gerenciador de senhas: ela serve para o console da Hetzner em emergência."
  read -r -p "Já fez isso? Digite SIM para continuar: " ok_expira
  if [ "$ok_expira" != "SIM" ] && [ "$ok_expira" != "sim" ]; then
    echo "Cancelado. Nada foi mudado."
    exit 0
  fi
fi

# Esta sessão veio pela rede privada? (endereços do Tailscale: 100.64.0.0/10)
conexao="${SSH_CONNECTION:-}"
origem="${conexao%% *}"
pela_rede_privada=0
if [[ "$origem" =~ ^100\.([0-9]+)\. ]] && [ "${BASH_REMATCH[1]}" -ge 64 ] && [ "${BASH_REMATCH[1]}" -le 127 ]; then
  pela_rede_privada=1
fi

if [ "$pela_rede_privada" != 1 ]; then
  echo "Você está conectado pela internet, não pela rede privada."
  echo "Antes de fechar, teste num outro terminal:  ssh root@$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].split(".")[0])')"
  read -r -p "Já conseguiu entrar pela rede privada? Digite SIM para fechar: " ok
  if [ "$ok" != "SIM" ] && [ "$ok" != "sim" ]; then
    echo "Cancelado. Nada foi mudado."
    exit 0
  fi
fi

ufw delete allow 22/tcp >/dev/null || true
touch "$EDEN_DIR/.ssh-publico-fechado"
echo "Pronto: a porta 22 está fechada para a internet. Entre pelo Tailscale: ssh root@<nome-do-servidor>"
