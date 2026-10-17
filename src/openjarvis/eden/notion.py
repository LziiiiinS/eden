"""Éden (Parte 4): Notion pela conexão interna da pessoa.

O que faz:
- **Trazer uma página do Notion** para os documentos do Éden (só o texto,
  em markdown). Depois a pessoa marca "Usar aqui" na conversa, como um PDF.
- **Salvar uma folha do Éden no Notion**, como página nova dentro da página
  que a pessoa escolheu ("página do Éden"). Só quando a pessoa toca no botão.

Segurança:
- A chave (NOTION_API_KEY) fica só no .env do servidor; o app nunca recebe.
- A conexão só enxerga as páginas que a pessoa compartilhar com ela no
  Notion. Pedimos só "Ler conteúdo" e "Inserir conteúdo" (sem "Atualizar"):
  o Éden não muda nem apaga nada que já existe.
- O texto trazido do Notion é dado, nunca ordem (vai para o contexto pelo
  mesmo caminho "desarmado" dos documentos).
- Só fala com api.notion.com, em caminhos fixos; IDs conferidos.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao

logger = logging.getLogger(__name__)

HOST = "api.notion.com"
VERSAO = "2026-03-11"
URL_BUSCA = f"https://{HOST}/v1/search"
URL_PAGINA = f"https://{HOST}/v1/pages/{{id}}"
URL_MARKDOWN = f"https://{HOST}/v1/pages/{{id}}/markdown"
URL_CRIAR = f"https://{HOST}/v1/pages"
FONTE = "Notion"

AJUSTE_PAI = "notion_pagina_pai"
TEMPO_LIMITE_S = 15.0
TEMPO_TOTAL_S = 30.0
MAX_RESPOSTA = 4 * 1024 * 1024
MAX_BUSCA = 100
MAX_RESULTADOS = 20
MAX_TITULO = 200
MAX_SALVAR = 100_000  # caracteres de markdown por página salva

_CHAVE = re.compile(r"(?:ntn_|secret_)[A-Za-z0-9]{20,80}")
_ID = re.compile(
    r"([0-9a-f]{8})-?([0-9a-f]{4})-?([0-9a-f]{4})-?([0-9a-f]{4})-?([0-9a-f]{12})"
)
_HOSTS_LINK = ("notion.so", "notion.site")


class ErroNotion(Exception):
    def __init__(self, mensagem: str, codigo: str = "eden_notion") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


class _Passageiro(Exception):
    """Falha de rede ou erro 5xx: vale tentar de novo uma vez."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


# ── chave e IDs ──────────────────────────────────────────────────────────


def chave() -> Optional[str]:
    valor = (os.environ.get("NOTION_API_KEY") or "").strip()
    if not valor:
        return None
    if not _CHAVE.fullmatch(valor):
        logger.warning("Éden: NOTION_API_KEY com formato estranho; Notion desligado")
        return None
    return valor


def configurado() -> bool:
    return chave() is not None


def id_da_pagina(valor: Any) -> str:
    """ID do Notion (com ou sem traços, ou o fim de um link) → formato com
    traços, minúsculo."""
    if not isinstance(valor, str):
        raise ErroOrganizacao("página do Notion inválida")
    texto = valor.strip().lower()
    if len(texto) > 400:
        raise ErroOrganizacao("página do Notion inválida")
    achado = None
    for achado in _ID.finditer(texto):
        pass
    if achado is None:
        raise ErroOrganizacao("página do Notion inválida")
    return "-".join(achado.groups())


def _link_ok(valor: Any) -> Optional[str]:
    if not isinstance(valor, str) or len(valor) > 500:
        return None
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or "@" in partes.netloc:
        return None
    if not any(host == h or host.endswith("." + h) for h in _HOSTS_LINK):
        return None
    return valor


def _texto_externo(valor: Any, maximo: int) -> str:
    from openjarvis.eden.google import limpar_externo

    return limpar_externo(valor, maximo)


def titulo_da_pagina(pagina: Dict[str, Any]) -> str:
    props = pagina.get("properties")
    if isinstance(props, dict):
        for prop in props.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                partes = prop.get("title") or []
                texto = "".join(
                    p.get("plain_text", "")
                    for p in partes
                    if isinstance(p, dict) and isinstance(p.get("plain_text"), str)
                )
                return _texto_externo(texto, MAX_TITULO) or "Sem título"
    return "Sem título"


def _resumo_pagina(pagina: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(pagina, dict) or pagina.get("object") != "page":
        return None
    if pagina.get("in_trash") or pagina.get("archived"):
        return None
    try:
        pid = id_da_pagina(pagina.get("id"))
    except ErroOrganizacao:
        return None
    editado = pagina.get("last_edited_time")
    return {
        "id": pid,
        "titulo": titulo_da_pagina(pagina),
        "link": _link_ok(pagina.get("url")),
        "editado_em": editado
        if isinstance(editado, str) and len(editado) <= 40
        else None,
    }


# ── página do Éden (onde salvar) ─────────────────────────────────────────


def pagina_pai(store: Organizacao) -> Optional[Dict[str, str]]:
    rows = store._ler("SELECT valor FROM ajustes WHERE chave = ?", (AJUSTE_PAI,))
    if not rows:
        return None
    try:
        dados = json.loads(rows[0][0])
        return {
            "id": id_da_pagina(dados["id"]),
            "titulo": str(dados["titulo"])[:MAX_TITULO],
        }
    except (ValueError, KeyError, TypeError, ErroOrganizacao):
        return None


def guardar_pai(store: Organizacao, pagina: Optional[Dict[str, str]]) -> None:
    if pagina is None:
        store.transacao(
            lambda c: c.execute("DELETE FROM ajustes WHERE chave = ?", (AJUSTE_PAI,))
        )
        return
    valor = json.dumps(
        {"id": pagina["id"], "titulo": pagina["titulo"]}, ensure_ascii=False
    )
    store.transacao(
        lambda c: c.execute(
            "INSERT INTO ajustes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (AJUSTE_PAI, valor),
        )
    )


# ── texto que vai para o Notion ──────────────────────────────────────────

_IMAGEM = re.compile(r"!\[([^\]\n]{0,300})\]\([^)\n]{0,2000}\)")


def markdown_para_salvar(texto: Any) -> str:
    """Folha do Éden → markdown para o Notion.

    - imagens viram só o texto alternativo (nada é baixado de fora);
    - fora de blocos de código, "<" vira "‹": o markdown do Notion entende
      marcações como <page url="..."> e <mention-...>, que poderiam ligar ou
      mover páginas que já existem."""
    if not isinstance(texto, str):
        raise ErroOrganizacao("faltou o texto da folha")
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if not texto.strip():
        raise ErroOrganizacao("a folha está vazia")
    if len(texto) > MAX_SALVAR:
        raise ErroOrganizacao("a folha é grande demais para salvar no Notion", 413)
    texto = _IMAGEM.sub(lambda m: m.group(1), texto)
    linhas = []
    em_codigo = False
    for linha in texto.split("\n"):
        if linha.lstrip().startswith(("```", "~~~")):
            em_codigo = not em_codigo
            linhas.append(linha)
            continue
        linhas.append(linha if em_codigo else linha.replace("<", "‹"))
    return "\n".join(linhas)


def titulo_para_salvar(valor: Any) -> str:
    titulo = _texto_externo(valor if isinstance(valor, str) else "", MAX_TITULO)
    titulo = titulo.replace("\n", " ").strip()
    if not titulo:
        raise ErroOrganizacao("a folha precisa de um título")
    return titulo


# ── cliente ──────────────────────────────────────────────────────────────


class ClienteNotion:
    """Só fala com api.notion.com, nos caminhos fixos acima."""

    def __init__(self, http: Any = None) -> None:
        self._http = http

    def _cliente_http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=TEMPO_LIMITE_S, follow_redirects=False)
        return self._http

    def _pedir(
        self, metodo: str, url: str, corpo: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not url.startswith(f"https://{HOST}/v1/"):
            raise ErroNotion("endereço não permitido")
        k = chave()
        if k is None:
            raise ErroNotion(
                "O Notion ainda não foi configurado (falta a NOTION_API_KEY no .env).",
                "eden_notion_sem_chave",
            )
        # Só leitura repete; criar página não (poderia duplicar).
        tentativas = (1, 2) if metodo == "GET" or url == URL_BUSCA else (1,)
        for tentativa in tentativas:
            try:
                return self._pedir_uma_vez(metodo, url, corpo, k)
            except _Passageiro as exc:
                logger.warning(
                    "Éden: Notion sem resposta (%s, tentativa %d)",
                    exc.motivo,
                    tentativa,
                )
                if tentativa == tentativas[-1]:
                    raise ErroNotion(
                        "Sem resposta do Notion agora. Tente de novo."
                        + (
                            ""
                            if metodo == "GET" or url == URL_BUSCA
                            else " Antes, confira no Notion se a página já não"
                            " foi criada."
                        ),
                        "eden_notion_rede",
                    ) from None
                time.sleep(1)
        raise ErroNotion("Sem resposta do Notion agora.")  # pragma: no cover

    def _pedir_uma_vez(
        self, metodo: str, url: str, corpo: Optional[Dict[str, Any]], k: str
    ) -> Dict[str, Any]:
        inicio = time.monotonic()
        cabecalhos = {
            "Authorization": f"Bearer {k}",
            "Notion-Version": VERSAO,
            "Accept-Encoding": "identity",
        }
        extra: Dict[str, Any] = {}
        if corpo is not None:
            extra["json"] = corpo
        try:
            with self._cliente_http().stream(
                metodo, url, headers=cabecalhos, **extra
            ) as resposta:
                status = resposta.status_code
                if status >= 500:
                    raise _Passageiro(f"erro {status}")
                if status == 401:
                    raise ErroNotion(
                        "O Notion recusou a chave (confira a NOTION_API_KEY no .env).",
                        "eden_notion_chave",
                    )
                if status == 403:
                    raise ErroNotion(
                        "A conexão do Éden no Notion não tem permissão para isso "
                        '(confira se "Ler conteúdo" e "Inserir conteúdo" estão '
                        "marcados).",
                        "eden_notion_permissao",
                    )
                if status == 404:
                    raise ErroNotion(
                        "Página não encontrada. No Notion, abra a página → ••• → "
                        "Conexões e adicione a conexão do Éden.",
                        "eden_notion_404",
                    )
                if status == 429:
                    raise ErroNotion(
                        "O Notion pediu para esperar um pouco. Tente de novo.",
                        "eden_notion_limite",
                    )
                if status != 200:
                    raise ErroNotion(
                        f"O Notion recusou o pedido ({status}).", "eden_notion_recusa"
                    )
                pedacos = []
                tamanho = 0
                for pedaco in resposta.iter_bytes():
                    tamanho += len(pedaco)
                    if tamanho > MAX_RESPOSTA:
                        raise ErroNotion("A página do Notion é grande demais.")
                    if time.monotonic() - inicio > TEMPO_TOTAL_S:
                        raise _Passageiro("demorou demais")
                    pedacos.append(pedaco)
        except (ErroNotion, _Passageiro):
            raise
        except Exception as exc:  # noqa: BLE001 - rede; nunca mostra cabeçalhos
            raise _Passageiro(type(exc).__name__) from None
        try:
            dados = json.loads(b"".join(pedacos))
        except (ValueError, RecursionError):
            raise ErroNotion("Resposta estranha do Notion.") from None
        if not isinstance(dados, dict):
            raise ErroNotion("Resposta estranha do Notion.")
        return dados

    # ── operações ────────────────────────────────────────────────────────

    def buscar(self, consulta: Any) -> List[Dict[str, Any]]:
        """Páginas que a conexão enxerga (as mais recentes primeiro)."""
        texto = consulta if isinstance(consulta, str) else ""
        texto = _texto_externo(texto, MAX_BUSCA).replace("\n", " ").strip()
        corpo: Dict[str, Any] = {
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": MAX_RESULTADOS,
        }
        if texto:
            corpo["query"] = texto
        dados = self._pedir("POST", URL_BUSCA, corpo)
        resultados = []
        for item in dados.get("results") or []:
            resumo = _resumo_pagina(item)
            if resumo is not None:
                resultados.append(resumo)
        return resultados[:MAX_RESULTADOS]

    def pagina(self, page_id: Any) -> Dict[str, Any]:
        pid = id_da_pagina(page_id)
        resumo = _resumo_pagina(self._pedir("GET", URL_PAGINA.format(id=pid)))
        if resumo is None:
            raise ErroNotion(
                "Essa página está na lixeira do Notion.", "eden_notion_404"
            )
        return resumo

    def markdown(self, page_id: Any) -> Dict[str, Any]:
        pid = id_da_pagina(page_id)
        dados = self._pedir("GET", URL_MARKDOWN.format(id=pid))
        texto = dados.get("markdown")
        if not isinstance(texto, str):
            raise ErroNotion("Resposta estranha do Notion.")
        return {"markdown": texto, "truncado": bool(dados.get("truncated"))}

    def criar(self, pai_id: str, titulo: str, markdown: str) -> Dict[str, Any]:
        corpo = {
            "parent": {"page_id": id_da_pagina(pai_id)},
            "properties": {"title": {"title": [{"text": {"content": titulo}}]}},
            "markdown": markdown,
        }
        resumo = _resumo_pagina(self._pedir("POST", URL_CRIAR, corpo))
        if resumo is None:
            raise ErroNotion("O Notion não confirmou a página criada.")
        return resumo


def cliente_do_app(app) -> ClienteNotion:  # noqa: ANN001
    atual = getattr(app.state, "eden_notion", None)
    if atual is None:
        atual = ClienteNotion()
        app.state.eden_notion = atual
    return atual


# ── ações de alto nível ──────────────────────────────────────────────────


def escolher_pai(
    store: Organizacao, cliente: ClienteNotion, page_id: Any
) -> Dict[str, str]:
    """Confere no Notion que a conexão enxerga a página e guarda como a
    página onde o Éden salva."""
    resumo = cliente.pagina(page_id)
    pai = {"id": resumo["id"], "titulo": resumo["titulo"]}
    guardar_pai(store, pai)
    return pai


def importar(
    store: Organizacao, cliente: ClienteNotion, espaco: str, page_id: Any
) -> Dict[str, Any]:
    """Traz o texto da página para os documentos do espaço."""
    from openjarvis.eden import documentos

    resumo = cliente.pagina(page_id)
    conteudo = cliente.markdown(resumo["id"])
    texto = conteudo["markdown"]
    bruto = texto.encode("utf-8")
    nome = documentos.limpar_nome(f"{resumo['titulo'][:100]} (Notion).md")
    doc = documentos.guardar(
        store,
        espaco,
        nome,
        "md",
        len(bruto),
        hashlib.sha256(b"notion:" + resumo["id"].encode() + b"\n" + bruto).hexdigest(),
        texto,
        None,
    )
    if conteudo["truncado"]:
        doc = {**doc, "aviso": "A página é grande: o Notion mandou só uma parte."}
    return doc


def salvar(
    store: Organizacao, cliente: ClienteNotion, titulo: Any, texto: Any
) -> Dict[str, Any]:
    pai = pagina_pai(store)
    if pai is None:
        raise ErroNotion(
            "Escolha antes a página do Notion onde o Éden salva "
            "(Configurações → Notion).",
            "eden_notion_sem_pai",
        )
    return cliente.criar(
        pai["id"], titulo_para_salvar(titulo), markdown_para_salvar(texto)
    )
