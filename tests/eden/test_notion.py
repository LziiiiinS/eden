"""Éden: Notion (Notion falso; nada sai para a internet)."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import pytest

from openjarvis.eden import documentos, notion
from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao

CHAVE = "ntn_" + "a1B2c3D4e5" * 4
PAI = "11111111-2222-3333-4444-555555555555"
OUTRA = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class Resposta:
    def __init__(self, status: int, dados=None, bruto: bytes = None) -> None:
        self.status_code = status
        self.content = bruto if bruto is not None else json.dumps(dados or {}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self):
        yield self.content


def pagina(pid, titulo, lixo=False):
    return {
        "object": "page",
        "id": pid,
        "url": "https://www.notion.so/"
        + titulo.replace(" ", "-")
        + "-"
        + pid.replace("-", ""),
        "in_trash": lixo,
        "last_edited_time": "2026-10-17T12:00:00.000Z",
        "properties": {
            "title": {
                "type": "title",
                "title": [{"plain_text": titulo}],
            }
        },
    }


class NotionFalso:
    def __init__(self) -> None:
        self.pedidos = []
        self.status = {}
        self.markdown = "# Reunião\n\n- item 1\n- item 2"
        self.truncado = False

    def stream(self, metodo, url, headers=None, json=None):
        assert urlparse(url).hostname == "api.notion.com", url
        assert headers["Authorization"] == f"Bearer {CHAVE}"
        assert headers["Notion-Version"] == notion.VERSAO
        self.pedidos.append((metodo, url, json))
        caminho = urlparse(url).path
        if caminho in self.status:
            return Resposta(self.status[caminho], {"message": "erro"})
        if metodo == "POST" and caminho == "/v1/search":
            return Resposta(
                200,
                {
                    "results": [
                        pagina(PAI, "Éden"),
                        pagina(OUTRA, "Velha", lixo=True),
                        {"object": "data_source", "id": OUTRA},
                        pagina("não é id", "Ruim"),
                    ]
                },
            )
        if metodo == "GET" and caminho.endswith("/markdown"):
            return Resposta(
                200,
                {
                    "object": "page_markdown",
                    "markdown": self.markdown,
                    "truncated": self.truncado,
                },
            )
        if metodo == "GET" and caminho.startswith("/v1/pages/"):
            return Resposta(
                200, pagina(caminho.rsplit("/", 1)[1], "Reunião de segunda")
            )
        if metodo == "POST" and caminho == "/v1/pages":
            return Resposta(
                200,
                pagina(
                    OUTRA, json["properties"]["title"]["title"][0]["text"]["content"]
                ),
            )
        return Resposta(404)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", CHAVE)
    store = Organizacao(tmp_path / "organizacao.db")
    falso = NotionFalso()
    yield store, notion.ClienteNotion(http=falso), falso
    store.close()


# ── chave e IDs ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "valor, ok",
    [
        (CHAVE, True),
        ("secret_" + "x" * 43, True),
        ("", False),
        ("ntn_curta", False),
        ("sk-ant-" + "x" * 40, False),
        (CHAVE + " extra", False),
    ],
)
def test_key_format(monkeypatch, valor, ok):
    monkeypatch.setenv("NOTION_API_KEY", valor)
    assert notion.configurado() is ok


def test_without_key_nothing_is_called(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    falso = NotionFalso()
    with pytest.raises(notion.ErroNotion) as exc:
        notion.ClienteNotion(http=falso).buscar("x")
    assert exc.value.codigo == "eden_notion_sem_chave"
    assert falso.pedidos == []


@pytest.mark.parametrize(
    "valor",
    [
        PAI,
        PAI.replace("-", ""),
        PAI.upper(),
        f"https://www.notion.so/Minha-pagina-{PAI.replace('-', '')}",
    ],
)
def test_page_ids(valor):
    assert notion.id_da_pagina(valor) == PAI


@pytest.mark.parametrize("valor", [None, "", "abc", "../../v1/users", "1" * 500, 123])
def test_bad_page_ids(valor):
    with pytest.raises(ErroOrganizacao):
        notion.id_da_pagina(valor)


# ── busca, leitura, página do Éden ───────────────────────────────────────


def test_search_lists_only_live_pages(ambiente):
    _, cliente, falso = ambiente
    resultados = cliente.buscar("  reunião\n ")
    assert [r["titulo"] for r in resultados] == ["Éden"]
    assert resultados[0]["id"] == PAI
    assert resultados[0]["link"].startswith("https://www.notion.so/")
    metodo, url, corpo = falso.pedidos[0]
    assert (metodo, url) == ("POST", notion.URL_BUSCA)
    assert corpo["filter"] == {"property": "object", "value": "page"}
    assert corpo["query"] == "reunião"


def test_empty_search_lists_recent(ambiente):
    _, cliente, falso = ambiente
    cliente.buscar("")
    assert "query" not in falso.pedidos[0][2]


def test_choose_parent_checks_access_and_saves(ambiente):
    store, cliente, falso = ambiente
    assert notion.pagina_pai(store) is None
    pai = notion.escolher_pai(store, cliente, PAI.replace("-", ""))
    assert pai == {"id": PAI, "titulo": "Reunião de segunda"}
    assert notion.pagina_pai(store) == pai
    assert falso.pedidos[-1][:2] == ("GET", notion.URL_PAGINA.format(id=PAI))
    notion.guardar_pai(store, None)
    assert notion.pagina_pai(store) is None


def test_choose_parent_not_shared(ambiente):
    store, cliente, falso = ambiente
    falso.status[f"/v1/pages/{PAI}"] = 404
    with pytest.raises(notion.ErroNotion) as exc:
        notion.escolher_pai(store, cliente, PAI)
    assert exc.value.codigo == "eden_notion_404"
    assert "Conexões" in str(exc.value)
    assert notion.pagina_pai(store) is None


def test_import_page_becomes_a_document(ambiente):
    store, cliente, falso = ambiente
    doc = notion.importar(store, cliente, "pessoal", PAI)
    assert doc["nome"] == "Reunião de segunda (Notion).md"
    assert doc["espaco"] == "pessoal"
    texto = documentos.documento(store, doc["id"])
    assert texto is not None
    # Importar de novo a mesma página igual não duplica.
    de_novo = notion.importar(store, cliente, "pessoal", PAI)
    assert de_novo["id"] == doc["id"]
    assert len(documentos.listar(store, "pessoal")) == 1


def test_import_truncated_page_warns(ambiente):
    store, cliente, falso = ambiente
    falso.truncado = True
    doc = notion.importar(store, cliente, "pessoal", PAI)
    assert "só uma parte" in doc["aviso"]


def test_import_unknown_space(ambiente):
    store, cliente, _ = ambiente
    with pytest.raises(ErroOrganizacao):
        notion.importar(store, cliente, "nao-existe", PAI)


# ── salvar ───────────────────────────────────────────────────────────────


def test_save_needs_a_parent(ambiente):
    store, cliente, falso = ambiente
    with pytest.raises(notion.ErroNotion) as exc:
        notion.salvar(store, cliente, "Plano", "# Plano")
    assert exc.value.codigo == "eden_notion_sem_pai"
    assert falso.pedidos == []


def test_save_creates_page_under_parent(ambiente):
    store, cliente, falso = ambiente
    notion.guardar_pai(store, {"id": PAI, "titulo": "Éden"})
    texto = (
        "# Plano\n\nVeja ![foto](https://evil.example/x.png?d=segredo)\n"
        '<page url="https://www.notion.so/outra">Outra</page>\n'
        "```html\n<b>código</b>\n```\n"
    )
    pagina_criada = notion.salvar(store, cliente, "Plano da semana", texto)
    assert pagina_criada["titulo"] == "Plano da semana"
    metodo, url, corpo = falso.pedidos[-1]
    assert (metodo, url) == ("POST", notion.URL_CRIAR)
    assert corpo["parent"] == {"page_id": PAI}
    md = corpo["markdown"]
    assert "evil.example" not in md and "Veja foto" in md
    assert '‹page url="https://www.notion.so/outra">Outra‹/page>' in md
    # Até dentro de bloco de código o "<" vira "‹" (sem brecha pela cerca).
    assert "‹b>código‹/b>" in md and "<" not in md


def test_save_is_not_retried(ambiente):
    store, cliente, falso = ambiente
    notion.guardar_pai(store, {"id": PAI, "titulo": "Éden"})
    falso.status["/v1/pages"] = 502
    with pytest.raises(notion.ErroNotion) as exc:
        notion.salvar(store, cliente, "Plano", "# Plano")
    assert "confira no Notion" in str(exc.value)
    assert len([p for p in falso.pedidos if p[0] == "POST"]) == 1


@pytest.mark.parametrize(
    "titulo, texto",
    [
        ("", "# x"),
        ("   ", "# x"),
        ("ok", ""),
        ("ok", "   \n"),
        ("ok", None),
        ("ok", "x" * 100_001),
    ],
)
def test_save_validates(ambiente, titulo, texto):
    store, cliente, falso = ambiente
    notion.guardar_pai(store, {"id": PAI, "titulo": "Éden"})
    with pytest.raises(ErroOrganizacao):
        notion.salvar(store, cliente, titulo, texto)
    assert falso.pedidos == []


# ── erros ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status, codigo",
    [
        (401, "eden_notion_chave"),
        (403, "eden_notion_permissao"),
        (429, "eden_notion_limite"),
        (400, "eden_notion_recusa"),
        (503, "eden_notion_rede"),
    ],
)
def test_errors(ambiente, monkeypatch, status, codigo):
    _, cliente, falso = ambiente
    monkeypatch.setattr(notion.time, "sleep", lambda s: None)
    falso.status["/v1/search"] = status
    with pytest.raises(notion.ErroNotion) as exc:
        cliente.buscar("x")
    assert exc.value.codigo == codigo
    assert CHAVE not in str(exc.value)


def test_network_error_hides_details(ambiente, monkeypatch):
    _, _, _ = ambiente
    monkeypatch.setattr(notion.time, "sleep", lambda s: None)

    class Quebrado:
        def stream(self, *a, **k):
            raise RuntimeError(f"Authorization: Bearer {CHAVE}")

    with pytest.raises(notion.ErroNotion) as exc:
        notion.ClienteNotion(http=Quebrado()).buscar("x")
    assert CHAVE not in str(exc.value) and exc.value.__cause__ is None


def test_big_or_strange_answers(ambiente):
    _, cliente, falso = ambiente

    class Grande(NotionFalso):
        def stream(self, metodo, url, headers=None, json=None):
            return Resposta(200, bruto=b"x" * (notion.MAX_RESPOSTA + 1))

    with pytest.raises(notion.ErroNotion):
        notion.ClienteNotion(http=Grande()).buscar("x")

    class Estranha(NotionFalso):
        def stream(self, metodo, url, headers=None, json=None):
            return Resposta(200, bruto=b"[1, 2]")

    with pytest.raises(notion.ErroNotion):
        notion.ClienteNotion(http=Estranha()).buscar("x")


def test_only_fixed_host():
    with pytest.raises(notion.ErroNotion):
        notion.ClienteNotion(http=NotionFalso())._pedir(
            "GET", "https://evil.example/v1/x"
        )


def test_link_is_built_from_the_id(ambiente):
    _, cliente, _ = ambiente
    resumo = cliente.pagina(PAI)
    assert resumo["link"] == "https://www.notion.so/" + PAI.replace("-", "")


# ── revisão de segurança (6ª rodada) ─────────────────────────────────────

PAGINA_EXISTENTE = (
    '<page url="https://www.notion.so/' + PAI.replace("-", "") + '">P</page>'
)


@pytest.mark.parametrize(
    "texto",
    [
        "``` x ``` <mention-page url='x'/>\n" + PAGINA_EXISTENTE,
        "    ```\n" + PAGINA_EXISTENTE,
        "```\n~~~\n```\n" + PAGINA_EXISTENTE,
        "~~~\n" + PAGINA_EXISTENTE,
        '<database url="https://www.notion.so/x"/>',
        "<image source='https://evil.example/x.png'/>",
    ],
)
def test_no_notion_tag_survives(texto):
    md = notion.markdown_para_salvar(texto)
    assert "<" not in md


@pytest.mark.parametrize(
    "texto",
    [
        "![a [b] c](https://evil.example/x.png?d=1)",
        "![linha\nquebrada](https://evil.example/x.png)",
        "![" + "a" * 400 + "](https://evil.example/x.png)",
        "![a][r]\n\n[r]: https://evil.example/x.png",
        "! [a](https://evil.example/x.png)",
    ],
)
def test_no_image_form_survives(texto):
    md = notion.markdown_para_salvar(texto)
    assert "![" not in md and not re.search(r"!\s*\[", md)


def test_failure_after_create_warns_about_duplicate(ambiente):
    store, _, _ = ambiente
    notion.guardar_pai(store, {"id": PAI, "titulo": "Éden"})

    class Estranha(NotionFalso):
        def stream(self, metodo, url, headers=None, json=None):
            self.pedidos.append((metodo, url, json))
            return Resposta(200, {"object": "error"})

    falso = Estranha()
    with pytest.raises(notion.ErroNotion) as exc:
        notion.salvar(store, notion.ClienteNotion(http=falso), "Plano", "# Plano")
    assert "confira no Notion se a página já foi criada" in str(exc.value)
    assert len(falso.pedidos) == 1


def test_title_with_slash_keeps_both_parts(ambiente):
    store, cliente, falso = ambiente

    class ComBarra(NotionFalso):
        def stream(self, metodo, url, headers=None, json=None):
            if metodo == "GET" and not url.endswith("/markdown"):
                self.pedidos.append((metodo, url, json))
                return Resposta(200, pagina(PAI, "Plano A/Plano B"))
            return super().stream(metodo, url, headers, json)

    doc = notion.importar(store, notion.ClienteNotion(http=ComBarra()), "pessoal", PAI)
    assert doc["nome"] == "Plano A-Plano B (Notion).md"


def test_notion_key_is_redacted():
    from openjarvis.eden.redact import redact_secrets

    assert CHAVE not in redact_secrets(f"erro com {CHAVE} no texto")
    assert "secret_" + "x" * 43 not in redact_secrets("secret_" + "x" * 43)
