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
- `src/openjarvis/eden/`: código de servidor do Éden. Hoje, as conversas
  guardadas no servidor (`conversations.py`) e as rotas `/v1/eden/...` (`routes.py`).
- `frontend/src/lib/eden-sync.ts` e `eden-sync-merge.ts`: sincronização das
  conversas entre os aparelhos.
- `frontend/src/components/Chat/EdenSyncBadge.tsx` e
  `frontend/src/components/Sidebar/EdenSyncStatus.tsx`: avisos de sincronização.
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

## Arquivos do OpenJarvis modificados

Mudanças de lógica têm um comentário `Éden:` explicando o motivo. Textos
traduzidos para português foram trocados no próprio lugar, sem comentário
em cada linha.

| Arquivo | O que mudou |
|---|---|
| `frontend/index.html` | Nome Éden, idioma pt-BR e nome do atalho no iPhone |
| `frontend/vite.config.ts` | Nome e descrição do app instalável (PWA) |
| `frontend/src/App.tsx` | Não abre o convite do ranking público quando o ranking está desligado; liga a sincronização |
| `frontend/src/components/Layout.tsx` | Aviso de servidor fora do ar em português |
| `frontend/src/components/Chat/InputArea.tsx` | Caixa de mensagem, estados ("Escrevendo…", "Pensando…"), erros e atalhos em português |
| `frontend/src/components/Chat/ChatArea.tsx` | Saudação e tela inicial em português; dicas de "conectar fontes de dados" escondidas no piloto (`SHOW_DATA_SOURCE_HINTS`) |
| `frontend/src/components/Chat/MicButton.tsx` | Avisos do microfone em português e nome acessível no botão |
| `frontend/src/components/Chat/MessageBubble.tsx` | "Copiar mensagem"; botão visível em telas de toque; aviso de sincronização nas mensagens do usuário |
| `frontend/src/components/Chat/SpeakMessageButton.tsx` | "Ouvir mensagem" em português |
| `frontend/src/components/Sidebar/Sidebar.tsx` | Menu lateral em português e nomes acessíveis nos botões de ícone; situação da sincronização |
| `frontend/src/components/Sidebar/ConversationList.tsx` | Tempos ("há 5 min") e textos em português; botão de apagar visível em telas de toque |
| `frontend/src/lib/store.ts` | Título de conversa nova "Nova conversa" (`NEW_CHAT_TITLE`); microfone ligado por padrão |
| `frontend/src/hooks/useSpeech.ts` | Grava num formato aceito pela transcrição e envia o tipo certo de arquivo (corrige o iPhone) |
| `src/openjarvis/core/config.py` | Novo campo `speech.openai_model` |
| `src/openjarvis/speech/_discovery.py` | Passa o modelo de transcrição escolhido |
| `src/openjarvis/speech/openai_whisper.py` | Aceita modelos de transcrição novos, além do whisper-1 |
| `src/openjarvis/server/api_routes.py` | Usa o idioma da configuração quando o app não informa |
| `src/openjarvis/server/app.py` | Registra as rotas de conversas do Éden |
| `tests/speech/…`, `tests/server/test_speech_routes.py`, `frontend/src/hooks/useSpeech.test.ts` | Testes das mudanças de voz |

## Regras deste fork

- Nada de chaves de API, senhas, tokens ou dados pessoais no repositório.
- Mudar o mínimo possível no código original, para conseguir trazer as
  atualizações do OpenJarvis (botão "Sync fork" no GitHub).
