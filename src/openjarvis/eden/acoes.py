"""Éden: ações propostas pelo Éden e confirmadas pela pessoa.

O Éden (a IA) nunca grava nada sozinho: ele não tem ferramentas. Quando quer
criar ou mudar algo (tarefa, memória, nota), escreve no fim da resposta um
bloco::

    ```eden-acao
    {"tipo": "tarefa.criar", "titulo": "Comprar pão", "data": "2026-10-16"}
    ```

O servidor lê a resposta inteira, confere cada bloco e cria uma **ação
pendente** com os parâmetros exatos, um resumo em português e uma assinatura
(sha256 do tipo + parâmetros). O app mostra um cartão; só quando a pessoa
toca em "Confirmar" o servidor executa — e executa o que está guardado no
servidor, não o que vier do app. Cada ação:

- vale por 15 minutos;
- só pode ser usada uma vez (a troca de "pendente" para "feita" é atômica);
- só é executada se a assinatura enviada pelo app for a mesma que o cartão
  mostrou (o cartão e a execução falam da mesma coisa).

Textos colados, e-mails, páginas e documentos são dados: um bloco que apareça
por causa deles continua precisando da confirmação da pessoa, com os
parâmetros à vista no cartão.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from openjarvis.eden.organizacao import (
    MAX_MEMORIA,
    MAX_NOTAS_TAREFA,
    MAX_TEXTO_NOTA,
    MAX_TITULO,
    TIPOS_NOTA,
    ErroOrganizacao,
    Organizacao,
    agora_ms,
    data_iso,
    hora_hhmm,
    inteiro,
    local_de_ms,
    resumo_data,
    texto,
)

VALIDADE_MS = 15 * 60 * 1000
MAX_ACOES_POR_RESPOSTA = 5
MAX_ACOES_POR_HORA = 60
MAX_BLOCO = 8000

TIPOS = (
    "memoria.criar",
    "memoria.apagar",
    "tarefa.criar",
    "tarefa.editar",
    "tarefa.concluir",
    "tarefa.apagar",
    "nota.criar",
)

_BLOCO = re.compile(r"```[ \t]*eden-acao[ \t]*\r?\n(.*?)```", re.DOTALL)
# Bloco aberto que a resposta não fechou (resposta cortada).
_BLOCO_ABERTO = re.compile(r"```[ \t]*eden-acao\b.*\Z", re.DOTALL)


class ErroAcao(Exception):
    def __init__(
        self, mensagem: str, status: int = 400, codigo: str = "eden_acao"
    ) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


@dataclass
class Proposta:
    tipo: str
    parametros: Dict[str, Any]
    resumo: str


def extrair_blocos(resposta: str) -> List[str]:
    return [m.group(1).strip() for m in _BLOCO.finditer(resposta or "")]


def remover_blocos(resposta: str) -> str:
    """Texto da resposta sem os blocos de ação (o que a pessoa vê)."""
    sem = _BLOCO.sub("", resposta or "")
    sem = _BLOCO_ABERTO.sub("", sem)
    return re.sub(r"\n{3,}", "\n\n", sem).rstrip()


def assinatura(tipo: str, parametros: Dict[str, Any]) -> str:
    canonico = json.dumps(
        parametros, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(f"{tipo}\n{canonico}".encode("utf-8")).hexdigest()


def _nome_espaco(store: Organizacao, espaco_id: Optional[str]) -> str:
    if espaco_id is None:
        return "todos os espaços"
    e = store.espaco(espaco_id)
    return e["nome"] if e else espaco_id


def _aspas(valor: str, maximo: int = 120) -> str:
    curto = " ".join(valor.split())
    if len(curto) > maximo:
        curto = curto[: maximo - 1] + "…"
    return f"“{curto}”"


def _so_campos(dados: Dict[str, Any], permitidos: Tuple[str, ...]) -> None:
    extras = set(dados) - set(permitidos) - {"tipo"}
    if extras:
        raise ErroOrganizacao(f"campos desconhecidos: {', '.join(sorted(extras))}")


def _lembrete_param(
    valor: Any, data: Optional[str], hora: Optional[str]
) -> Optional[str]:
    """Normaliza o lembrete para "AAAA-MM-DDTHH:MM" (horário do Éden) ou None."""
    if valor in (None, False):
        return None
    if valor is True:
        if not data:
            raise ErroOrganizacao("para ter lembrete, a tarefa precisa de uma data")
        return f"{data}T{hora or '09:00'}"
    if isinstance(valor, str):
        partes = valor.strip().replace(" ", "T").split("T")
        if len(partes) != 2:
            raise ErroOrganizacao("'lembrete' precisa ser AAAA-MM-DDTHH:MM")
        return f"{data_iso(partes[0], 'lembrete')}T{hora_hhmm(partes[1], 'lembrete')}"
    raise ErroOrganizacao("'lembrete' inválido")


def _texto_lembrete(valor: Optional[str], hoje: date) -> str:
    if not valor:
        return ""
    d, h = valor.split("T")
    return f" · lembrete {resumo_data(d, h, hoje)}"


def validar(
    bruto: Any,
    store: Organizacao,
    espaco_ativo: str,
    hoje: date,
) -> Proposta:
    """Confere um bloco (já lido como JSON) e devolve a proposta normalizada."""
    if not isinstance(bruto, dict):
        raise ErroOrganizacao("a ação precisa ser um objeto JSON")
    tipo = bruto.get("tipo")
    if tipo not in TIPOS:
        raise ErroOrganizacao("tipo de ação desconhecido")

    def espaco_de(campo: str = "espaco") -> str:
        valor = bruto.get(campo) or espaco_ativo
        return store.espaco_valido(valor)

    if tipo == "memoria.criar":
        _so_campos(bruto, ("texto", "espaco"))
        txt = texto(bruto.get("texto"), "texto", MAX_MEMORIA)
        valor_espaco = bruto.get("espaco", espaco_ativo)
        esp = (
            None
            if valor_espaco in ("todos", None, "")
            else store.espaco_valido(valor_espaco)
        )
        params = {"texto": txt, "espaco": esp}
        resumo = f"Guardar na memória ({_nome_espaco(store, esp)}): {_aspas(txt, 200)}"
        return Proposta(tipo, params, resumo)

    if tipo == "memoria.apagar":
        _so_campos(bruto, ("id",))
        mid = inteiro(bruto.get("id"))
        mem = store.memoria(mid)
        if mem is None:
            raise ErroOrganizacao("memória não encontrada")
        params = {"id": mid, "texto": mem["texto"]}
        return Proposta(tipo, params, f"Apagar da memória: {_aspas(mem['texto'], 200)}")

    if tipo == "tarefa.criar":
        _so_campos(bruto, ("titulo", "data", "hora", "lembrete", "notas", "espaco"))
        titulo = texto(bruto.get("titulo"), "titulo", MAX_TITULO)
        data = data_iso(bruto.get("data"))
        hora = hora_hhmm(bruto.get("hora"))
        if hora and not data:
            raise ErroOrganizacao("para ter horário, a tarefa precisa de uma data")
        notas = texto(bruto.get("notas"), "notas", MAX_NOTAS_TAREFA, obrigatorio=False)
        esp = espaco_de()
        lembrete = _lembrete_param(bruto.get("lembrete"), data, hora)
        params = {
            "titulo": titulo,
            "data": data,
            "hora": hora,
            "lembrete": lembrete,
            "notas": notas,
            "espaco": esp,
        }
        resumo = (
            f"Criar tarefa {_aspas(titulo)} em {_nome_espaco(store, esp)} — "
            f"{resumo_data(data, hora, hoje)}{_texto_lembrete(lembrete, hoje)}"
        )
        if notas:
            resumo += f" · notas: {_aspas(notas, 80)}"
        return Proposta(tipo, params, resumo)

    if tipo in ("tarefa.concluir", "tarefa.apagar"):
        _so_campos(bruto, ("id",))
        tid = inteiro(bruto.get("id"))
        tarefa = store.tarefa(tid)
        if tarefa is None:
            raise ErroOrganizacao("tarefa não encontrada")
        if tipo == "tarefa.concluir" and tarefa["feita"]:
            raise ErroOrganizacao("essa tarefa já está feita")
        params = {"id": tid, "titulo": tarefa["titulo"]}
        verbo = "Marcar como feita" if tipo == "tarefa.concluir" else "Apagar"
        resumo = (
            f"{verbo} a tarefa {_aspas(tarefa['titulo'])} "
            f"({_nome_espaco(store, tarefa['espaco'])}, "
            f"{resumo_data(tarefa['data'], tarefa['hora'], hoje)})"
        )
        return Proposta(tipo, params, resumo)

    if tipo == "tarefa.editar":
        _so_campos(
            bruto, ("id", "titulo", "data", "hora", "lembrete", "notas", "espaco")
        )
        tid = inteiro(bruto.get("id"))
        tarefa = store.tarefa(tid)
        if tarefa is None:
            raise ErroOrganizacao("tarefa não encontrada")
        mudancas: Dict[str, Any] = {}
        if "titulo" in bruto:
            mudancas["titulo"] = texto(bruto["titulo"], "titulo", MAX_TITULO)
        if "data" in bruto:
            mudancas["data"] = data_iso(bruto["data"])
        if "hora" in bruto:
            mudancas["hora"] = hora_hhmm(bruto["hora"])
        if "notas" in bruto:
            mudancas["notas"] = texto(
                bruto["notas"], "notas", MAX_NOTAS_TAREFA, obrigatorio=False
            )
        if "espaco" in bruto:
            mudancas["espaco"] = store.espaco_valido(bruto["espaco"])
        data = mudancas.get("data", tarefa["data"])
        hora = mudancas.get("hora", tarefa["hora"])
        if hora and not data:
            raise ErroOrganizacao("para ter horário, a tarefa precisa de uma data")
        if "lembrete" in bruto:
            mudancas["lembrete"] = _lembrete_param(bruto["lembrete"], data, hora)
        if not mudancas:
            raise ErroOrganizacao("nada para mudar na tarefa")
        params = {"id": tid, "titulo_atual": tarefa["titulo"], "mudancas": mudancas}
        partes = []
        if "titulo" in mudancas:
            partes.append(f"título {_aspas(mudancas['titulo'])}")
        if "data" in mudancas or "hora" in mudancas:
            partes.append(f"para {resumo_data(data, hora, hoje)}")
        if "lembrete" in mudancas:
            partes.append(
                "sem lembrete"
                if mudancas["lembrete"] is None
                else _texto_lembrete(mudancas["lembrete"], hoje).strip(" ·")
            )
        elif tarefa["lembrete_em"] and ("data" in mudancas or "hora" in mudancas):
            partes.append(
                "o lembrete acompanha" if data else "sem lembrete (ficou sem data)"
            )
        if "notas" in mudancas:
            partes.append(
                f"notas {_aspas(mudancas['notas'], 80)}"
                if mudancas["notas"]
                else "sem notas"
            )
        if "espaco" in mudancas:
            partes.append(f"mover para {_nome_espaco(store, mudancas['espaco'])}")
        resumo = f"Mudar a tarefa {_aspas(tarefa['titulo'])}: " + "; ".join(partes)
        return Proposta(tipo, params, resumo)

    # nota.criar
    _so_campos(bruto, ("texto", "titulo", "tipo_nota", "espaco"))
    txt = texto(bruto.get("texto"), "texto", MAX_TEXTO_NOTA)
    titulo = texto(bruto.get("titulo"), "titulo", MAX_TITULO, obrigatorio=False)
    tipo_nota = bruto.get("tipo_nota") or "nota"
    if tipo_nota not in TIPOS_NOTA:
        raise ErroOrganizacao("'tipo_nota' precisa ser nota ou ideia")
    esp = espaco_de()
    params = {"texto": txt, "titulo": titulo, "tipo_nota": tipo_nota, "espaco": esp}
    rotulo = "ideia" if tipo_nota == "ideia" else "nota"
    cabeca = f" {_aspas(titulo)}" if titulo else ""
    resumo = (
        f"Guardar {rotulo}{cabeca} em {_nome_espaco(store, esp)}: {_aspas(txt, 160)}"
    )
    return Proposta(tipo, params, resumo)


def propor(
    resposta: str,
    store: Organizacao,
    espaco_ativo: str,
    tz: timezone,
    conversa_id: Optional[str] = None,
    agora: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Lê os blocos da resposta, cria as ações pendentes e devolve
    (ações criadas, motivos das recusadas)."""
    agora = agora or agora_ms()
    hoje = local_de_ms(agora, tz).date()
    blocos = extrair_blocos(resposta)
    criadas: List[Dict[str, Any]] = []
    recusadas: List[str] = []
    if not blocos:
        return criadas, recusadas
    if len(blocos) > MAX_ACOES_POR_RESPOSTA:
        recusadas.append(
            f"o Éden sugeriu {len(blocos)} ações; só as "
            f"{MAX_ACOES_POR_RESPOSTA} primeiras foram consideradas"
        )
        blocos = blocos[:MAX_ACOES_POR_RESPOSTA]
    for bloco in blocos:
        if store.acoes_recentes(agora - 3600 * 1000) >= MAX_ACOES_POR_HORA:
            recusadas.append(
                "muitas sugestões na última hora; tente de novo mais tarde"
            )
            break
        try:
            if len(bloco) > MAX_BLOCO:
                raise ErroOrganizacao("ação grande demais")
            try:
                bruto = json.loads(bloco)
            except json.JSONDecodeError as exc:
                raise ErroOrganizacao(
                    "não deu para ler a ação (JSON inválido)"
                ) from exc
            proposta = validar(bruto, store, espaco_ativo, hoje)
        except ErroOrganizacao as exc:
            recusadas.append(str(exc))
            continue
        criadas.append(_gravar(store, proposta, conversa_id, agora))
    return criadas, recusadas


def _gravar(
    store: Organizacao, proposta: Proposta, conversa_id: Optional[str], agora: int
) -> Dict[str, Any]:
    acao_id = secrets.token_urlsafe(18)
    params_json = json.dumps(proposta.parametros, sort_keys=True, ensure_ascii=False)
    sig = assinatura(proposta.tipo, proposta.parametros)

    def fazer(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO acoes (id, tipo, parametros, assinatura, resumo, conversa_id, "
            "estado, criado_em, expira_em) VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?)",
            (
                acao_id,
                proposta.tipo,
                params_json,
                sig,
                proposta.resumo,
                conversa_id,
                agora,
                agora + VALIDADE_MS,
            ),
        )

    store.transacao(fazer)
    return store.acao(acao_id)  # type: ignore[return-value]


def _executar(
    store: Organizacao,
    conn: sqlite3.Connection,
    tipo: str,
    params: Dict[str, Any],
    tz: timezone,
    acao_id: str,
) -> Dict[str, Any]:
    """Executa com os parâmetros GUARDADOS no servidor."""
    quem = "eden"
    if tipo == "memoria.criar":
        mem = store.criar_memoria(
            params["texto"], params["espaco"], quem, acao_id, conn
        )
        return {"memoria": mem["id"]}
    if tipo == "memoria.apagar":
        store.apagar_memoria(params["id"], quem, acao_id, conn)
        return {"memoria": params["id"]}
    if tipo == "tarefa.criar":
        campos = {k: params[k] for k in ("titulo", "data", "hora", "notas", "espaco")}
        campos["lembrete"] = params["lembrete"] or False
        tarefa = store.criar_tarefa(campos, tz, quem, acao_id, conn)
        return {"tarefa": tarefa["id"]}
    if tipo == "tarefa.concluir":
        store.atualizar_tarefa(params["id"], {"feita": True}, tz, quem, acao_id, conn)
        return {"tarefa": params["id"]}
    if tipo == "tarefa.apagar":
        store.apagar_tarefa(params["id"], quem, acao_id, conn)
        return {"tarefa": params["id"]}
    if tipo == "tarefa.editar":
        mudancas = dict(params["mudancas"])
        if "lembrete" in mudancas:
            mudancas["lembrete"] = mudancas["lembrete"] or False
        store.atualizar_tarefa(params["id"], mudancas, tz, quem, acao_id, conn)
        return {"tarefa": params["id"]}
    if tipo == "nota.criar":
        nota = store.criar_nota(
            {
                "texto": params["texto"],
                "titulo": params["titulo"],
                "tipo": params["tipo_nota"],
                "espaco": params["espaco"],
            },
            quem,
            acao_id,
            conn,
        )
        return {"nota": nota["id"]}
    raise ErroOrganizacao("tipo de ação desconhecido")


def _decidir(
    store: Organizacao,
    acao_id: str,
    assinatura_app: Optional[str],
    executar: Optional[
        Callable[[sqlite3.Connection, str, Dict[str, Any]], Dict[str, Any]]
    ],
    agora: int,
) -> Dict[str, Any]:
    if not isinstance(acao_id, str) or not re.match(r"^[A-Za-z0-9_-]{8,64}$", acao_id):
        raise ErroAcao("ação não encontrada", 404, "eden_acao_nao_encontrada")

    def fazer(conn: sqlite3.Connection) -> Dict[str, Any]:
        row = conn.execute("SELECT * FROM acoes WHERE id = ?", (acao_id,)).fetchone()
        if row is None:
            raise ErroAcao("ação não encontrada", 404, "eden_acao_nao_encontrada")
        if row["estado"] != "pendente":
            raise ErroAcao("essa ação já foi decidida", 409, "eden_acao_ja_decidida")
        if row["expira_em"] <= agora:
            raise ErroAcao(
                "essa sugestão expirou (vale 15 minutos); peça de novo ao Éden",
                410,
                "eden_acao_expirada",
            )
        if executar is None:
            conn.execute(
                "UPDATE acoes SET estado = 'recusada', decidido_em = ? "
                "WHERE id = ? AND estado = 'pendente'",
                (agora, acao_id),
            )
            return {}
        if not assinatura_app or not secrets.compare_digest(
            str(assinatura_app), row["assinatura"]
        ):
            raise ErroAcao(
                "o cartão não bate com a ação guardada; atualize e confira de novo",
                409,
                "eden_acao_assinatura",
            )
        params = json.loads(row["parametros"])
        # Confere de novo a assinatura do que está gravado.
        if assinatura(row["tipo"], params) != row["assinatura"]:
            raise ErroAcao("ação guardada inconsistente", 409, "eden_acao_assinatura")
        cur = conn.execute(
            "UPDATE acoes SET estado = 'feita', decidido_em = ? "
            "WHERE id = ? AND estado = 'pendente'",
            (agora, acao_id),
        )
        if cur.rowcount != 1:
            raise ErroAcao("essa ação já foi decidida", 409, "eden_acao_ja_decidida")
        resultado = executar(conn, row["tipo"], params)
        conn.execute(
            "UPDATE acoes SET resultado = ? WHERE id = ?",
            (json.dumps(resultado), acao_id),
        )
        return resultado

    try:
        store.transacao(fazer)
    except ErroOrganizacao as exc:
        # Ex.: a tarefa foi apagada entre a sugestão e a confirmação. A
        # transação voltou atrás; marca a ação como falha (uso único).
        erro = json.dumps({"erro": str(exc)})

        def falhou(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE acoes SET estado = 'falhou', decidido_em = ?, resultado = ? "
                "WHERE id = ? AND estado = 'pendente'",
                (agora, erro, acao_id),
            )

        store.transacao(falhou)
        raise ErroAcao(f"não deu para fazer: {exc}", 409, "eden_acao_falhou") from exc
    return store.acao(acao_id)  # type: ignore[return-value]


def confirmar(
    store: Organizacao,
    acao_id: str,
    assinatura_app: Optional[str],
    tz: timezone,
    agora: Optional[int] = None,
) -> Dict[str, Any]:
    agora = agora or agora_ms()
    return _decidir(
        store,
        acao_id,
        assinatura_app,
        lambda conn, tipo, params: _executar(store, conn, tipo, params, tz, acao_id),
        agora,
    )


def recusar(
    store: Organizacao, acao_id: str, agora: Optional[int] = None
) -> Dict[str, Any]:
    return _decidir(store, acao_id, None, None, agora or agora_ms())
