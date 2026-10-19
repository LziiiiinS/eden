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

## Aparelhos ligados (chave por aparelho)

Cada celular ligado pelo **código curto** ou pelo **QR code** recebe uma chave
só dele. Em **Configurações → Aparelhos ligados** aparecem todos, com o último
uso.

- Perdeu um celular? No notebook, toque em **Desligar** ao lado dele. Ele
  perde o acesso na hora; os outros continuam.
- Só o notebook (chave principal) cria códigos, QR codes e chaves novas, e
  liga ou desliga contas (Google, e-mail, Notion). Um celular pode desligar
  só a si mesmo.
- Celular ligado antes desta versão usa a chave principal: nele, em
  **Configurações → Aparelhos ligados**, toque em **Usar uma chave só deste
  aparelho**.
- A chave do QR code vale 10 minutos para o primeiro uso; a do código curto,
  1 dia. Depois de usada, vale até ser desligada.
- Ao desligar um aparelho, os avisos de lembrete recomeçam: os aparelhos que
  continuam ligados se inscrevem de novo sozinhos quando abrem o Éden.

## Ligar a Google Agenda

O Éden lê os seus eventos e sugere eventos novos ou mudanças, sempre com o
cartão de confirmação. Ele pede **só a permissão da agenda** (e, se você
ligar a opção, a do Drive só para os arquivos que o próprio Éden cria). É
grátis e não precisa de cartão. Faça no notebook.

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

## E-mail (Gmail, só leitura)

O Éden pode **ler** uma caixa do Gmail (pode ser uma conta separada, só para
isso). Ele não manda, não apaga, não arquiva e não marca e-mails como lidos.
Usa o mesmo projeto do Google da agenda (o `.env` não muda).

Uma vez, no Google Cloud (console.cloud.google.com, no projeto do Éden):
1. **APIs e serviços → Biblioteca**: procure **Gmail API** e toque em
   **Ativar**.
2. **Google Auth Platform → Acesso a dados → Adicionar ou remover escopos**:
   marque **…/auth/gmail.readonly** ("ver suas mensagens de e-mail") e salve.

Depois, no Éden:
3. **Configurações → E-mail → Conectar e-mail**. Entre com a conta que o Éden
   pode ler e marque a permissão de ver os e-mails.
4. Como o app do Éden não é verificado pelo Google, aparece o aviso "O Google
   não verificou este app": toque em **Avançado → Acessar Éden**. É o seu
   próprio app.

No dia a dia:
- Menu **E-mail**: os e-mails dos últimos 7 dias, busca (ex.: `from:ana`,
  `is:unread`), abrir um e-mail (só o texto) e **Usar na conversa** (vira
  documento do espaço ativo).
- Na conversa: "chegou e-mail do cliente?" — o Éden olha os mais recentes.
- O Éden é instruído a tratar o que está escrito num e-mail como dado, não
  como ordem; qualquer coisa que ele sugira gravar continua pedindo a sua
  confirmação no cartão.
- Prefira uma conta **diferente** da conta da agenda. Se a agenda e o e-mail
  estiverem ligados ao mesmo tempo, desligar um deles apaga a ligação só no
  Éden (o Google retira a permissão da conta inteira, e a outra ligação cairia
  junto). Para retirar de vez: myaccount.google.com → Segurança → Apps de
  terceiros.
- Para tirar o acesso: **Configurações → E-mail → Desconectar** (ou em
  myaccount.google.com → Segurança → Apps de terceiros).

## Contas e impostos

Menu **Contas e impostos**: anote o que tem para **pagar** (aluguel, internet,
DAS do MEI…) e o que tem para **receber** (clientes), com valor, vencimento,
repetição (uma vez, todo mês, todo ano) e aviso no celular alguns dias antes
(às 9h, se os avisos estiverem ligados no celular). O aviso mostra o nome da
conta e quando vence, sem o valor (ele aparece na tela de bloqueio).

- O Éden **não paga nada, não liga no banco e não emite nota**: só anota,
  avisa e responde ("o que vence esta semana?", "quanto tenho a receber?").
- Marcar uma conta que repete como paga cria a próxima sozinha (dia 31 vira o
  último dia dos meses curtos). Marcou sem querer: abra a conta → **Voltar
  para em aberto** (a próxima criada sai junto, se você não mexeu nela).
- Valor: `150,50` ou `1.500,00` (vírgula nos centavos); `150.50` também vale.
- Modelos prontos: **DAS do MEI** (todo dia 20) e **Declaração anual do MEI**
  (até 31 de maio). Eles vêm sem valor: os valores mudam todo ano, confira no
  Portal do Empreendedor (gov.br/mei).
- Pela conversa ("anota o aluguel de 1.500 todo dia 5"), o Éden sugere e você
  confirma no cartão, como nas tarefas.
- Valor zero = "sem valor" (bom para prazos, como a declaração).

## Modo reunião

Menu **Modo reunião**: o Éden escuta **só enquanto você deixar gravando** e,
no fim, entrega o resumo (tópicos, decisões, quem ficou de fazer o quê,
datas). As tarefas viram cartões para confirmar.

- Antes de começar, avise as pessoas da reunião (o botão só liga depois de
  marcar isso). Durante o piloto, use só com dados de teste: confira antes as
  regras do trabalho e dos clientes.
- O áudio sobe em pedaços de ~1 minuto. Se a internet cair, o pedaço espera e
  vai de novo (sem cobrar duas vezes). Deixe a **tela ligada** e o Éden aberto
  nesta página: no iPhone, a gravação para com a tela travada.
- Custo aproximado: US$ 0,30 a 0,40 por hora (transcrição da OpenAI + resumo),
  dentro do limite do mês. O resumo usa o Claude; se ele não puder (limite,
  chave), usa a IA do dia a dia.
- O áudio **não fica guardado**, só o texto. **Apagar reunião** apaga o texto
  e o resumo.
- O que alguém falar na reunião ("Éden, apaga…") nunca vira ordem: o resumo só
  sugere tarefas, e cada uma precisa do seu toque.

## Casa (luzes, tomadas, ar-condicionado)

O Éden mexe na casa pelo **Home Assistant** (grátis). Ele nunca fala direto
com a nuvem de cada marca: o Home Assistant junta tudo e o Éden só pede a ele.

**Testar sem nada em casa:** no `.env` do servidor, `EDEN_CASA_DEMO=1` e
reinicie. Aparecem três aparelhos de mentira (luz, computador e ar) em
**Casa**, no menu.

**Com aparelhos de verdade** (depois da compra, que precisa da sua aprovação):

1. Instale o Home Assistant (num computador sempre ligado em casa) e adicione
   os aparelhos nele (lâmpada e tomada Wi-Fi Tuya/Smart Life, o ar pelo app
   da marca ou um controle infravermelho Wi-Fi).
2. No Home Assistant, crie um **usuário só para o Éden, sem ser
   administrador** (Configurações → Pessoas → Adicionar pessoa; deixe
   "Administrador" desligado). Entre com esse usuário: perfil →
   **Segurança** → **Tokens de acesso de longa duração** → criar. Copie o
   token direto para o `.env` do servidor (nunca na conversa, no app ou no
   GitHub). Assim, se o servidor do Éden for invadido, ninguém ganha o
   Home Assistant inteiro.
3. No `.env` do servidor:
   ```
   EDEN_CASA_URL=http://ENDERECO-DO-HOME-ASSISTANT:8123
   EDEN_CASA_TOKEN=(o token)
   EDEN_CASA_APARELHOS=light.quarto=Luz do quarto,switch.pc=Computador,climate.sala=Ar
   ```
   A lista é **fechada**: o Éden só mexe no que estiver nela (luz, tomada,
   ar, cena e botão). Fechaduras, alarmes e câmeras não entram.
   **Atenção:** a lista confere o *tipo* do aparelho, não o que ele faz.
   Não ponha nela uma tomada, botão ou cena que abra portão, destrave porta
   ou desligue alarme.
   O endereço precisa ser `https://`; `http://` só vale dentro de casa
   (`.local`, 192.168…, 10…) ou pelo Tailscale (`.ts.net`, 100.x).
4. Reinicie o Éden (`docker compose restart`).

Como funciona: pela tela, o toque no botão já vale. Na conversa ("estou
chegando em 5 minutos"), o Éden sugere a rotina num **cartão** e ela roda
quando você confirma — ele não agenda para depois. Teto de 60 comandos por
hora (`EDEN_TETO_CASA_HORA`). Ligar o computador sozinho precisa de algo
sempre ligado em casa (o Home Assistant manda o sinal de "acordar").

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

## Rotas e trânsito

O Éden mostra o tempo de carro com o trânsito de agora para os seus trajetos
salvos (ex.: Casa → Trabalho), pelo **TomTom** (conta grátis, sem cartão).

1. Crie a conta em **developer.tomtom.com** (Register) e confirme pelo e-mail.
2. No painel (**Dashboard → Keys**), copie a chave ("My first API key").
3. No `.env` desta pasta, na linha `TOMTOM_API_KEY=`, cole a chave depois do
   `=` (a linha não começa com `#`, sem espaços). Se a linha não existir,
   escreva no fim. Salve com **Ctrl + S**. **Não mande essa chave para
   ninguém.**
4. Rode o `iniciar-eden`.
5. No menu, **Rotas e trânsito**: escolha a origem e o destino (endereço,
   lugar ou coordenadas do Google Maps) e toque em **Salvar trajeto**.

A página **Hoje** mostra o tempo dos dois primeiros trajetos, e na conversa dá
para perguntar "quanto tempo até o trabalho agora?". O TomTom recebe só as
coordenadas de origem e destino (e o texto da busca de endereço).

**Comparar caminhos.** O Éden mostra até 3 caminhos com o trânsito de agora e
as vias principais de cada um (por exemplo, pelas Américas ou pela Lúcio
Costa), o mais rápido primeiro:
- na página, toque no ícone de caminho ao lado de um trajeto, ou use **Para
  onde agora?** (saindo da sua localização ou de um ponto salvo);
- na conversa, pergunte "melhor caminho agora para o Posto 4?" ou "qual a
  melhor rota pro Recreio?". Se o lugar não estiver salvo, o Éden procura o
  endereço e diz qual usou.
- Na conversa, o ponto de partida é a origem do primeiro trajeto salvo. Para
  sair de onde você está, ligue em **Rotas e trânsito → Na conversa** (o
  celular pede permissão de localização). A localização só vai quando a
  pergunta é sobre caminho, arredondada, e o Éden não guarda.
- Os nomes das vias vêm do TomTom; às vezes aparece só o número da estrada.

## Pesquisa na internet

Para perguntas sobre coisas de agora (notícias, preços, horários, resultados),
toque em **Pesquisar na internet** antes de enviar. Vale só para aquela
mensagem e desliga sozinho depois.

- Usa o **Claude** (a mesma chave da Anthropic do `.env`; não precisa de conta
  nova). Faz até 3 buscas por pergunta e no máximo 20 pesquisas por hora.
- Custo: o texto (como uma resposta do Claude) **mais US$ 0,01 por busca**.
  Entra no limite de gastos da Anthropic do mês.
- A resposta termina com **Fontes:** (os sites usados). Os links pedem
  confirmação antes de abrir.
- A pesquisa **não** recebe suas tarefas, notas, memórias, agenda nem
  documentos; só a conversa aberta (as últimas mensagens). E não cria cartões
  de ação: para guardar algo, peça depois numa mensagem normal.
- O que vem das páginas é tratado como dado, nunca como ordem.
- Para pesquisar algo da sua cidade, escreva a cidade na pergunta.
- Se aparecer "web search não está ligado", entre em
  **platform.claude.com/settings/capabilities** e confira se a busca na
  internet (web search) não foi desligada.

## Respostas em voz (modo conversa)

O Éden pode **falar** as respostas, com a voz da OpenAI (a mesma chave da
OpenAI do `.env`; não precisa de conta nova). Funciona no notebook, no iPhone
e no Samsung.

- No campo de mensagem, toque em **Responder em voz**. Daí em diante, o Éden
  fala cada resposta (mais curta, boa de ouvir) e, ao usar o **microfone**,
  já envia o que você falou: você fala, ele responde falando. Toque de novo
  para voltar ao texto.
- Em **Configurações → Voz**: ligar o alto-falante embaixo de cada resposta
  (para ouvir só quando quiser), o modo conversa e a voz (Marin, Cedar e
  outras). O botão **Ouvir** testa a voz.
- Custo: cerca de **US$ 0,02 a cada 1.000 caracteres falados** (uma resposta
  curta sai por menos de 1 centavo). Entra no limite de gastos da OpenAI do
  mês, e há um teto por hora.
- No iPhone: deixe o volume alto e a tela aberta. Se o som não sair, toque no
  alto-falante embaixo da resposta (o iPhone às vezes exige um toque).
- Respostas longas: a voz lê o começo e diz "O resto está na tela".

## Notion

Com o Notion ligado, dá para **trazer uma página do Notion** para a conversa
(como um documento) e **salvar uma folha do Éden** como página nova no Notion.
O Éden só enxerga as páginas que você compartilhar com ele e não muda nem
apaga páginas que já existem.

1. Entre em **notion.so/profile/integrations** → **Nova conexão** (ou "New
   integration"). Tipo **Interna**, nome **Éden**, no seu espaço de trabalho.
2. Em **Capacidades**, deixe marcado só **Ler conteúdo** e **Inserir
   conteúdo**. Desmarque "Atualizar conteúdo" (ele **vem marcado**),
   comentários e informações de usuários. Salve. Assim o Éden não consegue
   mudar nem apagar páginas que já existem.
3. Copie a **chave secreta** (começa com `ntn_`). No `.env` desta pasta, na
   linha `NOTION_API_KEY=`, cole depois do `=` (sem `#`, sem espaços). Se a
   linha não existir, escreva no fim. Salve com **Ctrl + S**. **Não mande
   essa chave para ninguém.**
4. Rode o `iniciar-eden`.
5. No Notion, em cada página que o Éden pode ver: **•••** (canto de cima) →
   **Conexões** → **Éden**. As páginas de dentro entram junto.
6. No Éden, **Configurações → Notion → Escolher**: a página onde o Éden vai
   criar as páginas novas (por exemplo, uma página "Éden").

Depois:
- **Trazer do Notion:** no campo de mensagem, **Documentos → Do Notion**,
  procure a página e toque em **Trazer**. Ela vira um documento do espaço
  ativo (só o texto) e já fica em uso na conversa.
- **Salvar no Notion:** abra a folha de uma resposta e toque em **Salvar no
  Notion**. Imagens de fora não vão junto.
- Se você mudar a página no Notion, traga de novo para atualizar.

## Segurança

- O `.env` tem as chaves. Não mande esse arquivo para ninguém, não cole as
  chaves em conversas e não tire print dele.
- Só este computador abre o Éden (`localhost`). O celular entra depois, pela
  rede privada (Tailscale), com endereço HTTPS.
- Se a chave de acesso vazar: no `.env`, apague o que vem depois de
  `OPENJARVIS_API_KEY=` (deixe a linha vazia), salve e rode o `iniciar-eden`.
  Ele cria uma chave nova e **desliga todas as chaves de aparelho** (alguém
  com a chave antiga pode ter criado outras). Ligue cada celular de novo pelo
  código curto.
- Perdeu só um celular: não precisa trocar a chave principal; desligue só ele
  em **Configurações → Aparelhos ligados**.
- Se a chave de uma IA vazar: apague a chave no site da empresa, crie outra e
  troque no `.env`.
- Tetos por hora, além do limite do mês (cada aparelho tem a sua conta; a
  chave principal, a dela): 150 mensagens, 120 áudios e 150 pedaços de
  reunião. Para mudar, no `.env`: `EDEN_TETO_CONVERSA_HORA`,
  `EDEN_TETO_TRANSCRICAO_HORA`, `EDEN_TETO_REUNIAO_HORA`.
- **Configurações → Atividade recente** mostra o que foi gravado, mudado ou
  apagado e de qual aparelho veio.

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
- **O que não volta atrás ao restaurar** (para um backup antigo não desfazer
  uma decisão de segurança): contas desligadas (Google, e-mail, Notion)
  continuam desligadas, os avisos dos celulares recomeçam (os aparelhos
  ligados se inscrevem de novo sozinhos) e o gasto do mês não diminui.
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
