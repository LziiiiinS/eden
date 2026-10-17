# Éden no notebook (Windows)

Esta pasta liga o Éden no próprio computador, usando o Docker Desktop. O código
não precisa estar no computador: a cada vez que você liga, o Docker busca a
versão mais nova do Éden no GitHub e monta.

## O que precisa

- **Docker Desktop** instalado e aberto ("Engine running" no canto de baixo).
- **Esta pasta** no computador. Se não tiver: no GitHub, botão verde
  **Code → Download ZIP**, extraia e use a pasta `deploy/eden`.
- A **chave de pelo menos uma IA**, com crédito: OpenAI (ChatGPT e microfone)
  e/ou Anthropic (Claude, para as missões).

## Primeira vez

1. Dê dois cliques em **iniciar-eden.cmd**. Ele cria o arquivo `.env`, cria a
   chave de acesso do Éden e abre o `.env` no Bloco de Notas.
2. Cole a chave da OpenAI depois de `OPENAI_API_KEY=` e a da Anthropic depois
   de `ANTHROPIC_API_KEY=` (sem espaços, sem aspas). Salve e feche.
3. Dê dois cliques em **iniciar-eden.cmd** de novo. Na primeira vez demora
   bastante (vários minutos), porque monta tudo do zero.
4. O navegador abre em **http://localhost:8000**. O Éden pede a **chave de
   acesso**: abra o `.env` no Bloco de Notas, copie o que vem depois de
   `OPENJARVIS_API_KEY=` e cole.

## No dia a dia

- **Ligar** (e atualizar para a versão mais nova): `iniciar-eden.cmd`.
  Antes de atualizar, ele faz sozinho um backup (ficam os 5 mais novos).
- **Parar**: `parar-eden.cmd`.
- **Backup**: `backup-eden.cmd`. Pode rodar com o Éden ligado.
- **Voltar um backup**: `restaurar-eden.cmd`.
- O Docker Desktop precisa estar aberto.

## Testar a sincronização sem celular

Abra o Éden numa janela normal e numa janela **InPrivate** (Edge: Ctrl+Shift+N).
Cada janela funciona como um aparelho diferente. Na InPrivate o Éden pede a
chave de acesso de novo. Escreva numa janela e veja a conversa aparecer na outra
(na hora em que você volta para ela, ou em até 30 segundos).

## Ligar o celular

- No Éden do computador: **Configurações → Conectar um celular → Mostrar QR
  code**. Com o Tailscale ligado no celular, aponte a câmera para o QR code.
- **iPhone com o Éden na tela de início**: o ícone não enxerga a chave que o QR
  code salvou no Safari e pede a chave de novo. No computador, toque em
  **Mostrar código**; no iPhone, toque em **Tenho um código do notebook** e
  digite o código (vale 5 minutos e serve uma vez só).

## Ligar a Google Agenda

O Éden lê os seus eventos e sugere eventos novos ou mudanças, sempre com o
cartão de confirmação. Ele pede **só a permissão da agenda**. É grátis e não
precisa de cartão. Faça no notebook.

1. No Éden: **Configurações → Google Agenda**. Copie o **endereço de retorno**
   que aparece lá (termina em `/v1/eden/google/retorno`).
2. Abra **https://console.cloud.google.com** com a sua conta do Google e crie
   um projeto chamado `Eden`.
3. No menu, abra **APIs e serviços → Biblioteca**, procure
   **Google Calendar API** e clique em **Ativar**. Se quiser salvar folhas no
   Drive, ative também a **Google Drive API**.
4. Abra **Google Auth Platform** (ou "Tela de consentimento OAuth"):
   - **Branding**: nome do app `Éden` e o seu e-mail.
   - **Público (Audience)**: tipo **Externo**. Depois clique em **Publicar o
     app** (Em produção). Assim a ligação não cai a cada 7 dias. O Google
     avisa que o app não foi verificado; para uso só seu, não precisa.
   - **Acesso a dados (Data access)**: adicione o escopo
     `.../auth/calendar.events` e, para o Drive, também `.../auth/drive.file`
     (só os arquivos que o Éden criar).
5. Em **Clientes**, clique em **Criar cliente**:
   - tipo **Aplicativo da Web**, nome `Éden`;
   - em **URIs de redirecionamento autorizados**, cole o endereço do passo 1;
   - crie e copie o **ID do cliente** e a **chave secreta do cliente**.
6. Abra o `.env` desta pasta no Bloco de Notas e acrescente, no fim:
   `GOOGLE_CLIENT_ID=` (cole o ID) e, na linha de baixo,
   `GOOGLE_CLIENT_SECRET=` (cole a chave secreta). Salve. **Não mande esses
   valores para ninguém.**
7. Rode o `iniciar-eden`.
8. No Éden: **Configurações → Google Agenda → Conectar**. Entre na sua conta.
   No aviso "o Google não verificou este app", toque em **Avançado → Acessar
   Éden**. Marque a caixa da **agenda** e continue.

**Dica de segurança (convites):** qualquer pessoa pode mandar um convite que
aparece na sua agenda, e o título dele chega ao Éden. O Éden trata título como
dado (nunca como ordem), marca "convite ainda não aceito" e ignora convites
recusados. Para reduzir convites estranhos: no Google Agenda, **Configurações →
Configurações de eventos → Adicionar convites à minha agenda → "Somente se o
remetente for conhecido"**.

**Salvar folhas no Drive (opcional):** em **Configurações → Google Agenda**,
toque em **Permitir salvar no Drive** e marque as duas caixas na tela do
Google. Depois, na folha de uma resposta, aparece **Salvar no Drive**: vira um
Google Docs numa pasta "Éden" do seu Drive. O Éden só enxerga os arquivos que
ele mesmo cria.

Para desligar: **Configurações → Google Agenda → Desconectar**. Ao mudar o
Éden para outro computador ou servidor, a ligação precisa ser feita de novo
(a autorização não vai no backup).

## Documentos na conversa

No campo de mensagem, toque em **Documentos** → **Enviar arquivo** e escolha um
PDF, Word (.docx), .txt ou .md (até 10 MB). No celular, o seletor de arquivos
também mostra o Google Drive. O Éden guarda **só o texto** do arquivo, no
espaço ativo, e usa nas conversas em que você marcar **Usar aqui** (até 3 por
conversa).

- PDF escaneado (só imagem) não tem texto para ler.
- Documento grande vai só em parte para a IA, e cada mensagem daquela conversa
  custa um pouco mais. Tire da conversa (×) quando não precisar mais.
- O que está escrito num documento é tratado como dado, nunca como ordem.
- Para apagar de vez: **Documentos** → lixeira.

## Clima, vento e ondas

No menu, **Clima e ondas**. Começa desligado; ao tocar em **Ligar**, o Éden
passa a consultar o **Open-Meteo** (grátis para uso pessoal, sem conta e sem
chave). Só vão as coordenadas dos lugares que você cadastrar.

- **Cidade:** busque pelo nome e toque em **+ cidade**.
- **Praia ou pico:** busque pelo nome ou, para um pico exato, no Google Maps
  toque e segure no mar perto do pico, copie os números (ex.: `-27.6025,
  -48.4320`), cole em **Coordenadas** e toque em **Adicionar praia**.
- A estrela marca o lugar principal (o que o Éden usa quando você pergunta
  "vai chover amanhã?" sem dizer onde).
- A tabela mostra vento e rajadas em nós, ondas e swell (altura e período),
  temperatura e chuva, de 3 em 3 horas, por 3 dias.

## Segurança

- O `.env` tem as chaves. Não mande esse arquivo para ninguém, não cole as
  chaves em conversas e não tire print dele.
- Só este computador abre o Éden (`localhost`). O celular entra depois, pela
  rede privada (Tailscale), com endereço HTTPS.
- Se a chave de acesso vazar: no `.env`, apague o que vem depois de
  `OPENJARVIS_API_KEY=` (deixe a linha vazia), salve e rode o `iniciar-eden`.
  Ele cria uma chave nova; digite a nova em cada aparelho.
- Se a chave de uma IA vazar: apague a chave no site da empresa, crie outra e
  troque no `.env`.

## Onde ficam os dados

Conversas, gastos do mês e o seu perfil (`USER.md`) ficam no volume
**eden-dados** do Docker. Parar, desligar o computador ou atualizar o Éden não
apaga nada. Só apaga se o volume for removido no Docker Desktop.

## Backup (cópia de segurança)

- **Fazer**: dois cliques em `backup-eden.cmd`. O arquivo vai para a pasta
  `backups`, com data e hora no nome (ex.:
  `eden-backup-manual-20261015-221500.tar.gz`).
- **O que entra**: conversas, gastos do mês, perfil (`USER.md`), memória
  (`MEMORY.md`), tarefas, notas e o texto dos documentos. **Não entram chaves**
  (o `.env` nunca vai para o backup).
- **Guarde uma cópia fora do computador** (pendrive, HD externo) de vez em
  quando: se o computador estragar, o backup da pasta `backups` vai junto.
- O backup tem as suas conversas: trate como documento pessoal e não mande
  para ninguém.
- **Voltar um backup**: dois cliques em `restaurar-eden.cmd`, escolha o número
  e digite `SIM`. Ele confere o arquivo, para o Éden, guarda o estado atual
  num backup `antes-de-restaurar` (para dar para desfazer), troca os dados e
  liga de novo. Um arquivo danificado ou que não seja do Éden é recusado sem
  mexer em nada.
- **Backup de outro computador** (ex.: levar para o servidor): copie o arquivo
  para a pasta `backups` do outro lado e use o `restaurar-eden` de lá.
- Depois de voltar um backup, celulares e navegadores que ainda tiverem
  conversas que não estavam nele mandam essas conversas de volta sozinhos.

## Problemas comuns

- **"O Docker Desktop não está aberto"**: abra o Docker Desktop, espere
  "Engine running" e rode de novo.
- **"O Éden ainda não respondeu"**: o script mostra as últimas linhas do
  registro. Mande essas linhas para o Claude (elas não têm chaves; o `.env`
  nunca).
