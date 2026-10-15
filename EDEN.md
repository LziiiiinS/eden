# Éden

O Éden é um assistente pessoal **baseado no [OpenJarvis](https://github.com/open-jarvis/OpenJarvis)**,
projeto da Universidade Stanford distribuído sob a licença Apache 2.0
(veja `LICENSE`). Este repositório é um fork: o código original continua
com seus autores, e as mudanças feitas para o Éden estão listadas abaixo.

"OpenJarvis" é o nome do projeto original. O Éden não é um produto oficial
do OpenJarvis nem de Stanford.

## Onde fica o que é do Éden

- `eden/config.toml`: configuração do servidor do Éden (sem chaves nem dados pessoais).
- `eden/SOUL.md`: personalidade e regras do Éden.
- `eden/USER.exemplo.md`: modelo do perfil do usuário. O perfil real fica só no servidor.
- `src/openjarvis/eden/`: código de servidor do Éden:
  - `conversations.py` e `routes.py`: conversas guardadas no servidor e rotas `/v1/eden/...`;
  - `settings.py`: seção `[eden]` do `config.toml` (modelos, limites, preços);
  - `routing.py`: qual IA responde (dia a dia x missão);
  - `providers.py`: conversa com a OpenAI (Responses API) e a Anthropic, anotando o gasto;
  - `budget.py`, `speech_budget.py` e `chat_hooks.py`: limite de gastos do mês.
- `frontend/src/lib/eden-sync.ts` e `eden-sync-merge.ts`: sincronização das
  conversas entre os aparelhos.
- `frontend/src/components/Chat/EdenSyncBadge.tsx` e
  `frontend/src/components/Sidebar/EdenSyncStatus.tsx`: avisos de sincronização.
- `frontend/src/lib/eden-ai.ts`, `components/Chat/EdenModeSwitch.tsx`,
  `components/Chat/EdenAiLabel.tsx` e `components/Sidebar/EdenSpending.tsx`:
  escolha da IA, aviso de qual IA respondeu e gastos do mês.
- `frontend/src/components/EdenAccessGate.tsx` e `frontend/src/lib/eden-key.ts`:
  pedem a chave de acesso do servidor na primeira vez que o aparelho abre o
  Éden (sem preenchimento automático do navegador, com botão de mostrar, e
  aceitando a linha inteira do `.env`).
- `frontend/src/pages/EdenSettingsPage.tsx`: configurações do Éden em português.
- `deploy/eden/`: rodar o Éden com Docker (notebook Windows agora; servidor
  depois). Passo a passo em `deploy/eden/LEIA-ME.md`.
- `.github/workflows/eden-checks.yml` e `.github/eden/`: testes automáticos
  (sem segredos, não publica nada), incluindo ligar a imagem do Éden e
  conferir o básico.
- `.gitattributes`: finais de linha certos para os scripts de Windows e Linux.
- `tests/eden/`: testes do código do Éden.

## Como funciona a sincronização

- O aparelho guarda as conversas (funciona sem internet) e envia cada conversa
  ao servidor assim que possível. O servidor é a fonte de verdade.
- Os IDs das mensagens vêm do aparelho: reenviar não duplica.
- Em conflito, vale a versão mais nova. Mensagens de dois aparelhos se juntam.
- Uma mensagem só conta como salva quando o servidor confirma o ID dela. Até lá
  aparece "Salvando…" e, sem conexão, "Não sincronizada".
- Apagar remove o conteúdo no servidor e deixa só uma marca para os outros
  aparelhos também apagarem.
- Cada conversa tem um usuário (`user_id`). No piloto há um só.

## ChatGPT + Claude e limite de gastos

- O app tem três modos: **Automático**, **Dia a dia** (sempre ChatGPT) e
  **Missão** (sempre Claude). São "modelos" do Éden (`eden-auto`, `eden-dia`,
  `eden-missao`) que o servidor troca pelos modelos de `[eden.ias]`.
- No automático, vão para o Claude: pedido de documento ou entrega (proposta,
  contrato, relatório, apresentação, planilha…), mensagem para cliente e pedido
  longo. Uma conversa que virou missão continua no Claude. `/missao` ou `/dia`
  no começo da mensagem força o modo.
- Embaixo de cada resposta aparece qual IA respondeu (e o motivo, ao tocar).
- Limite por mês e por empresa em `[eden.limites]` (US$). Antes de cada pedido
  o servidor confere o gasto do mês mais uma reserva; se passar, recusa antes
  de chamar a IA. O gasto vem dos números de tokens que a empresa informa; sem
  eles, de uma estimativa conservadora. A transcrição de voz também entra.
- O mês vira à meia-noite do dia 1, horário de Brasília.
- O limite cobre a conversa e a transcrição. Funções do OpenJarvis fora do
  piloto (pesquisa aprofundada, agentes) ficam escondidas e não entram na conta.
- O crédito pré-pago nos sites da OpenAI e da Anthropic é uma segunda trava.

## Como rodar

- **Notebook (Windows):** Docker Desktop + a pasta `deploy/eden`. Dois cliques
  em `iniciar-eden.cmd` cria a chave de acesso, monta a versão mais nova do
  GitHub e abre `http://localhost:8000`. Detalhes em `deploy/eden/LEIA-ME.md`.
- As chaves ficam no arquivo `.env` da pasta (fora do GitHub). Os dados
  (conversas, gastos, perfil) ficam no volume `eden-dados` do Docker.
- Dentro do contêiner, `deploy/eden/iniciar-no-conteiner.sh` copia
  `eden/config.toml` e `eden/SOUL.md` para a pasta de dados a cada início e
  cria `USER.md`/`MEMORY.md` vazios só na primeira vez.

## Arquivos do OpenJarvis modificados

Mudanças de lógica têm um comentário `Éden:` explicando o motivo. Textos
traduzidos para português foram trocados no próprio lugar, sem comentário
em cada linha.

| Arquivo | O que mudou |
|---|---|
| `frontend/index.html` | Nome Éden, idioma pt-BR e nome do atalho no iPhone |
| `frontend/vite.config.ts` | Nome e descrição do app instalável (PWA) |
| `frontend/src/App.tsx` | Não abre o convite do ranking público quando o ranking está desligado; liga a sincronização; tela da chave de acesso; configurações do Éden em `/settings` (as originais em `/settings/avancado`); atalhos ⌘K e ⌘I desligados no servidor do Éden |
| `frontend/src/pages/ChatPage.tsx` | Painel do sistema (energia, GPU) escondido no piloto |
| `frontend/src/components/Chat/XRayFooter.tsx` | Detalhes da resposta em português, com qual IA respondeu e por quê |
| `frontend/src/components/Layout.tsx` | Aviso de servidor fora do ar em português |
| `frontend/src/components/Chat/InputArea.tsx` | Caixa de mensagem, estados ("Escrevendo…", "Pensando…"), erros e atalhos em português; modos do Éden no lugar da pesquisa aprofundada; no celular, Enter pula linha e o motivo do microfone indisponível aparece escrito |
| `frontend/src/components/Chat/ChatArea.tsx` | Saudação e tela inicial em português; dicas de "conectar fontes de dados" escondidas no piloto (`SHOW_DATA_SOURCE_HINTS`); botão do painel do sistema escondido |
| `frontend/src/components/Chat/MicButton.tsx` | Avisos do microfone em português e nome acessível no botão |
| `frontend/src/components/Chat/MessageBubble.tsx` | "Copiar mensagem"; botão visível em telas de toque; aviso de sincronização nas mensagens do usuário; qual IA respondeu |
| `frontend/src/components/Chat/SpeakMessageButton.tsx` | "Ouvir mensagem" em português |
| `frontend/src/components/Sidebar/Sidebar.tsx` | Menu lateral em português e nomes acessíveis nos botões de ícone; situação da sincronização; gastos do mês; no piloto, menu só com Conversa e Configurações e seletor de modelos escondido no servidor do Éden |
| `frontend/src/components/Sidebar/ConversationList.tsx` | Tempos ("há 5 min") e textos em português; botão de apagar visível em telas de toque |
| `frontend/src/lib/store.ts` | Título de conversa nova "Nova conversa" (`NEW_CHAT_TITLE`); microfone ligado por padrão |
| `frontend/src/hooks/useSpeech.ts` | Grava num formato aceito pela transcrição e envia o tipo certo de arquivo (corrige o iPhone); envia a duração da gravação |
| `frontend/src/lib/sse.ts` | Erros do servidor em português; lê qual IA respondeu |
| `frontend/src/lib/api.ts` | Envia a duração do áudio; erro da transcrição em português |
| `frontend/src/types/index.ts` | Campos do Éden na telemetria da mensagem |
| `src/openjarvis/core/config.py` | Novo campo `speech.openai_model` |
| `src/openjarvis/speech/_discovery.py` | Passa o modelo de transcrição escolhido |
| `src/openjarvis/speech/openai_whisper.py` | Aceita modelos de transcrição novos, além do whisper-1; lê a duração do áudio |
| `src/openjarvis/server/api_routes.py` | Usa o idioma da configuração quando o app não informa; limite de gastos na transcrição |
| `src/openjarvis/server/app.py` | Registra as rotas de conversas do Éden |
| `src/openjarvis/server/routes.py` | Conversa passa pela escolha de IA e pelo limite do Éden; modos do Éden na lista de modelos; erro de geração em português |
| `src/openjarvis/server/cloud_router.py` | OpenAI e Anthropic passam pelo Éden (Responses API + limite) |
| `deploy/docker/Dockerfile` | Rust 1.89 (a 1.88 não montava mais); SDKs da OpenAI e da Anthropic; arquivos do Éden e pasta `/dados` na imagem |
| `deploy/docker/Dockerfile.gpu`, `Dockerfile.gpu.rocm`, `Dockerfile.sandbox`, `tests/deployment/test_docker.py` | Rust 1.89, a versão mínima de `rust/rust-toolchain.toml` |
| `.gitignore` | Deixa o modelo `deploy/eden/.env.exemplo` ir para o GitHub (o `.env` de verdade continua fora) |
| `tests/speech/…`, `tests/server/test_speech_routes.py`, `frontend/src/hooks/useSpeech.test.ts` | Testes das mudanças de voz |

## Regras deste fork

- Nada de chaves de API, senhas, tokens ou dados pessoais no repositório.
- Mudar o mínimo possível no código original, para conseguir trazer as
  atualizações do OpenJarvis (botão "Sync fork" no GitHub).
