# Éden: faz uma cópia de segurança (backup) dos dados do Éden.
#
# O que entra: conversas, gastos do mês, perfil (USER.md) e memória
# (MEMORY.md). Não entram chaves: o .env nunca vai para o backup.
#
# O arquivo fica na pasta "backups", ao lado deste script, com a data e a
# hora no nome. Pode rodar com o Éden ligado.
#
# O backup tem as suas conversas: trate como documento pessoal. Para não
# perder tudo se o computador estragar, guarde uma cópia fora dele
# (pendrive, HD externo).

$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

function Falar([string]$texto) { Write-Host $texto }

$null = docker info 2>$null
if ($LASTEXITCODE -ne 0) {
    Falar 'O Docker Desktop não está aberto (ou ainda está ligando).'
    Falar 'Abra o Docker Desktop, espere aparecer "Engine running" e rode de novo.'
    exit 1
}

$null = docker image inspect eden:local 2>$null
if ($LASTEXITCODE -ne 0) {
    Falar 'O Éden ainda não foi montado neste computador. Rode o iniciar-eden primeiro.'
    exit 1
}

$pasta = Join-Path $PSScriptRoot 'backups'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null

$hora = Get-Date -Format 'yyyyMMdd-HHmmss'
Falar 'Fazendo o backup do Éden…'
docker compose run --rm backup criar /backups --tipo manual --hora $hora
if ($LASTEXITCODE -ne 0) {
    Falar ''
    Falar 'Não consegui fazer o backup. Copie as linhas acima e mande para o Claude.'
    exit 1
}

Falar ''
Falar "Pronto! O backup está na pasta: $pasta"
Falar 'Dica: copie esse arquivo para um pendrive ou HD externo de vez em quando.'
Falar 'Ele tem as suas conversas: não mande para ninguém.'
