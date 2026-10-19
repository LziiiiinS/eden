"""Éden: a lista de sugestões filtra por conversa e por espaço (fictício)."""

import json

from openjarvis.eden.organizacao import Organizacao, agora_ms


def _sugestao(store, acao_id, conversa, espaco):
    agora = agora_ms()

    def fazer(conn):
        conn.execute(
            "INSERT INTO acoes (id, tipo, parametros, assinatura, resumo, "
            "conversa_id, estado, criado_em, expira_em) "
            "VALUES (?, 'tarefa.criar', ?, 'x', 'resumo', ?, 'pendente', ?, ?)",
            (acao_id, json.dumps({"espaco": espaco}), conversa, agora, agora + 60_000),
        )

    store.transacao(fazer)


def test_filters(tmp_path):
    store = Organizacao(tmp_path / "organizacao.db")
    _sugestao(store, "acao-pessoal-1", "c1", "pessoal")
    _sugestao(store, "acao-trabalho1", "c2", "ls-visuals")
    _sugestao(store, "acao-pessoal-2", "c2", "pessoal")
    try:
        assert len(store.listar_acoes()) == 3
        assert {a["id"] for a in store.listar_acoes(conversa="c2")} == {
            "acao-trabalho1",
            "acao-pessoal-2",
        }
        assert {a["id"] for a in store.listar_acoes(espaco="pessoal")} == {
            "acao-pessoal-1",
            "acao-pessoal-2",
        }
        assert [
            a["id"] for a in store.listar_acoes(conversa="c2", espaco="ls-visuals")
        ] == ["acao-trabalho1"]
        assert store.listar_acoes(conversa="nenhuma") == []
    finally:
        store.close()
