#!/usr/bin/env bash
# Éden: roda um comando e, se ele falhar, repete o final da saída como
# anotações do GitHub (aparecem na página do PR e podem ser lidas pela API).
# Uso: bash .github/eden/anotar.sh "Nome do passo" comando args...
set -uo pipefail
label="$1"
shift
out="$(mktemp)"
"$@" 2>&1 | tee "$out"
status=${PIPESTATUS[0]}
if [ "$status" -ne 0 ]; then
  key="$out.key"
  grep -E "error|Error|ERROR|FAILED|failed|Traceback|assert|^E  |npm ERR|ERESOLVE|EBADENGINE" "$out" | tail -n 150 > "$key" || true
  [ -s "$key" ] || tail -n 150 "$out" > "$key"
  split -l 15 "$key" "$out.part."
  n=0
  for part in "$out".part.*; do
    n=$((n + 1))
    [ "$n" -gt 10 ] && break
    msg="$(sed -e 's/%/%25/g' -e 's/\r//g' "$part" | awk '{printf "%s%%0A", $0}')"
    echo "::error title=${label} (${n})::${msg}"
  done
fi
exit "$status"
