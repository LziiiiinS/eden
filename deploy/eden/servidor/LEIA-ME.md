# Éden no servidor (Hetzner CX23, Ubuntu 24.04)

Este guia liga o Éden num servidor na internet, para ele funcionar com o
notebook desligado. O servidor **não fica aberto para a internet**: o Éden só
é acessado pela sua rede privada (Tailscale), igual ao notebook hoje.

> **Antes de começar:** contratar o servidor é decisão sua (tem custo mensal;
> confira o preço atual no site da Hetzner). Nada aqui contrata nada sozinho.

## O que você vai precisar

- Conta na Hetzner com forma de pagamento (você cria).
- O notebook com o Windows (para os comandos abaixo, no PowerShell).
- A mesma conta do Tailscale do notebook e dos celulares.
- As chaves das IAs (as mesmas do `.env` do notebook).

## 1. Criar a chave SSH no notebook (uma vez só)

A chave SSH é o "crachá" do notebook para entrar no servidor, sem senha.

1. Abra o **PowerShell** (menu Iniciar → digite PowerShell).
2. Rode: `ssh-keygen -t ed25519 -C "notebook-levi"`
3. Aperte **Enter** para o local padrão. Quando pedir *passphrase*, crie uma
   frase (recomendado) e anote num lugar seguro.
4. Mostre a parte **pública** da chave:
   `Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub`
5. Copie a linha inteira (começa com `ssh-ed25519`). Essa parte pode ser
   colada na Hetzner. **O arquivo sem `.pub` nunca sai do notebook.**

## 2. Criar o servidor na Hetzner

No painel da Hetzner Cloud, crie um projeto (ex.: `Eden`) e adicione um
servidor com:

- **Imagem:** Ubuntu 24.04.
- **Tipo:** CX23 (x86, CPU compartilhada).
- **Local:** qualquer um que ofereça o CX23.
- **Rede:** deixe o **IPv4 público** ligado (o GitHub não funciona só com IPv6).
- **Chave SSH:** cole a linha `ssh-ed25519 …` do passo 1.
- **Nome:** `eden-servidor`.
- **Backups da Hetzner:** opcional e pago à parte. Veja a seção
  "Backups fora do servidor".

Crie o servidor e anote o **endereço IPv4** que aparece.

## 3. Entrar no servidor

No PowerShell do notebook:

```
ssh root@ENDERECO-IPV4
```

Na primeira vez ele pergunta se confia no servidor: digite `yes`. Se criou
passphrase, ela é pedida agora.

## 4. Instalar o Éden

Já dentro do servidor (o começo da linha fica `root@eden-servidor`):

```
curl -fsSL https://raw.githubusercontent.com/LziiiiinS/eden/main/deploy/eden/servidor/instalar.sh -o instalar.sh
bash instalar.sh
```

1. No passo do Tailscale aparece um **link**: abra no navegador, entre na sua
   conta do Tailscale e autorize o servidor.
2. Na primeira vez o script para pedindo a chave das IAs:
   - `nano /opt/eden/.env`
   - cole a chave depois de `OPENAI_API_KEY=` e a da Anthropic depois de
     `ANTHROPIC_API_KEY=` (no PowerShell, colar = botão direito do mouse);
   - salve: **Ctrl+O**, **Enter**, **Ctrl+X**;
   - rode de novo: `bash instalar.sh`
3. A montagem do Éden demora bastante na primeira vez (pode passar de 20
   minutos). Pode deixar rodando.
4. No fim aparece o endereço: `https://eden-servidor.….ts.net`.

## 5. Abrir nos aparelhos

1. No notebook (com Tailscale ligado), abra o endereço do passo 4.
2. Ele pede a chave de acesso. Para ver a chave, no servidor:
   `sudo grep '^OPENJARVIS_API_KEY=' /opt/eden/.env | cut -d= -f2`
   (não tire print).
3. Nos celulares: no Éden do notebook, **Configurações → Conectar um celular**
   e leia o QR code com a câmera.

## 6. Levar as conversas do notebook para o servidor

1. No notebook: `backup-eden.cmd` (na pasta do Éden).
2. No PowerShell, dentro da pasta do Éden do notebook, mande o arquivo
   (troque pelo nome real do backup):
   `scp .\backups\eden-backup-manual-AAAAMMDD-HHMMSS.tar.gz root@eden-servidor:/root/`
3. No servidor:
   `sudo /opt/eden/restaurar-eden.sh /root/eden-backup-manual-AAAAMMDD-HHMMSS.tar.gz`
   e depois `rm /root/eden-backup-*.tar.gz`
4. No notebook, pare o Éden local (`parar-eden.cmd`), para não ter dois Édens
   com conversas diferentes.

## 6b. Avisos, celulares e Google Agenda no endereço novo

O servidor tem endereço e chave de acesso novos (`https://eden-servidor.….ts.net`).

- **Celulares:** leia o QR code de novo (Configurações → Conectar um celular,
  no Éden do servidor). No **iPhone**, abra pelo Safari, toque em
  *Compartilhar → Adicionar à Tela de Início* e entre pelo ícone novo com o
  **código curto** (Configurações → Mostrar código). Pode apagar o ícone
  antigo.
- **Avisos de lembrete:** ligue de novo em cada aparelho (Configurações →
  Avisos de lembrete neste aparelho → Ativar). Os do notebook não valem aqui.
- **Google Agenda** (se você usa):
  1. no Éden do servidor, **Configurações → Google Agenda**: copie o
     endereço de retorno novo;
  2. no Google Cloud (**Clientes → Éden**), acrescente esse endereço em
     **URIs de redirecionamento autorizados** e salve (o do notebook pode
     ficar);
  3. no servidor, `nano /opt/eden/.env` e acrescente as linhas
     `GOOGLE_CLIENT_ID=…` e `GOOGLE_CLIENT_SECRET=…` (as mesmas do notebook);
  4. `cd /opt/eden && docker compose up -d`;
  5. **Configurações → Google Agenda → Conectar** (a autorização não vem no
     backup, de propósito).

## 7. Fechar o SSH para a internet

Antes, dois cuidados para não ficar trancado do lado de fora:

1. **Desligar a expiração da chave do servidor no Tailscale.** Por padrão, a
   chave de cada aparelho expira depois de alguns meses; no servidor, isso o
   tiraria da rede privada (e o Éden e o SSH parariam juntos). No painel do
   Tailscale, em **Machines**, nos três pontinhos do `eden-servidor`, escolha
   **Disable key expiry**.
2. **Senha do root para emergência.** No servidor, rode `passwd` e crie uma
   senha forte; guarde num gerenciador de senhas. Ela **não** serve para o
   SSH (que só aceita chave): serve só para o **console** do painel da
   Hetzner, se um dia o Tailscale falhar.

Depois que você conseguir entrar pelo Tailscale (`ssh root@eden-servidor`,
com o Tailscale ligado no notebook):

```
sudo /opt/eden/fechar-ssh-publico.sh
```

A partir daí o servidor não aceita nenhuma conexão da internet. Em
emergência, entre pelo **console** do painel da Hetzner com a senha do root
(se esqueceu, o painel tem a opção de redefinir a senha do root).

- Use verificação em duas etapas na conta do Tailscale (e na do GitHub, que
  é o login dela): quem entra na conta do Tailscale chega ao servidor.

## No dia a dia

| Para…                         | Rode no servidor                                  |
|-------------------------------|---------------------------------------------------|
| Atualizar o Éden              | `sudo /opt/eden/atualizar-eden.sh`                |
| Fazer um backup agora         | `sudo /opt/eden/backup-eden.sh`                   |
| Voltar um backup              | `sudo /opt/eden/restaurar-eden.sh`                |
| Ver se está ligado            | `cd /opt/eden && docker compose ps`               |
| Ver o registro (sem chaves)   | `cd /opt/eden && docker compose logs --tail 50 eden` |
| Reiniciar                     | `cd /opt/eden && docker compose restart eden`     |
| Éden para outra pessoa        | `sudo /opt/eden/nova-pessoa.sh NOME` (veja abaixo) |

- **Atualizar** faz um backup antes e, se a versão nova não responder, volta
  sozinho para a anterior.
- **Atualização automática do Éden: desligada.** Para ligar (todo dia às
  04:15): `sudo systemctl enable --now eden-atualizar.timer`.
- **Atualizações de segurança do Ubuntu: automáticas.** Se pedirem reinício,
  o servidor reinicia às 04:45 e o Éden volta sozinho.
- **Backup diário:** às 03:30, em `/opt/eden/backups` (ficam os 14 mais
  novos). Ver quando roda: `systemctl list-timers eden-backup.timer`.

## Outra pessoa (namorada, pai): um Éden só dela

Cada pessoa ganha o **próprio Éden**, ao lado do seu, sem nada compartilhado:
chave de acesso, conversas, memórias, tarefas, contas e backup próprios. As
chaves de IA são **as da pessoa** (conta dela, limite dela): o seu `.env`
nunca é copiado.

**Antes (decisões suas e dela):** quem e quando; a pessoa cria a conta de IA
dela (com limite baixo e verificação em duas etapas); o celular dela entra na
sua rede do Tailscale (convite ou compartilhar só o servidor). Isso mexe em
contas reais: só com a sua autorização e a dela.

1. No servidor: `sudo /opt/eden/nova-pessoa.sh ana` (só letras minúsculas e
   números). Na 1ª vez ele prepara tudo e para pedindo a chave de IA dela.
2. `sudo nano /opt/eden-ana/.env`: a pessoa cola a chave dela depois de
   `OPENAI_API_KEY=` (ou `ANTHROPIC_API_KEY=`). Não mande chave por mensagem.
3. Rode de novo `sudo /opt/eden/nova-pessoa.sh ana`. Ele liga o Éden dela e
   mostra o endereço: `https://eden-servidor.….ts.net:8443` (a 2ª pessoa fica
   na `:8444`).
4. Para ligar o celular dela: abra o endereço dela no notebook, entre com a
   chave dela e mostre o QR code das Configurações **na frente do aparelho**.

- **Atualizar:** o `atualizar-eden.sh` atualiza o seu e depois o de cada
  pessoa (com backup antes de cada um).
- **Backup dela:** todo dia às 03:41 (a 2ª pessoa, 03:42…), em
  `/opt/eden-ana/backups`. Agora: `sudo /opt/eden-ana/backup-eden.sh`.
- **Voltar um backup dela:** `sudo /opt/eden-ana/restaurar-eden.sh`.
- **Ver se está ligado:** `cd /opt/eden-ana && sudo docker compose ps`.
- **Desligar (sem apagar nada):** `cd /opt/eden-ana && sudo docker compose
  down` e `sudo tailscale serve --https=8443 off`. Para ligar de novo: rode o
  `nova-pessoa.sh ana`.
- **Memória:** cada Éden usa pouca memória parado, mas pode usar até 2 GB
  numa conversa pesada. Com 3 Édens, acompanhe com `free -h` nos primeiros
  dias.

## Backups fora do servidor

O backup diário fica no próprio servidor: se o servidor for perdido, ele vai
junto. Duas opções para ter uma cópia fora:

1. **Backups da Hetzner** (pago à parte): cópia do servidor inteiro, feita
   pela Hetzner. Liga no painel, em *Backups*. Decisão sua.
2. **Baixar para o notebook de vez em quando** (grátis): no PowerShell, na
   pasta do Éden do notebook:
   `scp "root@eden-servidor:/opt/eden/backups/eden-backup-diario-*.tar.gz" .\backups\`

## Segurança

- Ninguém da internet acessa o Éden: ele só escuta dentro do servidor
  (`127.0.0.1:8000`; o de outra pessoa, `8001`, `8002`…) e o Tailscale
  entrega para os aparelhos da sua rede com HTTPS.
- Firewall: só a rede privada (e o SSH, até o passo 7) entram. SSH só com
  chave, nunca com senha.
- Chaves: ficam em `/opt/eden/.env`, que só o root lê. Nunca vão para o
  GitHub, para o backup ou para o registro.
- Se a chave de acesso vazar: apague o que vem depois de
  `OPENJARVIS_API_KEY=` em `/opt/eden/.env`, rode `bash instalar.sh` de novo
  (ele cria outra) e digite a nova em cada aparelho.
- Se a chave de uma IA vazar: apague no site da empresa, crie outra, troque
  no `.env` e rode `cd /opt/eden && docker compose up -d`.

## Problemas comuns

- **"Permission denied (publickey)"** ao entrar: a chave do passo 1 não foi
  colada na Hetzner, ou o comando está sem `root@`.
- **O link do Tailscale expirou:** rode `tailscale up --ssh --hostname eden-servidor`.
- **"O Éden não respondeu"**: o script mostra as últimas linhas do registro.
  Mande essas linhas para o Claude (elas não têm chaves; o `.env` nunca).
