# Éden: volta os dados do Éden para um backup.
#
# 1. Mostra os backups da pasta "backups" (o mais novo primeiro) e pergunta
#    qual usar.
# 2. Confere o arquivo inteiro antes de mexer em qualquer coisa.
# 3. Para o Éden, guarda o estado atual num backup "antes-de-restaurar"
#    (para dar para desfazer), troca os dados e liga o Éden de novo.
#
# Para usar um backup de outro computador, copie o arquivo para a pasta
# "backups" (o nome precisa começar com eden-backup-).

$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot

function Falar([string]$texto) { Write-Host $texto }

function Eden-Responde {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

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
$lista = @()
if (Test-Path $pasta) {
    $lista = @(Get-ChildItem -Path $pasta -Filter 'eden-backup-*.tar.gz' -File |
        Sort-Object LastWriteTime -Descending | Select-Object -First 20)
}
if ($lista.Count -eq 0) {
    Falar 'Não achei nenhum backup na pasta "backups".'
    Falar 'Para fazer um, use o backup-eden. Para usar um de outro computador, copie o arquivo para essa pasta.'
    exit 1
}

Falar 'Backups encontrados (o mais novo primeiro):'
for ($i = 0; $i -lt $lista.Count; $i++) {
    $f = $lista[$i]
    $mb = '{0:N1} MB' -f ($f.Length / 1MB)
    Falar ("  [{0}] {1}  ({2})  {3}" -f ($i + 1), $f.LastWriteTime.ToString('dd/MM/yyyy HH:mm'), $mb, $f.Name)
}
Falar ''
$resposta = Read-Host 'Número do backup (Enter = 1, o mais novo)'
if ([string]::IsNullOrWhiteSpace($resposta)) { $resposta = '1' }
$numero = 0
if (-not [int]::TryParse($resposta.Trim(), [ref]$numero) -or $numero -lt 1 -or $numero -gt $lista.Count) {
    Falar 'Número inválido. Nada foi mudado.'
    exit 1
}
$escolhido = $lista[$numero - 1]

Falar ''
Falar "Conferindo $($escolhido.Name)…"
docker compose run --rm backup conferir "/backups/$($escolhido.Name)"
if ($LASTEXITCODE -ne 0) {
    Falar ''
    Falar 'Esse backup está danificado ou não é do Éden. Nada foi mudado.'
    exit 1
}

Falar ''
Falar 'Isso troca as conversas, as tarefas e o perfil ATUAIS pelos desse backup.'
Falar 'Contas desligadas continuam desligadas, os celulares ligam os avisos de novo sozinhos e o gasto do mes nao diminui.'
Falar 'O estado atual fica guardado num backup "antes-de-restaurar" (dá para voltar).'
$ok = Read-Host 'Digite SIM para continuar'
if ($ok.Trim() -ne 'SIM') {
    Falar 'Cancelado. Nada foi mudado.'
    exit 0
}

Falar 'Parando o Éden…'
docker compose stop eden
if (Eden-Responde) {
    Falar 'O Éden não parou. Nada foi mudado. Feche o Éden pelo parar-eden e tente de novo.'
    exit 1
}

$hora = Get-Date -Format 'yyyyMMdd-HHmmss'
docker compose run --rm backup restaurar "/backups/$($escolhido.Name)" --hora $hora
$deuCerto = ($LASTEXITCODE -eq 0)

Falar 'Ligando o Éden de novo…'
docker compose up -d
$pronto = $false
for ($i = 0; $i -lt 90; $i++) {
    if (Eden-Responde) { $pronto = $true; break }
    Start-Sleep -Seconds 2
}

Falar ''
if (-not $deuCerto) {
    Falar 'A restauração não foi feita (os dados continuam como estavam). Copie as linhas acima e mande para o Claude.'
    exit 1
}
if ($pronto) {
    Falar 'Pronto! O Éden voltou com os dados do backup.'
    Falar 'Celulares e navegadores que ainda tiverem conversas que não estavam no backup mandam essas conversas'
    Falar 'de volta sozinhos (nada se perde). Se algo parecer estranho, feche e abra o Éden no aparelho.'
} else {
    Falar 'Os dados foram restaurados, mas o Éden ainda não respondeu. Rode o iniciar-eden.'
    exit 1
}
