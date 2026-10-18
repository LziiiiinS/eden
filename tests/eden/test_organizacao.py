"""Éden (Parte 2): espaços, perfil, memórias, tarefas, notas, ações e contexto."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from openjarvis.eden import acoes, contexto
from openjarvis.eden.organizacao import (
    ErroOrganizacao,
    Organizacao,
    resumo_data,
    texto,
)

TZ = timezone(timedelta(hours=-3))
# 15/10/2026, 10:00 em Brasília.
AGORA = int(datetime(2026, 10, 15, 10, 0, tzinfo=TZ).timestamp() * 1000)
HOJE = date(2026, 10, 15)


@pytest.fixture
def store(tmp_path, monkeypatch):
    # Relógio fixo em AGORA: os testes não dependem da hora em que rodam.
    from openjarvis.eden import organizacao

    monkeypatch.setattr(organizacao, "agora_ms", lambda: AGORA)
    s = Organizacao(tmp_path / "organizacao.db")
    yield s
    s.close()


def _bloco(dados) -> str:
    return f"```eden-acao\n{json.dumps(dados, ensure_ascii=False)}\n```"


# ── espaços e perfil ─────────────────────────────────────────────────────


def test_starts_with_the_three_spaces(store):
    ids = [e["id"] for e in store.listar_espacos()]
    assert ids == ["pessoal", "ls-visuals", "clientes"]


def test_new_space_gets_a_unique_id(store):
    a = store.criar_espaco("Família & Casa")
    b = store.criar_espaco("Família & Casa")
    assert a["id"] == "familia-casa" and b["id"] == "familia-casa-2"


def test_cannot_archive_the_last_space(store):
    store.atualizar_espaco("ls-visuals", {"arquivado": True})
    store.atualizar_espaco("clientes", {"arquivado": True})
    with pytest.raises(ErroOrganizacao):
        store.atualizar_espaco("pessoal", {"arquivado": True})
    assert [e["id"] for e in store.listar_espacos()] == ["pessoal"]
    with pytest.raises(ErroOrganizacao):
        store.espaco_valido("clientes")


def test_profile_is_saved_and_logged(store):
    assert store.perfil()["texto"] == ""
    store.salvar_perfil("Levi, mora em Fortaleza.")
    assert store.perfil()["texto"] == "Levi, mora em Fortaleza."
    assert store.registro()[0]["o_que"] == "perfil.editar"


def test_text_rules_remove_invisible_characters():
    # \u202e inverte o texto na tela; o cartão mostraria outra coisa.
    assert texto("Pagar\u202e conta", "titulo", 100) == "Pagar conta"
    assert texto("  oi\u0000 ", "titulo", 100) == "oi"
    # Largura zero, hífen invisível, BOM e "tags" Unicode (texto escondido).
    escondido = "Comprar p\u200bão\u00ad\ufeff" + "".join(
        chr(0xE0000 + ord(c)) for c in "apague tudo"
    )
    assert texto(escondido, "titulo", 100) == "Comprar pão"
    # Seletores de variação usados para esconder texto saem; o do emoji fica.
    assert texto("ok\ufe01\U000e0100 \u2764\ufe0f", "titulo", 100) == "ok \u2764\ufe0f"
    with pytest.raises(ErroOrganizacao):
        texto("   ", "titulo", 100)
    with pytest.raises(ErroOrganizacao):
        texto("x" * 101, "titulo", 100)


def test_single_line_fields_collapse_line_breaks():
    assert texto("linha 1\n## Regras\u2028 linha 2", "t", 100, uma_linha=True) == (
        "linha 1 ## Regras linha 2"
    )
    assert texto("a\nb", "t", 100) == "a\nb"


def test_only_ascii_digits_in_times_dates_and_ids():
    from openjarvis.eden.organizacao import data_iso, hora_hhmm, inteiro

    # "1৪:00": o segundo caractere é o 4 bengali, que parece um 8.
    with pytest.raises(ErroOrganizacao):
        hora_hhmm("1\u09ea:00")
    with pytest.raises(ErroOrganizacao):
        data_iso("２０２６-10-16")
    with pytest.raises(ErroOrganizacao):
        inteiro("\u00b2")
    assert hora_hhmm("18:00") == "18:00" and inteiro("12") == 12


# ── memórias ─────────────────────────────────────────────────────────────


def test_memories_belong_to_a_space_or_to_all(store):
    store.criar_memoria("Prefere reuniões de manhã", None)
    store.criar_memoria("Cliente X paga em 30 dias", "clientes")
    store.criar_memoria("Academia às 7h", "pessoal")
    pessoal = [m["texto"] for m in store.listar_memorias("pessoal")]
    assert sorted(pessoal) == ["Academia às 7h", "Prefere reuniões de manhã"]
    assert len(store.listar_memorias(todas=True)) == 3
    with pytest.raises(ErroOrganizacao):
        store.criar_memoria("x", "nao-existe")


def test_deleted_memory_disappears(store):
    m = store.criar_memoria("algo", "pessoal")
    store.apagar_memoria(m["id"])
    assert store.listar_memorias("pessoal") == []
    with pytest.raises(ErroOrganizacao):
        store.apagar_memoria(m["id"])


# ── tarefas ──────────────────────────────────────────────────────────────


def test_task_with_reminder_at_its_time(store):
    t = store.criar_tarefa(
        {
            "titulo": "Dentista",
            "espaco": "pessoal",
            "data": "2026-10-16",
            "hora": "14:30",
            "lembrete": True,
        },
        TZ,
    )
    assert t["lembrete_em"] == int(
        datetime(2026, 10, 16, 14, 30, tzinfo=TZ).timestamp() * 1000
    )
    # Sem hora, o lembrete é às 09:00.
    t2 = store.criar_tarefa(
        {
            "titulo": "Pagar boleto",
            "espaco": "pessoal",
            "data": "2026-10-20",
            "lembrete": True,
        },
        TZ,
    )
    assert local(t2["lembrete_em"]) == datetime(2026, 10, 20, 9, 0, tzinfo=TZ)


def local(ms):
    return datetime.fromtimestamp(ms / 1000, tz=TZ)


def test_task_rules(store):
    with pytest.raises(ErroOrganizacao, match="precisa de uma data"):
        store.criar_tarefa({"titulo": "x", "espaco": "pessoal", "hora": "10:00"}, TZ)
    with pytest.raises(ErroOrganizacao, match="data"):
        store.criar_tarefa(
            {"titulo": "x", "espaco": "pessoal", "data": "16/10/2026"}, TZ
        )
    with pytest.raises(ErroOrganizacao, match="horário"):
        store.criar_tarefa(
            {"titulo": "x", "espaco": "pessoal", "data": "2026-10-16", "hora": "25:00"},
            TZ,
        )
    with pytest.raises(ErroOrganizacao, match="precisa de uma data"):
        store.criar_tarefa({"titulo": "x", "espaco": "pessoal", "lembrete": True}, TZ)


def test_moving_a_task_moves_its_reminder_and_resets_it(store):
    t = store.criar_tarefa(
        {
            "titulo": "Reunião",
            "espaco": "pessoal",
            "data": "2026-10-16",
            "hora": "10:00",
            "lembrete": True,
        },
        TZ,
    )
    store.marcar_lembrete_enviado(t["id"], AGORA)
    t = store.atualizar_tarefa(t["id"], {"data": "2026-10-17"}, TZ)
    assert local(t["lembrete_em"]) == datetime(2026, 10, 17, 10, 0, tzinfo=TZ)
    assert t["lembrete_enviado_em"] is None


def test_open_tasks_order_and_done(store):
    store.criar_tarefa({"titulo": "sem data", "espaco": "pessoal"}, TZ)
    store.criar_tarefa(
        {"titulo": "dia 20", "espaco": "pessoal", "data": "2026-10-20"}, TZ
    )
    c = store.criar_tarefa(
        {"titulo": "dia 16", "espaco": "pessoal", "data": "2026-10-16"}, TZ
    )
    store.criar_tarefa({"titulo": "outro espaço", "espaco": "clientes"}, TZ)
    assert [t["titulo"] for t in store.listar_tarefas("pessoal")] == [
        "dia 16",
        "dia 20",
        "sem data",
    ]
    store.atualizar_tarefa(c["id"], {"feita": True}, TZ)
    assert [t["titulo"] for t in store.listar_tarefas("pessoal", "feitas")] == [
        "dia 16"
    ]
    assert len(store.listar_tarefas(None)) == 3


def test_due_reminders_are_sent_once(store):
    t = store.criar_tarefa(
        {
            "titulo": "Ligar",
            "espaco": "pessoal",
            "data": "2026-10-15",
            "hora": "09:50",
            "lembrete": True,
        },
        TZ,
    )
    store.criar_tarefa(
        {
            "titulo": "Depois",
            "espaco": "pessoal",
            "data": "2026-10-15",
            "hora": "18:00",
            "lembrete": True,
        },
        TZ,
    )
    assert [x["id"] for x in store.lembretes_vencidos(AGORA)] == [t["id"]]
    assert store.marcar_lembrete_enviado(t["id"], AGORA) is True
    assert store.marcar_lembrete_enviado(t["id"], AGORA) is False
    assert store.lembretes_vencidos(AGORA) == []


# ── notas ────────────────────────────────────────────────────────────────


def test_notes_search_and_pinned_first(store):
    store.criar_nota({"texto": "Comprar lente 50mm", "espaco": "ls-visuals"})
    fixa = store.criar_nota(
        {
            "texto": "Vídeo de bastidores",
            "tipo": "ideia",
            "espaco": "ls-visuals",
            "fixada": True,
        }
    )
    store.criar_nota({"texto": "Receita de bolo", "espaco": "pessoal"})
    lista = store.listar_notas("ls-visuals")
    assert lista[0]["id"] == fixa["id"]
    assert [n["texto"] for n in store.listar_notas(None, busca="lente")] == [
        "Comprar lente 50mm"
    ]
    assert [n["texto"] for n in store.listar_notas(None, tipo="ideia")] == [
        "Vídeo de bastidores"
    ]
    # % e _ na busca são letras comuns.
    assert store.listar_notas(None, busca="%") == []


# ── ações propostas ──────────────────────────────────────────────────────


def test_blocks_are_found_and_hidden():
    resposta = "Posso criar.\n\n" + _bloco({"tipo": "tarefa.criar", "titulo": "Pão"})
    assert acoes.extrair_blocos(resposta) == [
        '{"tipo": "tarefa.criar", "titulo": "Pão"}'
    ]
    assert acoes.remover_blocos(resposta) == "Posso criar."
    # Bloco cortado no meio (resposta interrompida) também some da tela.
    assert acoes.remover_blocos('Ok.\n```eden-acao\n{"tipo": ') == "Ok."


def test_proposal_creates_pending_action_with_summary(store):
    resposta = "Combinado.\n" + _bloco(
        {
            "tipo": "tarefa.criar",
            "titulo": "Comprar presente da Ana",
            "data": "2026-10-17",
            "hora": "18:00",
            "lembrete": True,
        }
    )
    criadas, recusadas = acoes.propor(resposta, store, "pessoal", TZ, "c1", AGORA)
    assert recusadas == []
    [acao] = criadas
    assert acao["estado"] == "pendente"
    assert acao["resumo"] == (
        "Criar tarefa “Comprar presente da Ana” em Pessoal — sáb 17/10 18:00"
        " · lembrete sáb 17/10 18:00"
    )
    assert acao["expira_em"] == AGORA + acoes.VALIDADE_MS
    # Nada foi criado ainda.
    assert store.listar_tarefas(None) == []


def test_confirming_runs_exactly_the_stored_action_once(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "tarefa.criar", "titulo": "Pão", "data": "2026-10-16"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    feita = acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 1000)
    assert feita["estado"] == "feita"
    [tarefa] = store.listar_tarefas("pessoal")
    assert tarefa["titulo"] == "Pão" and tarefa["origem"] == "eden"
    assert feita["resultado"] == {"tarefa": tarefa["id"]}
    # Repetir não cria outra.
    with pytest.raises(acoes.ErroAcao) as erro:
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 2000)
    assert erro.value.status == 409
    assert len(store.listar_tarefas("pessoal")) == 1
    assert store.registro()[0]["acao_id"] == acao["id"]


def test_wrong_signature_is_refused_and_action_stays_pending(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "Gosta de café"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    for sig in (None, "", "0" * 64):
        with pytest.raises(acoes.ErroAcao) as erro:
            acoes.confirmar(store, acao["id"], sig, TZ, AGORA)
        assert erro.value.codigo == "eden_acao_assinatura"
    assert store.acao(acao["id"])["estado"] == "pendente"
    assert store.listar_memorias("pessoal") == []


def test_expired_action_is_refused(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "x"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    depois = AGORA + acoes.VALIDADE_MS + 1
    assert store.acao(acao["id"])["estado"] == "pendente"
    with pytest.raises(acoes.ErroAcao) as erro:
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, depois)
    assert erro.value.status == 410


def test_refusing(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "x"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = acoes.recusar(store, criadas[0]["id"], AGORA)
    assert acao["estado"] == "recusada"
    with pytest.raises(acoes.ErroAcao):
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA)


def test_target_deleted_before_confirming_marks_failure(store):
    t = store.criar_tarefa({"titulo": "Lavar carro", "espaco": "pessoal"}, TZ)
    criadas, _ = acoes.propor(
        _bloco({"tipo": "tarefa.concluir", "id": t["id"]}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    assert acao["resumo"].startswith("Marcar como feita a tarefa “Lavar carro”")
    store.apagar_tarefa(t["id"])
    with pytest.raises(acoes.ErroAcao) as erro:
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA)
    assert erro.value.codigo == "eden_acao_falhou"
    assert store.acao(acao["id"])["estado"] == "falhou"


@pytest.mark.parametrize(
    "bloco, motivo",
    [
        ("{nao e json", "JSON"),
        ('["lista"]', "objeto"),
        ('{"tipo": "conta.apagar_tudo"}', "desconhecido"),
        (
            '{"tipo": "tarefa.criar", "titulo": "x", "url": "http://x"}',
            "campos desconhecidos",
        ),
        ('{"tipo": "tarefa.criar", "titulo": ""}', "vazio"),
        ('{"tipo": "tarefa.criar", "titulo": "x", "espaco": "outro"}', "espaço"),
        ('{"tipo": "tarefa.concluir", "id": 999}', "não encontrada"),
        ('{"tipo": "memoria.apagar", "id": "abc"}', "número"),
    ],
)
def test_invalid_proposals_are_refused(store, bloco, motivo):
    criadas, recusadas = acoes.propor(
        f"```eden-acao\n{bloco}\n```", store, "pessoal", TZ, None, AGORA
    )
    assert criadas == []
    assert len(recusadas) == 1 and motivo in recusadas[0]


def test_at_most_five_actions_per_answer(store):
    resposta = "\n".join(
        _bloco({"tipo": "memoria.criar", "texto": f"m{i}"}) for i in range(7)
    )
    criadas, recusadas = acoes.propor(resposta, store, "pessoal", TZ, None, AGORA)
    assert len(criadas) == 5
    assert "5 primeiras" in recusadas[0]


def test_hourly_limit(store, monkeypatch):
    monkeypatch.setattr(acoes, "MAX_ACOES_POR_HORA", 2)
    resposta = "\n".join(
        _bloco({"tipo": "memoria.criar", "texto": f"m{i}"}) for i in range(3)
    )
    criadas, recusadas = acoes.propor(resposta, store, "pessoal", TZ, None, AGORA)
    assert len(criadas) == 2 and "muitas sugestões" in recusadas[0]


def test_one_conversation_cannot_use_up_the_limit_of_the_others(store, monkeypatch):
    # Achado 17: texto injetado numa conversa não trava as sugestões das outras.
    monkeypatch.setattr(acoes, "MAX_ACOES_POR_CONVERSA_HORA", 2)
    monkeypatch.setattr(acoes, "MAX_ACOES_POR_HORA", 5)
    resposta = "\n".join(
        _bloco({"tipo": "memoria.criar", "texto": f"m{i}"}) for i in range(4)
    )
    criadas, recusadas = acoes.propor(resposta, store, "pessoal", TZ, "conv-a", AGORA)
    assert len(criadas) == 2 and "nesta conversa" in recusadas[0]
    # Nova resposta na mesma conversa: continua travada.
    criadas, recusadas = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "outra"}),
        store,
        "pessoal",
        TZ,
        "conv-a",
        AGORA + 1000,
    )
    assert criadas == [] and "nesta conversa" in recusadas[0]
    # Outra conversa ainda consegue.
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "da outra conversa"}),
        store,
        "pessoal",
        TZ,
        "conv-b",
        AGORA + 2000,
    )
    assert len(criadas) == 1
    # Uma hora depois, a primeira volta a funcionar.
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "depois"}),
        store,
        "pessoal",
        TZ,
        "conv-a",
        AGORA + 3600 * 1000 + 1,
    )
    assert len(criadas) == 1


def test_edit_task_summary_and_execution(store):
    t = store.criar_tarefa(
        {
            "titulo": "Reunião",
            "espaco": "clientes",
            "data": "2026-10-16",
            "hora": "10:00",
            "lembrete": True,
        },
        TZ,
    )
    criadas, _ = acoes.propor(
        _bloco({"tipo": "tarefa.editar", "id": t["id"], "data": "2026-10-17"}),
        store,
        "clientes",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    assert (
        acao["resumo"]
        == "Mudar a tarefa “Reunião”: para sáb 17/10 10:00; o lembrete acompanha"
    )
    acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA)
    nova = store.tarefa(t["id"])
    assert nova["data"] == "2026-10-17"
    assert local(nova["lembrete_em"]) == datetime(2026, 10, 17, 10, 0, tzinfo=TZ)


def test_memory_and_note_actions(store):
    m = store.criar_memoria("Antiga", "pessoal")
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.apagar", "id": m["id"]})
        + _bloco(
            {"tipo": "memoria.criar", "texto": "Vale para tudo", "espaco": "todos"}
        )
        + _bloco(
            {
                "tipo": "nota.criar",
                "texto": "Roteiro do vídeo",
                "tipo_nota": "ideia",
                "titulo": "Bastidores",
                "espaco": "ls-visuals",
            }
        ),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    assert [a["resumo"] for a in criadas] == [
        "Apagar da memória: “Antiga”",
        "Guardar na memória (todos os espaços): “Vale para tudo”",
        "Guardar ideia “Bastidores” em LS Visuals: “Roteiro do vídeo”",
    ]
    for a in criadas:
        acoes.confirmar(store, a["id"], a["assinatura"], TZ, AGORA)
    assert [x["texto"] for x in store.listar_memorias("clientes")] == ["Vale para tudo"]
    [nota] = store.listar_notas("ls-visuals")
    assert nota["tipo"] == "ideia" and nota["origem"] == "eden"


def test_unknown_or_malformed_action_ids(store):
    for acao_id in ("x", "../../etc", "a" * 100):
        with pytest.raises(acoes.ErroAcao) as erro:
            acoes.confirmar(store, acao_id, "0" * 64, TZ, AGORA)
        assert erro.value.status == 404
    assert store.acao("../../etc") is None


# ── contexto ─────────────────────────────────────────────────────────────


def test_context_only_has_the_active_space(store):
    store.salvar_perfil("Levi, fotógrafo.")
    store.criar_memoria("Prefere respostas curtas", None)
    store.criar_memoria("Cliente Y é exigente", "clientes")
    store.criar_tarefa(
        {"titulo": "Comprar pão", "espaco": "pessoal", "data": "2026-10-14"}, TZ
    )
    store.criar_tarefa({"titulo": "Entregar fotos Y", "espaco": "clientes"}, TZ)
    store.criar_nota({"texto": "Lista de filmes", "espaco": "pessoal"})
    texto_ctx = contexto.montar(store, "pessoal", TZ, AGORA)
    assert "quinta-feira, 2026-10-15 (15/10/2026), 10:00" in texto_ctx
    assert "Espaço ativo: Pessoal (pessoal)" in texto_ctx
    assert "Levi, fotógrafo." in texto_ctx
    assert '"Prefere respostas curtas" (todos os espaços)' in texto_ctx
    assert '"Comprar pão" — ontem (atrasada)' in texto_ctx
    assert "Lista de filmes" in texto_ctx
    assert "Cliente Y" not in texto_ctx and "Entregar fotos Y" not in texto_ctx
    assert "```eden-acao" in texto_ctx


def test_context_falls_back_to_first_space(store):
    assert "Espaço ativo: Pessoal" in contexto.montar(store, "nao-existe", TZ, AGORA)


def test_date_summary():
    assert resumo_data(None, None, HOJE) == "sem data"
    assert resumo_data("2026-10-15", "18:00", HOJE) == "hoje 18:00"
    assert resumo_data("2026-10-16", None, HOJE) == "amanhã"
    assert resumo_data("2026-10-14", None, HOJE) == "ontem"
    assert resumo_data("2026-10-20", None, HOJE) == "ter 20/10"
    assert resumo_data("2027-01-02", None, HOJE) == "02/01/2027"


def test_context_knows_confirmed_cards_and_other_spaces(store):
    # Teste do Levi (15/10): o lembrete foi criado no Pessoal e confirmado;
    # depois ele trocou para LS Visuals e perguntou o que tinha para hoje.
    criadas, _ = acoes.propor(
        _bloco(
            {
                "tipo": "tarefa.criar",
                "titulo": "Mandar mensagem",
                "data": "2026-10-15",
                "hora": "10:02",
                "lembrete": True,
            }
        ),
        store,
        "pessoal",
        TZ,
        "conv-1",
        AGORA,
    )
    acoes.confirmar(store, criadas[0]["id"], criadas[0]["assinatura"], TZ, AGORA)
    ctx = contexto.montar(store, "ls-visuals", TZ, AGORA + 60_000, conversa_id="conv-1")
    assert "Espaço ativo: LS Visuals" in ctx
    assert "- Pessoal: 1 para hoje, 0 atrasada(s)" in ctx
    assert "Mandar mensagem" in ctx  # no resumo do cartão desta conversa
    assert "CONFIRMADA pela pessoa e gravada (sugerida às 10:00 de 15/10)" in ctx
    # Outra conversa não vê os cartões desta.
    outra = contexto.montar(store, "ls-visuals", TZ, AGORA, conversa_id="conv-2")
    assert "## Sugestões feitas nesta conversa" not in outra
    # No próprio espaço, a tarefa aparece com o horário do lembrete.
    pessoal = contexto.montar(store, "pessoal", TZ, AGORA)
    assert '"Mandar mensagem" — hoje 10:02 · lembrete 10:02' in pessoal


def test_ids_from_another_space_are_refused_and_not_echoed(store):
    segredo = store.criar_memoria("Cliente Acme paga R$ 8.000", "clientes")
    tarefa = store.criar_tarefa(
        {"titulo": "Proposta sigilosa", "espaco": "clientes"}, TZ
    )
    blocos = _bloco({"tipo": "memoria.apagar", "id": segredo["id"]}) + _bloco(
        {"tipo": "tarefa.apagar", "id": tarefa["id"]}
    )
    criadas, recusadas = acoes.propor(blocos, store, "pessoal", TZ, "c1", AGORA)
    assert criadas == []
    assert all("não está no espaço ativo" in r for r in recusadas)
    assert "Acme" not in " ".join(recusadas) and "sigilosa" not in " ".join(recusadas)


def test_refused_cards_do_not_repeat_their_text_in_context(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "texto que foi recusado"}),
        store,
        "pessoal",
        TZ,
        "c1",
        AGORA,
    )
    acoes.recusar(store, criadas[0]["id"], AGORA)
    ctx = contexto.montar(store, "pessoal", TZ, AGORA, conversa_id="c1")
    assert "recusada pela pessoa" in ctx and "texto que foi recusado" not in ctx


def test_card_shows_the_whole_text_and_long_ai_texts_are_refused(store):
    longa = "a" * 450
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": longa}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    assert longa in criadas[0]["resumo"]
    _, recusadas = acoes.propor(
        _bloco({"tipo": "nota.criar", "texto": "b" * 5000}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    assert recusadas and "4000" in recusadas[0]


def test_confirmation_refused_when_the_task_was_edited_meanwhile(store):
    t = store.criar_tarefa({"titulo": "Lavar carro", "espaco": "pessoal"}, TZ)
    criadas, _ = acoes.propor(
        _bloco({"tipo": "tarefa.apagar", "id": t["id"]}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    store.atualizar_tarefa(t["id"], {"titulo": "Lavar carro e moto"}, TZ)
    with pytest.raises(acoes.ErroAcao) as erro:
        acoes.confirmar(store, criadas[0]["id"], criadas[0]["assinatura"], TZ, AGORA)
    assert erro.value.codigo == "eden_acao_falhou"
    assert store.tarefa(t["id"]) is not None


def test_signature_covers_the_summary(store):
    criadas, _ = acoes.propor(
        _bloco({"tipo": "memoria.criar", "texto": "x"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    acao = criadas[0]
    # Trocar o resumo guardado (ex.: banco adulterado) invalida a ação.
    store.transacao(
        lambda c: c.execute(
            "UPDATE acoes SET resumo = 'Outra coisa' WHERE id = ?", (acao["id"],)
        )
    )
    with pytest.raises(acoes.ErroAcao) as erro:
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA)
    assert erro.value.codigo == "eden_acao_assinatura"


def test_weird_block_does_not_break_the_others(store):
    resposta = _bloco({"tipo": "tarefa.concluir", "id": "\u00b2"}) + _bloco(
        {"tipo": "memoria.criar", "texto": "ok"}
    )
    criadas, recusadas = acoes.propor(resposta, store, "pessoal", TZ, None, AGORA)
    assert len(criadas) == 1 and len(recusadas) == 1


# ── limpeza automática (90 dias) ─────────────────────────────────────────

DIA_MS = 24 * 3600 * 1000


def _acao_antiga(
    store, acao_id, criado_em, estado="feita", expira_em=None, decidido_em=None
):
    if expira_em is None:
        expira_em = criado_em + 15 * 60 * 1000
    store.transacao(
        lambda c: c.execute(
            "INSERT INTO acoes (id, tipo, parametros, assinatura, resumo, "
            "conversa_id, estado, criado_em, expira_em, decidido_em) "
            "VALUES (?, 'memoria.criar', '{}', 'x', 'r', NULL, ?, ?, ?, ?)",
            (acao_id, estado, criado_em, expira_em, decidido_em),
        )
    )


def _registro(store, quando):
    store.transacao(
        lambda c: c.execute(
            "INSERT INTO registro (quando, quem, o_que, alvo) "
            "VALUES (?, 'pessoa', 'criou', 'tarefa')",
            (quando,),
        )
    )


def test_cleanup_removes_only_old_cards_and_log_lines(store):
    agora = AGORA
    _acao_antiga(store, "velha", agora - 91 * DIA_MS)
    _acao_antiga(store, "recente", agora - 89 * DIA_MS)
    # Pendente vencida sai; pendente que ainda vale fica (mesmo velha).
    _acao_antiga(store, "pendente-velha", agora - 200 * DIA_MS, estado="pendente")
    _acao_antiga(
        store,
        "pendente-valendo",
        agora - 200 * DIA_MS,
        estado="pendente",
        expira_em=agora + 60_000,
    )
    _registro(store, agora - 120 * DIA_MS)
    _registro(store, agora - 10 * DIA_MS)
    tarefa = store.criar_tarefa({"titulo": "Fica", "espaco": "pessoal"}, TZ)
    memoria = store.criar_memoria("fica também")

    apagados = store.limpar_antigos(agora, 90)

    assert apagados == {"acoes": 2, "registro": 1, "presas": 0}
    restantes = {r["id"] for r in store._ler("SELECT id FROM acoes")}
    assert restantes == {"recente", "pendente-valendo"}
    antigas = store._ler("SELECT id FROM registro WHERE quando < ?", (agora - DIA_MS,))
    assert len(antigas) == 1
    # Tarefas e memórias não são tocadas.
    assert store.tarefa(tarefa["id"]) is not None
    assert any(m["id"] == memoria["id"] for m in store.listar_memorias(todas=True))
    assert store.ultima_limpeza() == agora


def test_cards_stuck_while_talking_to_google_become_failed(store):
    agora = AGORA
    _acao_antiga(
        store,
        "presa-0001",
        agora - DIA_MS,
        estado="executando",
        decidido_em=agora - DIA_MS,
    )
    _acao_antiga(
        store,
        "no-ar-0001",
        agora - 60_000,
        estado="executando",
        decidido_em=agora - 60_000,
    )
    apagados = store.limpar_antigos(agora, 90)
    assert apagados["presas"] == 1
    assert store.acao("presa-0001")["estado"] == "falhou"
    assert "confira na agenda" in store.acao("presa-0001")["resultado"]["erro"]
    assert store.acao("no-ar-0001")["estado"] == "executando"
    # Ao ligar o servidor: nenhuma chamada está no ar, então fecha todas.
    assert store.fechar_presas(agora + 1) == 1
    assert store.acao("no-ar-0001")["estado"] == "falhou"


def test_cleanup_rejects_zero_days(store):
    with pytest.raises(ValueError):
        store.limpar_antigos(AGORA, 0)


def test_tampered_card_in_the_database_does_not_run(store, tmp_path):
    """Rodada final (18/10): a assinatura usa a chave do servidor (acoes.key,
    fora do backup); uma linha mexida no banco não vira outra ação."""
    tarefa = store.criar_tarefa({"titulo": "Não apagar", "espaco": "pessoal"}, TZ)
    criadas, _ = acoes.propor(
        _bloco({"tipo": "nota.criar", "texto": "lista de compras"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    [acao] = criadas
    assert (tmp_path / "acoes.key").stat().st_mode & 0o077 == 0
    params = {"id": tarefa["id"], "titulo": "Não apagar"}
    falsa = acoes.assinatura("tarefa.apagar", params, acao["resumo"])
    store.transacao(
        lambda c: c.execute(
            "UPDATE acoes SET tipo = 'tarefa.apagar', parametros = ?, assinatura = ? "
            "WHERE id = ?",
            (json.dumps(params, sort_keys=True), falsa, acao["id"]),
        )
    )
    with pytest.raises(acoes.ErroAcao):
        acoes.confirmar(store, acao["id"], falsa, TZ, AGORA + 1000)
    assert store.tarefa(tarefa["id"]) is not None


def test_edit_card_shows_the_space_move_before_long_notes(store):
    tarefa = store.criar_tarefa({"titulo": "Relatório", "espaco": "pessoal"}, TZ)
    [acao], _ = acoes.propor(
        _bloco(
            {
                "tipo": "tarefa.editar",
                "id": tarefa["id"],
                "notas": "oi" + "\n" * 60 + "fim",
                "espaco": "clientes",
            }
        ),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    assert acao["resumo"].startswith("Mudar a tarefa “Relatório”: mover para Clientes")
    assert "\n\n\n" not in acao["resumo"]
    assert acao["parametros"]["mudancas"]["notas"] == "oi\n\nfim"


def test_card_is_void_if_the_task_changed_in_any_field(store):
    """Revisão do Codex (18/10): mudar a hora em outro aparelho invalida o
    cartão (antes só o título era conferido)."""
    tarefa = store.criar_tarefa(
        {
            "titulo": "Dentista",
            "espaco": "pessoal",
            "data": "2026-10-20",
            "hora": "10:00",
        },
        TZ,
    )
    [acao], _ = acoes.propor(
        _bloco({"tipo": "tarefa.editar", "id": tarefa["id"], "notas": "levar exame"}),
        store,
        "pessoal",
        TZ,
        None,
        AGORA,
    )
    store.atualizar_tarefa(tarefa["id"], {"hora": "23:00"}, TZ)
    with pytest.raises((ErroOrganizacao, acoes.ErroAcao)):
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 1000)
    assert store.tarefa(tarefa["id"])["notas"] == ""


def test_stretched_expiry_in_the_database_does_not_pass(store):
    [acao], _ = acoes.propor(
        _bloco({"tipo": "nota.criar", "texto": "x"}), store, "pessoal", TZ, None, AGORA
    )
    store.transacao(
        lambda c: c.execute(
            "UPDATE acoes SET expira_em = ? WHERE id = ?",
            (AGORA + 10 * acoes.VALIDADE_MS, acao["id"]),
        )
    )
    with pytest.raises(acoes.ErroAcao):
        acoes.confirmar(
            store, acao["id"], acao["assinatura"], TZ, AGORA + 2 * acoes.VALIDADE_MS
        )
