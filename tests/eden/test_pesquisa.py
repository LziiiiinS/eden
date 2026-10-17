"""Éden: pesquisa na internet (Anthropic falsa; nada sai para a internet)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from openjarvis.eden import pesquisa
from openjarvis.eden.budget import BudgetExceeded, SpendingLedger
from openjarvis.eden.providers import TRUNCATED_NOTE, ProviderError
from openjarvis.eden.settings import EdenSettings

TZ = timezone(timedelta(hours=-3))
MOMENTO = datetime(2026, 10, 17, 18, 30, tzinfo=TZ)


class RespostaFalsa:
    def __init__(self, status, linhas, corpo=b""):
        self.status_code = status
        self._linhas = linhas
        self._corpo = corpo

    async def aread(self):
        return self._corpo

    async def aiter_lines(self):
        for linha in self._linhas:
            yield linha

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class AnthropicFalsa:
    def __init__(self, resposta):
        self.resposta = resposta
        self.pedidos = []

    def __call__(self):
        return self

    def stream(self, metodo, url, json=None, headers=None):
        self.pedidos.append(
            {"metodo": metodo, "url": url, "json": json, "headers": headers}
        )
        return self.resposta

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def sse(*eventos):
    linhas = []
    for e in eventos:
        linhas += [f"event: {e.get('type', '')}", "data: " + json.dumps(e), ""]
    return linhas


def texto(t):
    return {
        "type": "content_block_delta",
        "index": 0,
        "delta": {"type": "text_delta", "text": t},
    }


def resultado(*itens):
    return {
        "type": "content_block_start",
        "index": 2,
        "content_block": {
            "type": "web_search_tool_result",
            "tool_use_id": "srvtoolu_1",
            "content": [
                {
                    "type": "web_search_result",
                    "url": url,
                    "title": titulo,
                    "encrypted_content": "xyz",
                    "page_age": None,
                }
                for url, titulo in itens
            ],
        },
    }


def citacao(url, titulo):
    return {
        "type": "content_block_delta",
        "index": 3,
        "delta": {
            "type": "citations_delta",
            "citation": {
                "type": "web_search_result_location",
                "url": url,
                "title": titulo,
                "cited_text": "...",
                "encrypted_index": "abc",
            },
        },
    }


BUSCA = {
    "type": "content_block_start",
    "index": 1,
    "content_block": {
        "type": "server_tool_use",
        "id": "srvtoolu_1",
        "name": "web_search",
        "input": {},
    },
}
INICIO = {
    "type": "message_start",
    "message": {"usage": {"input_tokens": 900, "output_tokens": 1}},
}


def fim(entrada=12000, saida=300, buscas=1, motivo="end_turn"):
    return {
        "type": "message_delta",
        "delta": {"stop_reason": motivo},
        "usage": {
            "input_tokens": entrada,
            "output_tokens": saida,
            "server_tool_use": {"web_search_requests": buscas},
        },
    }


def coletar(gen):
    async def rodar():
        return [t async for t in gen]

    return asyncio.run(rodar())


def gasto(ledger):
    return ledger._conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM spending"
    ).fetchone()[0]


@pytest.fixture
def ledger(tmp_path):
    led = SpendingLedger(tmp_path / "gastos.db")
    yield led
    led.close()


def rodar(ledger, linhas, mensagens=None, settings=None, status=200, corpo=b""):
    falsa = AnthropicFalsa(RespostaFalsa(status, linhas, corpo))
    gen = pesquisa.stream_pesquisa(
        mensagens
        or [{"role": "user", "content": "Quem ganhou o jogo do Flamengo ontem?"}],
        settings=settings or EdenSettings(),
        ledger=ledger,
        client_factory=falsa,
        api_key="sk-ant-teste",
        momento=MOMENTO,
    )
    return falsa, gen


# ── pedido ────────────────────────────────────────────────────────────────


def test_request_uses_search_tool_and_no_personal_context(ledger):
    falsa, gen = rodar(ledger, sse(INICIO, texto("Oi"), fim()))
    coletar(gen)
    pedido = falsa.pedidos[0]
    assert pedido["url"] == "https://api.anthropic.com/v1/messages"
    corpo = pedido["json"]
    assert corpo["tools"] == [pesquisa.FERRAMENTA]
    assert corpo["tools"][0]["type"] == "web_search_20250305"
    assert corpo["tools"][0]["max_uses"] == 3
    assert corpo["model"] == "claude-sonnet-5-5"
    assert corpo["max_tokens"] <= 4096
    assert corpo["stream"] is True
    sistema = corpo["system"]
    assert "17/10/2026 18:30" in sistema and "sábado" in sistema
    assert "nunca ordem" in sistema and "eden-acao" in sistema
    # Nada do contexto pessoal do Éden (memórias, tarefas, agenda...).
    for proibido in ("Memórias", "Tarefas", "Agenda", "Documentos", "Levi"):
        assert proibido not in sistema
    assert pedido["headers"]["x-api-key"] == "sk-ant-teste"


def test_conversation_is_trimmed_and_action_blocks_removed():
    bloco = '```eden-acao\n{"tipo":"tarefa.criar","titulo":"x"}\n```'
    bruto = [
        {"role": "system", "content": "ignorar"},
        {"role": "assistant", "content": "começa no assistente"},
        {"role": "user", "content": "a" * 5000},
        {"role": "assistant", "content": f"Feito.\n{bloco}"},
        {"role": "user", "content": "e"},
        {"role": "user", "content": "amanhã?"},
        {"role": "tool", "content": "x"},
        {"role": "user", "content": 123},
    ]
    msgs = pesquisa.mensagens_da_conversa(bruto)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert len(msgs[0]["content"]) == pesquisa.MAX_CHARS_HISTORICO
    assert "eden-acao" not in msgs[1]["content"] and msgs[1]["content"] == "Feito."
    assert msgs[2]["content"] == "e\n\namanhã?"


def test_conversation_keeps_only_last_messages():
    bruto = []
    for i in range(20):
        bruto += [
            {"role": "user", "content": f"p{i}"},
            {"role": "assistant", "content": f"r{i}"},
        ]
    bruto.append({"role": "user", "content": "final"})
    msgs = pesquisa.mensagens_da_conversa(bruto)
    assert len(msgs) <= pesquisa.MAX_MENSAGENS
    assert msgs[-1]["content"] == "final" and msgs[0]["role"] == "user"


def test_long_question_is_cut():
    msgs = pesquisa.mensagens_da_conversa([{"role": "user", "content": "x" * 50000}])
    assert len(msgs[0]["content"]) == pesquisa.MAX_CHARS_PERGUNTA


@pytest.mark.parametrize(
    "bruto",
    [
        None,
        [],
        "texto",
        [{"role": "assistant", "content": "só resposta"}],
        [{"role": "user", "content": "   "}],
    ],
)
def test_conversation_needs_a_question(bruto):
    with pytest.raises(pesquisa.ErroPesquisa):
        pesquisa.mensagens_da_conversa(bruto)


# ── resposta e fontes ────────────────────────────────────────────────────


def test_streams_text_and_appends_sources(ledger):
    linhas = sse(
        INICIO,
        texto("Vou pesquisar."),
        BUSCA,
        resultado(
            ("https://ge.globo.com/jogo", "Flamengo vence | ge"),
            ("https://exemplo.com/a(b)", "Com parênteses"),
            ("javascript:alert(1)", "ruim"),
            ("https://ruim.com/x y", "espaço"),
        ),
        texto("O Flamengo venceu por 2 a 1."),
        citacao("https://ge.globo.com/jogo", "Flamengo vence | ge"),
        citacao("https://citada.com/so-na-citacao", "Só [na] citação <b>"),
        fim(),
    )
    _, gen = rodar(ledger, linhas)
    saida = "".join(coletar(gen))
    assert saida.startswith("Vou pesquisar.\n\nO Flamengo venceu por 2 a 1.")
    assert "**Fontes:**" in saida
    fontes = saida.split("**Fontes:**")[1]
    linhas_fontes = [linha for linha in fontes.splitlines() if linha.strip()]
    # Citadas primeiro, depois as outras encontradas.
    assert linhas_fontes[0] == "- [Flamengo vence  ge](https://ge.globo.com/jogo)"
    assert linhas_fontes[1] == "- [Só na citação b](https://citada.com/so-na-citacao)"
    assert "https://exemplo.com/a%28b%29" in fontes
    assert "javascript" not in fontes and "ruim.com" not in fontes


def test_sources_are_capped():
    fontes = {}
    for i in range(30):
        pesquisa.anotar_fonte(fontes, f"https://site{i}.com/", f"Site {i}")
    texto_final = pesquisa.texto_fontes(fontes, [])
    assert texto_final.count("\n- [") == pesquisa.MAX_FONTES


def test_title_falls_back_to_host():
    fontes = {}
    pesquisa.anotar_fonte(fontes, "https://g1.globo.com/rj/noticia", "   ")
    assert fontes["https://g1.globo.com/rj/noticia"] == "g1.globo.com"


def test_no_sources_no_footer(ledger):
    _, gen = rodar(ledger, sse(INICIO, texto("Sem busca."), fim(buscas=0)))
    assert "".join(coletar(gen)) == "Sem busca."


def test_truncated_and_paused_notes(ledger):
    _, gen = rodar(ledger, sse(INICIO, texto("a"), fim(motivo="max_tokens")))
    assert TRUNCATED_NOTE in "".join(coletar(gen))
    _, gen = rodar(ledger, sse(INICIO, texto("a"), fim(motivo="pause_turn")))
    assert "parou no meio" in "".join(coletar(gen))


def test_error_event_raises(ledger):
    _, gen = rodar(
        ledger, sse(INICIO, {"type": "error", "error": {"message": "Overloaded"}})
    )
    with pytest.raises(ProviderError, match="Overloaded"):
        coletar(gen)


def test_http_error_explained_with_console_hint(ledger):
    corpo = json.dumps({"error": {"message": "web search is not enabled"}}).encode()
    _, gen = rodar(ledger, [], status=400, corpo=corpo)
    with pytest.raises(ProviderError) as exc:
        coletar(gen)
    assert "web search is not enabled" in str(exc.value)
    assert "settings/capabilities" in str(exc.value)
    # Recusado: nada cobrado.
    assert gasto(ledger) == 0


# ── gastos ───────────────────────────────────────────────────────────────


def test_cost_counts_final_tokens_and_searches(ledger):
    settings = EdenSettings()
    _, gen = rodar(
        ledger,
        sse(INICIO, BUSCA, texto("ok"), fim(entrada=12000, saida=300, buscas=2)),
        settings=settings,
    )
    coletar(gen)
    esperado = (
        settings.token_cost("anthropic", settings.mission_model, 12000, 300) + 2 * 0.01
    )
    assert abs(gasto(ledger) - esperado) < 1e-9
    linha = ledger._conn.execute(
        "SELECT kind, input_tokens, estimated FROM spending"
    ).fetchone()
    assert tuple(linha) == ("pesquisa", 12000, 0)


def test_interrupted_search_is_estimated_high(ledger):
    settings = EdenSettings()
    linhas = sse(INICIO, BUSCA, texto("começo"))  # sem message_delta
    _, gen = rodar(ledger, linhas, settings=settings)
    coletar(gen)
    linha = ledger._conn.execute(
        "SELECT input_tokens, estimated, cost_usd FROM spending"
    ).fetchone()
    assert linha[0] >= 900 + pesquisa.TOKENS_POR_BUSCA_ESTIMADOS
    assert linha[1] == 1
    assert linha[2] >= 0.01


def test_budget_blocks_before_calling(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 5.0, "anthropic": 0.05})
    falsa, gen = rodar(ledger, sse(INICIO, texto("x"), fim()), settings=settings)
    with pytest.raises(BudgetExceeded):
        coletar(gen)
    assert falsa.pedidos == []


def test_reservation_includes_searches_and_results():
    settings = EdenSettings()
    reserva = pesquisa.reserva_usd(settings, 3000)
    assert reserva > 3 * pesquisa.PRECO_BUSCA_USD
    minimo = settings.token_cost(
        "anthropic", settings.mission_model, pesquisa.RESERVA_RESULTADOS_TOKENS, 0
    )
    assert reserva > minimo


def test_without_key_or_claude_model(ledger):
    falsa = AnthropicFalsa(RespostaFalsa(200, []))
    with pytest.raises(pesquisa.ErroPesquisa) as exc:
        coletar(
            pesquisa.stream_pesquisa(
                [{"role": "user", "content": "x"}],
                settings=EdenSettings(),
                ledger=ledger,
                client_factory=falsa,
                api_key="",
            )
        )
    assert exc.value.codigo == "eden_pesquisa_sem_chave"
    settings = EdenSettings(mission_model="gpt-6.1-sol")
    with pytest.raises(pesquisa.ErroPesquisa) as exc:
        coletar(
            pesquisa.stream_pesquisa(
                [{"role": "user", "content": "x"}],
                settings=settings,
                ledger=ledger,
                client_factory=falsa,
                api_key="sk-ant-teste",
            )
        )
    assert exc.value.codigo == "eden_pesquisa_modelo"
    assert falsa.pedidos == []


# ── limite por hora e formato ────────────────────────────────────────────


def test_hourly_limit():
    relogio = [0.0]
    limite = pesquisa.LimitePorHora(maximo=2, relogio=lambda: relogio[0])
    assert limite.usar() and limite.usar()
    assert not limite.usar()
    relogio[0] = 3601.0
    assert limite.usar()


def test_sse_chunks_are_openai_style():
    pedaco = pesquisa.pedaco_sse("olá")
    assert pedaco.startswith("data: ") and pedaco.endswith("\n\n")
    dados = json.loads(pedaco[6:])
    assert dados["choices"][0]["delta"]["content"] == "olá"
    fim_txt = pesquisa.fim_sse()
    assert '"finish_reason": "stop"' in fim_txt and fim_txt.endswith("data: [DONE]\n\n")


def test_route_headers():
    cab = pesquisa.cabecalhos_rota(EdenSettings())
    assert cab["X-Eden-Mode"] == "missao" and cab["X-Eden-Provider"] == "anthropic"
    assert cab["X-Eden-Reason"] == "pesquisa" and cab["Cache-Control"] == "no-store"
