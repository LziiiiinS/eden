"""Éden: nada com cara de chave aparece em mensagens e registros."""

from openjarvis.eden.redact import redact_secrets


def test_redacts_known_key_shapes():
    text = (
        "openai sk-proj-AbCd1234EfGh5678 anthropic sk-ant-api03-xyzXYZ123 "
        "eden oj_sk_abc-DEF_123 header Bearer abc.def-123 x-api-key: segredo1"
    )
    out = redact_secrets(text)
    for secret in (
        "sk-proj-AbCd1234EfGh5678",
        "sk-ant-api03-xyzXYZ123",
        "oj_sk_abc-DEF_123",
        "abc.def-123",
        "segredo1",
    ):
        assert secret not in out
    assert "openai" in out and "anthropic" in out


def test_keeps_normal_text():
    assert redact_secrets("A chave da OpenAI foi recusada.") == (
        "A chave da OpenAI foi recusada."
    )
