#!/bin/sh
# Éden: prepara a pasta de dados e liga o servidor (roda dentro do contêiner).
#
# - config.toml e SOUL.md vêm sempre da versão do Éden que está na imagem
#   (para cada atualização valer sem mexer na pasta de dados).
# - USER.md e MEMORY.md são do usuário: criados vazios na primeira vez e
#   nunca sobrescritos.
# - Conversas e gastos ficam em /dados/eden/ (volume do Docker).
set -eu

DADOS="${OPENJARVIS_HOME:-/dados}"
mkdir -p "$DADOS"

cp /app/eden/config.toml "$DADOS/config.toml"
cp /app/eden/SOUL.md "$DADOS/SOUL.md"
[ -f "$DADOS/USER.md" ] || : > "$DADOS/USER.md"
[ -f "$DADOS/MEMORY.md" ] || : > "$DADOS/MEMORY.md"

if [ -z "${OPENJARVIS_API_KEY:-}" ]; then
  echo "Éden: falta OPENJARVIS_API_KEY no arquivo .env. Rode o iniciar-eden de novo." >&2
  exit 1
fi
if [ -z "${OPENAI_API_KEY:-}" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "Éden: falta a chave de pelo menos uma IA (OPENAI_API_KEY ou ANTHROPIC_API_KEY) no arquivo .env." >&2
  exit 1
fi

exec jarvis serve --host 0.0.0.0 --port 8000
