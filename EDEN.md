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

## Arquivos do OpenJarvis modificados

Cada mudança no código original tem um comentário `Éden:` explicando o motivo.

| Arquivo | O que mudou |
|---|---|
| `frontend/index.html` | Nome Éden, idioma pt-BR e nome do atalho no iPhone |
| `frontend/vite.config.ts` | Nome e descrição do app instalável (PWA) |
| `frontend/src/App.tsx` | Não abre o convite do ranking público quando o ranking está desligado |
| `frontend/src/components/Layout.tsx` | Aviso de servidor fora do ar com o nome Éden |
| `frontend/src/components/Chat/InputArea.tsx` | Texto da caixa de mensagem com o nome Éden |
| `frontend/src/hooks/useSpeech.ts` | Grava num formato aceito pela transcrição e envia o tipo certo de arquivo (corrige o iPhone) |
| `src/openjarvis/core/config.py` | Novo campo `speech.openai_model` |
| `src/openjarvis/speech/_discovery.py` | Passa o modelo de transcrição escolhido |
| `src/openjarvis/speech/openai_whisper.py` | Aceita modelos de transcrição novos, além do whisper-1 |
| `src/openjarvis/server/api_routes.py` | Usa o idioma da configuração quando o app não informa |
| `tests/speech/…`, `tests/server/test_speech_routes.py`, `frontend/src/hooks/useSpeech.test.ts` | Testes das mudanças de voz |

## Regras deste fork

- Nada de chaves de API, senhas, tokens ou dados pessoais no repositório.
- Mudar o mínimo possível no código original, para conseguir trazer as
  atualizações do OpenJarvis (botão "Sync fork" no GitHub).
