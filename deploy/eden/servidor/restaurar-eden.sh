#!/usr/bin/env bash
# Éden (servidor): volta os dados para um backup.
#
#   sudo /opt/eden/restaurar-eden.sh                  mostra os backups e pergunta
#   sudo /opt/eden/restaurar-eden.sh ARQUIVO.tar.gz   usa esse arquivo (pode ser um
#                                                     backup trazido do notebook)
#
# Confere o arquivo inteiro antes; para o Éden; guarda o estado atual num
# backup "antes-de-restaurar" (para dar para desfazer); troca os dados e liga
# de novo. Um arquivo danificado ou que não seja do Éden é recusado sem mexer
# em nada.
set -euo pipefail

# Pasta deste Éden: a do próprio script (o Éden de outra pessoa tem a cópia
# dele em /opt/eden-NOME), a não ser que EDEN_DIR diga outra.
EDEN_DIR="${EDEN_DIR:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")}"
# Nome do projeto no Docker e porta: os do docker-compose.yml desta pasta. O
# nome vai sempre com -p, então nenhuma linha do .env consegue trocar de Éden.
PROJETO="$(sed -n 's/^name: *\([a-z0-9][a-z0-9_-]*\) *$/\1/p' "$EDEN_DIR/docker-compose.yml" 2>/dev/null | head -1 || true)"
[ -n "$PROJETO" ] || { echo "ERRO: não achei o nome do Éden em $EDEN_DIR/docker-compose.yml" >&2; exit 1; }
PORTA="$(sed -n 's/.*"127\.0\.0\.1:\([0-9]\{4\}\):8000".*/\1/p' "$EDEN_DIR/docker-compose.yml" | head -1 || true)"
PORTA="${PORTA:-8000}"
dc() { docker compose -p "$PROJETO" "$@"; }
sim=0
arquivo=""
for a in "$@"; do
  case "$a" in
    --sim) sim=1 ;;  # não pergunta (testes automáticos)
    -*) echo "uso: restaurar-eden.sh [ARQUIVO.tar.gz]" >&2; exit 2 ;;
    *) arquivo="$a" ;;
  esac
done

# Caminho completo do arquivo informado, antes de mudar de pasta.
if [ -n "$arquivo" ]; then
  [ -f "$arquivo" ] || { echo "Arquivo não encontrado: $arquivo"; exit 1; }
  arquivo="$(realpath "$arquivo")"
fi

cd "$EDEN_DIR"
[ -d backups ] || install -d -m 700 -o 10001 -g 10001 backups

echo "Éden \"$PROJETO\" ($EDEN_DIR)."
responde() { curl -fsS "http://127.0.0.1:$PORTA/health" >/dev/null 2>&1; }

if [ -z "$arquivo" ]; then
  mapfile -t lista < <(find backups -maxdepth 1 -type f -name 'eden-backup-*.tar.gz' -printf '%T@ %f\n' \
    | sort -rn | head -20 | cut -d' ' -f2-)
  if [ "${#lista[@]}" -eq 0 ]; then
    echo "Não achei nenhum backup em $EDEN_DIR/backups."
    exit 1
  fi
  echo "Backups (o mais novo primeiro):"
  for i in "${!lista[@]}"; do
    f="backups/${lista[$i]}"
    printf '  [%d] %s  (%s)  %s\n' "$((i + 1))" "$(date -r "$f" '+%d/%m/%Y %H:%M')" \
      "$(du -h "$f" | cut -f1)" "${lista[$i]}"
  done
  read -r -p "Número do backup (Enter = 1, o mais novo): " n
  n="${n:-1}"
  if ! [[ "$n" =~ ^[0-9]+$ ]] || [ "$n" -lt 1 ] || [ "$n" -gt "${#lista[@]}" ]; then
    echo "Número inválido. Nada foi mudado."
    exit 1
  fi
  nome="${lista[$((n - 1))]}"
else
  nome="$(basename "$arquivo")"
  [[ "$nome" =~ ^[A-Za-z0-9._-]+\.tar\.gz$ ]] || { echo "Nome de arquivo estranho: $nome"; exit 1; }
  # Backup da pasta de OUTRO Éden deste servidor (ex.: o da namorada no seu):
  # recusado, para os dados de uma pessoa não irem parar no Éden da outra.
  case "$arquivo" in
    "$(realpath -m "$EDEN_DIR")"/backups/*) ;;
    */eden/backups/*|*/eden-*/backups/*)
      echo "Esse backup é de outro Éden deste servidor. Nada foi mudado."
      exit 1 ;;
  esac
  if [ "$arquivo" != "$(realpath -m "backups/$nome")" ]; then
    # Backup trazido de fora (ex.: do notebook): copia para a pasta de backups.
    if [ -e "backups/$nome" ]; then
      cmp -s "$arquivo" "backups/$nome" \
        || { echo "Já existe outro backup com esse nome em backups/. Renomeie o arquivo. Nada foi mudado."; exit 1; }
    else
      install -m 600 -o 10001 -g 10001 "$arquivo" "backups/$nome"
      copiado=1
    fi
  fi
fi

echo "Conferindo $nome…"
if ! dc run --rm -T backup conferir "/backups/$nome"; then
  [ "${copiado:-0}" != 1 ] || rm -f "backups/$nome"
  echo "Esse backup está danificado ou não é do Éden. Nada foi mudado."
  exit 1
fi

if [ "$sim" != 1 ]; then
  echo
  echo "Isso troca as conversas, os gastos e o perfil ATUAIS pelos desse backup."
  echo "O estado atual fica guardado num backup \"antes-de-restaurar\" (dá para voltar)."
  read -r -p "Digite SIM para continuar: " ok
  if [ "$ok" != "SIM" ] && [ "$ok" != "sim" ]; then
    echo "Cancelado. Nada foi mudado."
    exit 0
  fi
fi

echo "Parando o Éden…"
dc stop eden >/dev/null
if responde; then
  echo "O Éden não parou. Nada foi mudado."
  exit 1
fi

deu_certo=1
dc run --rm -T backup restaurar "/backups/$nome" --hora "$(date +%Y%m%d-%H%M%S)" || deu_certo=0

echo "Ligando o Éden de novo…"
dc up -d --no-build >/dev/null
pronto=0
for _ in $(seq 1 90); do
  if responde; then pronto=1; break; fi
  sleep 2
done

if [ "$deu_certo" != 1 ]; then
  echo "A restauração não foi feita (os dados continuam como estavam)."
  exit 1
fi
if [ "$pronto" = 1 ]; then
  echo "Pronto! O Éden voltou com os dados do backup."
else
  echo "Os dados foram restaurados, mas o Éden ainda não respondeu. Veja: cd $EDEN_DIR && sudo docker compose logs --tail 40 eden"
  exit 1
fi
