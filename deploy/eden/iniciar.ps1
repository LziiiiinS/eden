# Éden: liga o Éden neste computador (Windows + Docker Desktop).
#
# O que este script faz:
#   1. confere se o Docker Desktop está aberto;
#   2. cria o arquivo .env (se ainda não existir) e a chave de acesso do Éden;
#   3. confere se há chave de pelo menos uma IA (sem mostrar nenhuma chave);
#   4. monta a versão mais nova do Éden (do GitHub) e liga;
#   5. espera o Éden responder e abre no navegador.
#
# Ele nunca mostra chaves na tela. Para ver a chave de acesso, abra o .env
# no Bloco de Notas.

# 'Continue': no Windows PowerShell, 'Stop' transforma avisos normais do
# Docker (que saem no canal de erro) em falha.
$ErrorActionPreference = 'Continue'
Set-Location -Path $PSScriptRoot
$envPath = Join-Path $PSScriptRoot '.env'
$utf8 = New-Object System.Text.UTF8Encoding $false

function Falar([string]$texto) { Write-Host $texto }

function Tem-Valor([string]$texto, [string]$nome) {
    return [regex]::IsMatch($texto, "(?m)^\s*$nome=\S+")
}

# 1. Docker aberto?
$null = docker info 2>$null
if ($LASTEXITCODE -ne 0) {
    Falar 'O Docker Desktop não está aberto (ou ainda está ligando).'
    Falar 'Abra o Docker Desktop, espere aparecer "Engine running" e rode de novo.'
    exit 1
}

# 2. Arquivo .env e chave de acesso do Éden
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $PSScriptRoot '.env.exemplo') $envPath
    Falar 'Criei o arquivo .env nesta pasta.'
}
$texto = [System.IO.File]::ReadAllText($envPath)
if (-not (Tem-Valor $texto 'OPENJARVIS_API_KEY')) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    $b64 = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
    $linha = "OPENJARVIS_API_KEY=oj_sk_$b64"
    if ([regex]::IsMatch($texto, '(?m)^\s*OPENJARVIS_API_KEY=.*$')) {
        $texto = [regex]::Replace($texto, '(?m)^\s*OPENJARVIS_API_KEY=.*$', $linha)
    } else {
        $texto = "$linha`r`n$texto"
    }
    [System.IO.File]::WriteAllText($envPath, $texto, $utf8)
    Falar 'Criei a chave de acesso do Éden (fica só no arquivo .env).'
}

# 3. Chaves das IAs (só confere se existem)
$temOpenAI = Tem-Valor $texto 'OPENAI_API_KEY'
$temAnthropic = Tem-Valor $texto 'ANTHROPIC_API_KEY'
if (-not $temOpenAI -and -not $temAnthropic) {
    Falar ''
    Falar 'Falta a chave de pelo menos uma IA no arquivo .env.'
    Falar 'Abra o .env no Bloco de Notas, cole a chave depois de OPENAI_API_KEY= (ou ANTHROPIC_API_KEY=),'
    Falar 'salve e rode o iniciar-eden de novo.'
    Start-Process notepad.exe $envPath
    exit 1
}
if (-not $temOpenAI) { Falar 'Aviso: sem chave da OpenAI. O ChatGPT (dia a dia) e o microfone não vão funcionar.' }
if (-not $temAnthropic) { Falar 'Aviso: sem chave da Anthropic. O Claude (missões) não vai funcionar.' }

# 4. Montar e ligar
Falar ''
Falar 'Montando e ligando o Éden. Na primeira vez demora bastante (vários minutos); depois fica mais rápido.'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Falar ''
    Falar 'Não consegui montar ou ligar o Éden. Copie as últimas linhas acima e mande para o Claude.'
    exit 1
}

# 5. Esperar responder
Falar 'Esperando o Éden responder…'
$pronto = $false
for ($i = 0; $i -lt 90; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $pronto = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

if ($pronto) {
    Falar ''
    Falar 'Pronto! O Éden está em http://localhost:8000'
    Falar 'Na primeira vez ele pede a chave de acesso: abra o .env no Bloco de Notas e copie o que vem depois de OPENJARVIS_API_KEY='
    Start-Process 'http://localhost:8000'
} else {
    Falar ''
    Falar 'O Éden ainda não respondeu. Últimas linhas do registro:'
    docker compose logs --tail 30 eden
    exit 1
}
