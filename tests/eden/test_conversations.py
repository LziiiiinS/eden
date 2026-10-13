"""Éden: testes do armazenamento de conversas no servidor."""

import pytest

from openjarvis.eden.conversations import (
    ConversationStore,
    ConversationValidationError,
    validate_conversation,
)


def _conv(conv_id="c1", updated=1000, messages=None, title="Teste"):
    return {
        "id": conv_id,
        "title": title,
        "model": "gpt-teste",
        "createdAt": 900,
        "updatedAt": updated,
        "messages": messages
        if messages is not None
        else [
            {"id": "m1", "role": "user", "content": "Oi", "timestamp": 950},
            {"id": "m2", "role": "assistant", "content": "Olá!", "timestamp": 960},
        ],
    }


@pytest.fixture
def store(tmp_path):
    s = ConversationStore(tmp_path / "conv.db")
    yield s
    s.close()


def _save(store, raw):
    return store.upsert_conversation(validate_conversation(raw["id"], raw))


def test_save_and_read_back(store):
    meta = _save(store, _conv())
    assert meta["updatedAt"] == 1000
    conv = store.get_conversation("c1")
    assert [m["content"] for m in conv["messages"]] == ["Oi", "Olá!"]
    assert conv["title"] == "Teste"


def test_same_push_twice_does_not_duplicate(store):
    _save(store, _conv())
    _save(store, _conv())
    assert len(store.get_conversation("c1")["messages"]) == 2


def test_newer_version_updates_message_content(store):
    _save(store, _conv())
    newer = _conv(updated=2000)
    newer["messages"][1]["content"] = "Olá, tudo bem?"
    _save(store, newer)
    assert store.get_conversation("c1")["messages"][1]["content"] == "Olá, tudo bem?"


def test_older_version_does_not_overwrite(store):
    newer = _conv(updated=2000, title="Novo")
    newer["messages"][1]["content"] = "Versão nova"
    _save(store, newer)
    _save(store, _conv(updated=1000, title="Velho"))
    conv = store.get_conversation("c1")
    assert conv["title"] == "Novo"
    assert conv["messages"][1]["content"] == "Versão nova"


def test_offline_device_messages_are_merged_and_version_bumped(store):
    _save(store, _conv(updated=2000))
    offline = _conv(updated=1500)
    offline["messages"].append(
        {"id": "m3", "role": "user", "content": "Sem internet", "timestamp": 1400}
    )
    meta = _save(store, offline)
    assert meta["updatedAt"] == 2001  # avança para os outros aparelhos buscarem
    ids = [m["id"] for m in store.get_conversation("c1")["messages"]]
    assert ids == ["m1", "m2", "m3"]


def test_delete_removes_content_and_leaves_tombstone(store):
    _save(store, _conv())
    meta = store.delete_conversation("c1", 3000)
    assert meta["deleted"] is True
    conv = store.get_conversation("c1")
    assert conv["messages"] == []
    assert conv["title"] == ""
    assert store.list_conversations()[0]["deleted"] is True


def test_old_push_after_delete_does_not_resurrect(store):
    _save(store, _conv())
    store.delete_conversation("c1", 3000)
    meta = _save(store, _conv(updated=2000))
    assert meta["deleted"] is True
    assert store.get_conversation("c1")["messages"] == []


def test_delete_older_than_last_edit_is_ignored(store):
    _save(store, _conv(updated=5000))
    meta = store.delete_conversation("c1", 3000)
    assert meta["deleted"] is False
    assert len(store.get_conversation("c1")["messages"]) == 2


def test_extra_fields_round_trip(store):
    raw = _conv()
    raw["messages"][1]["usage"] = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    raw["messages"][1]["unknownField"] = "não guardar"
    _save(store, raw)
    msg = store.get_conversation("c1")["messages"][1]
    assert msg["usage"]["total_tokens"] == 3
    assert "unknownField" not in msg


def test_users_are_isolated(store):
    store.upsert_conversation(validate_conversation("c1", _conv()), user_id="a")
    assert store.get_conversation("c1", user_id="b") is None
    assert store.list_conversations(user_id="b") == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(id="outro"),
        lambda c: c.update(updatedAt="ontem"),
        lambda c: c.update(updatedAt=True),
        lambda c: c.update(messages="não é lista"),
        lambda c: c["messages"][0].update(id="id com espaço"),
        lambda c: c["messages"][0].update(role="system"),
        lambda c: c["messages"][0].update(content=123),
    ],
)
def test_invalid_payloads_are_rejected(mutate):
    raw = _conv()
    mutate(raw)
    with pytest.raises(ConversationValidationError):
        validate_conversation("c1", raw)


def test_invalid_conversation_id_rejected():
    with pytest.raises(ConversationValidationError):
        validate_conversation("../etc", _conv(conv_id="../etc"))


def test_server_reports_messages_the_device_lacks(store):
    other_device = _conv(updated=1000)
    other_device["messages"].append(
        {"id": "m9", "role": "user", "content": "Do notebook", "timestamp": 970}
    )
    _save(store, other_device)
    phone = _conv(updated=1100)  # não tem a m9
    meta = _save(store, phone)
    assert meta["serverHasMore"] is True
    again = _save(store, other_device | {"updatedAt": 1200})
    assert again["serverHasMore"] is False
