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
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from openjarvis.eden.organizacao import (
    MAX_MEMORIA,
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

logger = logging.getLogger(__name__)

VALIDADE_MS = 15 * 60 * 1000
MAX_ACOES_POR_RESPOSTA = 5
# Textos que o Éden propõe precisam caber inteiros no cartão (a pessoa vê
# tudo o que será gravado). Pela tela, os limites são maiores.
MAX_IA_NOTAS_TAREFA = 1000
MAX_IA_TEXTO_NOTA = 4000
MAX_ACOES_POR_HORA = 60
# Uma conversa com texto colado "mandando" a IA sugerir coisas não pode gastar
# o limite de todas as outras (revisão de segurança de 15/10, achado 17).
MAX_ACOES_POR_CONVERSA_HORA = 20
MAX_BLOCO = 8000

TIPOS = (
    "memoria.criar",
    "memoria.apagar",
    "tarefa.criar",
    "tarefa.editar",
    "tarefa.concluir",
    "tarefa.apagar",
    "nota.criar",
    "agenda.criar",
    "agenda.editar",
    "conta.criar",
    "conta.pagar",
    "conta.apagar",
)
# Ações que mexem fora do Éden (Google): executadas fora da transação do banco.
TIPOS_EXTERNOS = ("agenda.criar", "agenda.editar")
MAX_LOCAL_AGENDA = 200

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


_CHAVES: Dict[str, bytes] = {}
_CHAVES_LOCK = threading.Lock()


def chave_assinatura(store: Organizacao) -> bytes:
    """Chave secreta do servidor para assinar os cartões. Fica ao lado do
    banco (acoes.key, só o dono lê) e não vai para o backup: uma linha mexida
    no banco ou num backup não consegue mostrar um cartão e executar outro
    (rodada final de segurança, 18/10)."""
    caminho = Path(getattr(store, "_path", "organizacao.db")).parent / "acoes.key"
    with _CHAVES_LOCK:
        guardada = _CHAVES.get(str(caminho))
        if guardada is not None:
            return guardada
        try:
            dados = caminho.read_bytes()
        except FileNotFoundError:
            dados = b""
        if len(dados) < 32:
            dados = secrets.token_bytes(32)
            tmp = caminho.with_name(caminho.name + ".novo")
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(dados)
            os.replace(tmp, caminho)
        _CHAVES[str(caminho)] = dados[:32]
        return dados[:32]


def assinatura(
    tipo: str,
    parametros: Dict[str, Any],
    resumo: str = "",
    chave: bytes = b"",
    identidade: str = "",
) -> str:
    """HMAC-sha256 (com a chave do servidor) do tipo, dos parâmetros, do
    resumo que o cartão mostra e da identidade do cartão (id, conversa,
    criação e validade): copiar para outro id ou esticar a validade num banco
    mexido não passa (revisão do Codex, 18/10)."""
    canonico = json.dumps(
        parametros, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    texto = f"{tipo}\n{canonico}\n{resumo}\n{identidade}".encode("utf-8")
    if not chave:
        return hashlib.sha256(texto).hexdigest()
    return hmac.new(chave, texto, hashlib.sha256).hexdigest()


def _identidade(
    acao_id: str, conversa_id: Optional[str], criado: int, expira: int
) -> str:
    return f"{acao_id}\n{conversa_id or ''}\n{int(criado)}\n{int(expira)}"


def _nome_espaco(store: Organizacao, espaco_id: Optional[str]) -> str:
    if espaco_id is None:
        return "todos os espaços"
    e = store.espaco(espaco_id)
    return e["nome"] if e else espaco_id


def _aspas(valor: str) -> str:
    # Texto inteiro, sem cortar: o cartão mostra exatamente o que será gravado.
    return f"“{valor}”"


_LINHAS_VAZIAS = re.compile(r"\n(?:[ \t]*\n){2,}")


def _sem_vazias(valor: str) -> str:
    """Textos que o Éden propõe: no máximo uma linha em branco seguida. Assim
    nada do cartão fica escondido lá embaixo por uma pilha de linhas vazias
    (rodada final de segurança, 18/10). O que vai para o cartão é o que é
    gravado."""
    return _LINHAS_VAZIAS.sub("\n\n", valor)


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
    agenda: Optional[Dict[str, Any]] = None,
    tz: Optional[timezone] = None,
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
        txt = texto(bruto.get("texto"), "texto", MAX_MEMORIA, uma_linha=True)
        valor_espaco = bruto.get("espaco", espaco_ativo)
        esp = (
            None
            if valor_espaco in ("todos", None, "")
            else store.espaco_valido(valor_espaco)
        )
        params = {"texto": txt, "espaco": esp}
        resumo = f"Guardar na memória ({_nome_espaco(store, esp)}): {_aspas(txt)}"
        return Proposta(tipo, params, resumo)

    if tipo == "memoria.apagar":
        _so_campos(bruto, ("id",))
        mid = inteiro(bruto.get("id"))
        mem = store.memoria(mid)
        if mem is None:
            raise ErroOrganizacao("memória não encontrada")
        if mem["espaco"] not in (None, espaco_ativo):
            # Só o espaço ativo (e as memórias de todos): sem isso, um pedido
            # com ids "chutados" traria para cá o texto de outro espaço.
            raise ErroOrganizacao("essa memória não está no espaço ativo")
        params = {"id": mid, "texto": mem["texto"]}
        return Proposta(tipo, params, f"Apagar da memória: {_aspas(mem['texto'])}")

    if tipo == "tarefa.criar":
        _so_campos(bruto, ("titulo", "data", "hora", "lembrete", "notas", "espaco"))
        titulo = texto(bruto.get("titulo"), "titulo", MAX_TITULO, uma_linha=True)
        data = data_iso(bruto.get("data"))
        hora = hora_hhmm(bruto.get("hora"))
        if hora and not data:
            raise ErroOrganizacao("para ter horário, a tarefa precisa de uma data")
        notas = _sem_vazias(
            texto(bruto.get("notas"), "notas", MAX_IA_NOTAS_TAREFA, obrigatorio=False)
        )
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
            resumo += f" · notas: {_aspas(notas)}"
        return Proposta(tipo, params, resumo)

    if tipo in ("tarefa.concluir", "tarefa.apagar"):
        _so_campos(bruto, ("id",))
        tid = inteiro(bruto.get("id"))
        tarefa = store.tarefa(tid)
        if tarefa is None:
            raise ErroOrganizacao("tarefa não encontrada")
        if tarefa["espaco"] != espaco_ativo:
            raise ErroOrganizacao("essa tarefa não está no espaço ativo")
        if tipo == "tarefa.concluir" and tarefa["feita"]:
            raise ErroOrganizacao("essa tarefa já está feita")
        params = {"id": tid, "titulo": tarefa["titulo"], "antes": _retrato(tarefa)}
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
        if tarefa["espaco"] != espaco_ativo:
            raise ErroOrganizacao("essa tarefa não está no espaço ativo")
        mudancas: Dict[str, Any] = {}
        if "titulo" in bruto:
            mudancas["titulo"] = texto(
                bruto["titulo"], "titulo", MAX_TITULO, uma_linha=True
            )
        if "data" in bruto:
            mudancas["data"] = data_iso(bruto["data"])
        if "hora" in bruto:
            mudancas["hora"] = hora_hhmm(bruto["hora"])
        if "notas" in bruto:
            mudancas["notas"] = _sem_vazias(
                texto(bruto["notas"], "notas", MAX_IA_NOTAS_TAREFA, obrigatorio=False)
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
        params = {
            "id": tid,
            "titulo_atual": tarefa["titulo"],
            "mudancas": mudancas,
            "antes": _retrato(tarefa),
        }
        partes = []
        # O que muda de lugar vem primeiro; o texto livre (notas), por último.
        if "espaco" in mudancas:
            partes.append(f"mover para {_nome_espaco(store, mudancas['espaco'])}")
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
                f"notas {_aspas(mudancas['notas'])}"
                if mudancas["notas"]
                else "sem notas"
            )
        resumo = f"Mudar a tarefa {_aspas(tarefa['titulo'])}: " + "; ".join(partes)
        return Proposta(tipo, params, resumo)

    if tipo in ("agenda.criar", "agenda.editar"):
        return _validar_agenda(tipo, bruto, hoje, agenda, tz)

    if tipo.startswith("conta."):
        return _validar_conta(tipo, bruto, store, espaco_ativo, hoje)

    # nota.criar
    _so_campos(bruto, ("texto", "titulo", "tipo_nota", "espaco"))
    txt = _sem_vazias(texto(bruto.get("texto"), "texto", MAX_IA_TEXTO_NOTA))
    titulo = texto(
        bruto.get("titulo"), "titulo", MAX_TITULO, obrigatorio=False, uma_linha=True
    )
    tipo_nota = bruto.get("tipo_nota") or "nota"
    if tipo_nota not in TIPOS_NOTA:
        raise ErroOrganizacao("'tipo_nota' precisa ser nota ou ideia")
    esp = espaco_de()
    params = {"texto": txt, "titulo": titulo, "tipo_nota": tipo_nota, "espaco": esp}
    rotulo = "ideia" if tipo_nota == "ideia" else "nota"
    cabeca = f" {_aspas(titulo)}" if titulo else ""
    resumo = f"Guardar {rotulo}{cabeca} em {_nome_espaco(store, esp)}: {_aspas(txt)}"
    return Proposta(tipo, params, resumo)


_CAMPOS_RETRATO = ("titulo", "data", "hora", "lembrete_em", "notas", "espaco", "feita")


def _retrato(tarefa: Dict[str, Any]) -> Dict[str, Any]:
    """Como a tarefa estava quando o cartão foi feito."""
    return {k: tarefa.get(k) for k in _CAMPOS_RETRATO}


_REPETE_TXT = {"nao": "", "mensal": " · todo mês", "anual": " · todo ano"}


def _validar_conta(
    tipo: str, bruto: Dict[str, Any], store: Organizacao, espaco_ativo: str, hoje: date
) -> Proposta:
    """Parte 5: contas e impostos. O cartão mostra valor, data e repetição
    exatamente como serão gravados — antes do texto da pessoa, para uma
    descrição não conseguir imitar o resto do cartão (revisão de 18/10)."""
    from openjarvis.eden import financas

    if tipo == "conta.criar":
        _so_campos(
            bruto,
            (
                "tipo_conta",
                "descricao",
                "valor",
                "vencimento",
                "repete",
                "categoria",
                "aviso_dias",
                "notas",
                "espaco",
            ),
        )
        dados = {k: v for k, v in bruto.items() if k not in ("tipo", "tipo_conta")}
        dados["tipo"] = bruto.get("tipo_conta") or "pagar"
        if "notas" in dados:
            dados["notas"] = _sem_vazias(
                texto(dados["notas"], "notas", MAX_IA_NOTAS_TAREFA, obrigatorio=False)
            )
        c = financas.campos(dados, store, espaco_ativo)
        params = {
            "tipo_conta": c["tipo"],
            "descricao": c["descricao"],
            "valor_centavos": c["valor_centavos"],
            "vencimento": c["vencimento"],
            "repete": c["repete"],
            "categoria": c["categoria"],
            "aviso_dias": c["aviso_dias"],
            "notas": c["notas"],
            "espaco": c["espaco"],
        }
        rotulo = "conta a pagar" if c["tipo"] == "pagar" else "valor a receber"
        quando = "vence" if c["tipo"] == "pagar" else "para"
        aviso = (
            "sem aviso"
            if c["aviso_dias"] < 0
            else "aviso no dia"
            if c["aviso_dias"] == 0
            else f"aviso {c['aviso_dias']} dia(s) antes"
        )
        resumo = (
            f"Anotar {rotulo} ({financas.reais(c['valor_centavos'])}, {quando} "
            f"{resumo_data(c['vencimento'], None, hoje)}"
            f"{_REPETE_TXT[c['repete']]}, {aviso}, em "
            f"{_nome_espaco(store, c['espaco'])}): {_aspas(c['descricao'])}"
        )
        if c["categoria"]:
            resumo += f" · categoria {_aspas(c['categoria'])}"
        if c["notas"]:
            resumo += f" · notas: {_aspas(c['notas'])}"
        return Proposta(tipo, params, resumo)

    # conta.pagar / conta.apagar
    _so_campos(bruto, ("id",))
    conta = financas.conta(store, bruto.get("id"))
    if conta is None:
        raise ErroOrganizacao("conta não encontrada")
    if conta["espaco"] != espaco_ativo:
        raise ErroOrganizacao("essa conta não está no espaço ativo")
    # A versão amarra o cartão à conta como ela estava (tipo, espaço,
    # repetição, dia…): qualquer mudança depois invalida o cartão.
    params = {
        "id": conta["id"],
        "descricao": conta["descricao"],
        "valor_centavos": conta["valor_centavos"],
        "vencimento": conta["vencimento"],
        "versao": conta["versao"],
    }
    detalhe = (
        f"{financas.reais(conta['valor_centavos'])}, vencimento "
        f"{resumo_data(conta['vencimento'], None, hoje)}"
    )
    if tipo == "conta.pagar":
        if conta["paga"]:
            raise ErroOrganizacao("essa conta já está paga")
        verbo = (
            "Marcar como paga" if conta["tipo"] == "pagar" else "Marcar como recebido"
        )
        if conta["repete"] != "nao":
            ja = financas.proxima_existente(store, conta["id"])
            if ja is not None:
                detalhe += (
                    "; a próxima já está anotada para "
                    f"{resumo_data(ja['vencimento'], None, hoje)}"
                )
            else:
                proxima = financas.proximo_vencimento(
                    conta["vencimento"], conta["repete"], conta["dia"]
                )
                detalhe += f"; a próxima fica para {resumo_data(proxima, None, hoje)}"
        return Proposta(
            tipo, params, f"{verbo} ({detalhe}): {_aspas(conta['descricao'])}"
        )
    return Proposta(
        tipo, params, f"Apagar a conta ({detalhe}): {_aspas(conta['descricao'])}"
    )


def _duracao(valor: Any) -> int:
    if valor in (None, ""):
        return 60
    duracao = inteiro(valor, "duracao_min")
    if not 5 <= duracao <= 24 * 60:
        raise ErroOrganizacao("'duracao_min' precisa ser de 5 a 1440 minutos")
    return duracao


def _texto_duracao(minutos: int) -> str:
    if minutos % 60 == 0:
        return f"{minutos // 60} h"
    if minutos > 60:
        return f"{minutos // 60} h {minutos % 60} min"
    return f"{minutos} min"


def _quando_evento(evento: Dict[str, Any], hoje: date) -> str:
    inicio = datetime.fromisoformat(evento["inicio"])
    hora = None if evento.get("dia_inteiro") else inicio.strftime("%H:%M")
    return resumo_data(inicio.date().isoformat(), hora, hoje)


def _texto_periodo(corpo: Dict[str, Any], hoje: date, tz: Any) -> str:
    """Início e fim que vão para o Google, em texto (o cartão mostra o
    resultado final, não só o que a IA pediu)."""
    inicio, fim = corpo["start"], corpo["end"]
    if "date" in inicio:
        d0 = date.fromisoformat(inicio["date"])
        d1 = date.fromisoformat(fim["date"]) - timedelta(days=1)
        txt = resumo_data(d0.isoformat(), None, hoje)
        if d1 > d0:
            txt += f" a {resumo_data(d1.isoformat(), None, hoje)}"
        return txt + " (dia inteiro)"
    a = datetime.fromisoformat(inicio["dateTime"]).astimezone(tz)
    b = datetime.fromisoformat(fim["dateTime"]).astimezone(tz)
    txt = resumo_data(a.date().isoformat(), a.strftime("%H:%M"), hoje)
    if b.date() == a.date():
        return f"{txt}–{b:%H:%M}"
    return f"{txt} até {resumo_data(b.date().isoformat(), b.strftime('%H:%M'), hoje)}"


def _validar_agenda(
    tipo: str,
    bruto: Dict[str, Any],
    hoje: date,
    agenda: Optional[Dict[str, Any]],
    tz: Optional[timezone] = None,
) -> Proposta:
    if not agenda or not agenda.get("conectado"):
        raise ErroOrganizacao("a Google Agenda não está conectada")
    if tipo == "agenda.criar":
        _so_campos(bruto, ("titulo", "data", "hora", "duracao_min", "local"))
        titulo = texto(bruto.get("titulo"), "titulo", MAX_TITULO, uma_linha=True)
        data = data_iso(bruto.get("data"))
        if not data:
            raise ErroOrganizacao("o evento precisa de uma data")
        hora = hora_hhmm(bruto.get("hora"))
        duracao = _duracao(bruto.get("duracao_min")) if hora else None
        local = texto(
            bruto.get("local"),
            "local",
            MAX_LOCAL_AGENDA,
            obrigatorio=False,
            uma_linha=True,
        )
        params = {
            "titulo": titulo,
            "data": data,
            "hora": hora,
            "duracao_min": duracao,
            "local": local,
        }
        quando = resumo_data(data, hora, hoje)
        if hora:
            quando += f" ({_texto_duracao(duracao)})"
        else:
            quando += " (dia inteiro)"
        resumo = f"Criar na Google Agenda: {_aspas(titulo)} — {quando}"
        if local:
            resumo += f" · local {_aspas(local)}"
        return Proposta(tipo, params, resumo)

    # agenda.editar
    from openjarvis.eden.google import MAX_ID_PARA_IA, mudancas_do_evento

    _so_campos(bruto, ("id", "titulo", "data", "hora", "duracao_min", "local"))
    evento_id = bruto.get("id")
    eventos = agenda.get("eventos") or {}
    if (
        not isinstance(evento_id, str)
        or len(evento_id) > MAX_ID_PARA_IA
        or evento_id not in eventos
    ):
        raise ErroOrganizacao("evento não encontrado na agenda dos próximos dias")
    evento = eventos[evento_id]
    mudancas: Dict[str, Any] = {}
    if "titulo" in bruto:
        mudancas["titulo"] = texto(
            bruto["titulo"], "titulo", MAX_TITULO, uma_linha=True
        )
    if "data" in bruto:
        mudancas["data"] = data_iso(bruto["data"])
        if not mudancas["data"]:
            raise ErroOrganizacao("'data' não pode ficar vazia")
    if "hora" in bruto:
        mudancas["hora"] = hora_hhmm(bruto["hora"])
        if not mudancas["hora"]:
            raise ErroOrganizacao("'hora' não pode ficar vazia")
    if "duracao_min" in bruto:
        mudancas["duracao_min"] = _duracao(bruto["duracao_min"])
        if evento.get("dia_inteiro") and "hora" not in mudancas:
            raise ErroOrganizacao(
                "o evento é de dia inteiro: para mudar a duração, diga também a hora"
            )
    if "local" in bruto:
        mudancas["local"] = texto(
            bruto["local"],
            "local",
            MAX_LOCAL_AGENDA,
            obrigatorio=False,
            uma_linha=True,
        )
    if not mudancas:
        raise ErroOrganizacao("nada para mudar no evento")
    zona = tz or datetime.fromisoformat(evento["inicio"]).tzinfo or timezone.utc
    # O que vai para o Google é calculado agora e entra na assinatura: o
    # cartão mostra exatamente o que será gravado.
    corpo = mudancas_do_evento(evento, mudancas, zona)
    partes: List[str] = []
    if "summary" in corpo:
        partes.append(f"título → {_aspas(corpo['summary'])}")
    if "start" in corpo:
        partes.append(f"para {_texto_periodo(corpo, hoje, zona)}")
    if "location" in corpo:
        partes.append(
            f"local → {_aspas(corpo['location'])}" if corpo["location"] else "sem local"
        )
    params = {
        "id": evento_id,
        "titulo_atual": evento["titulo"],
        "antes": {
            "inicio": evento["inicio"],
            "fim": evento.get("fim"),
            "dia_inteiro": bool(evento.get("dia_inteiro")),
            "etag": evento.get("etag") or "",
        },
        "corpo": corpo,
    }
    resumo = (
        f"Mudar na Google Agenda {_aspas(evento['titulo'])} "
        f"({_quando_evento(evento, hoje)}): " + "; ".join(partes)
    )
    convidados = int(evento.get("convidados") or 0)
    if convidados:
        resumo += (
            f" · evento com {convidados} "
            f"{'convidado' if convidados == 1 else 'convidados'}"
        )
    if evento.get("convite"):
        resumo += " · convite que você ainda não aceitou"
    return Proposta(tipo, params, resumo)


def propor(
    resposta: str,
    store: Organizacao,
    espaco_ativo: str,
    tz: timezone,
    conversa_id: Optional[str] = None,
    agora: Optional[int] = None,
    agenda: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Lê os blocos da resposta, cria as ações pendentes e devolve
    (ações criadas, motivos das recusadas). ``agenda``: retrato da Google
    Agenda em cache ({"conectado", "eventos": {id: evento}})."""
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
    uma_hora_atras = agora - 3600 * 1000
    for bloco in blocos:
        if (
            conversa_id
            and store.acoes_recentes(uma_hora_atras, conversa_id)
            >= MAX_ACOES_POR_CONVERSA_HORA
        ):
            recusadas.append(
                "muitas sugestões nesta conversa na última hora; comece uma "
                "conversa nova ou tente de novo mais tarde"
            )
            break
        if store.acoes_recentes(uma_hora_atras) >= MAX_ACOES_POR_HORA:
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
            proposta = validar(bruto, store, espaco_ativo, hoje, agenda, tz)
        except ErroOrganizacao as exc:
            recusadas.append(str(exc))
            continue
        except (ValueError, TypeError, OverflowError):
            # Um bloco estranho não derruba os outros.
            recusadas.append("não deu para entender a ação")
            continue
        criadas.append(_gravar(store, proposta, conversa_id, agora))
    return criadas, recusadas


def _gravar(
    store: Organizacao, proposta: Proposta, conversa_id: Optional[str], agora: int
) -> Dict[str, Any]:
    acao_id = secrets.token_urlsafe(18)
    params_json = json.dumps(proposta.parametros, sort_keys=True, ensure_ascii=False)
    sig = assinatura(
        proposta.tipo,
        proposta.parametros,
        proposta.resumo,
        chave_assinatura(store),
        _identidade(acao_id, conversa_id, agora, agora + VALIDADE_MS),
    )

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


def _alvo_igual(
    store: Organizacao, conn: sqlite3.Connection, tipo: str, params: Dict[str, Any]
) -> None:
    """O item que o cartão mostrou continua igual? Se foi editado pela tela
    no meio tempo, a confirmação não vale para a versão nova."""
    if tipo == "memoria.apagar":
        row = conn.execute(
            "SELECT texto FROM memorias WHERE id = ? AND apagado_em IS NULL",
            (params["id"],),
        ).fetchone()
        if row is None:
            raise ErroOrganizacao("memória não encontrada")
        if row["texto"] != params["texto"]:
            raise ErroOrganizacao("a memória mudou depois da sugestão; peça de novo")
    elif tipo in ("tarefa.concluir", "tarefa.apagar", "tarefa.editar"):
        tarefa = store.tarefa(params["id"], conn)
        if tarefa is None:
            raise ErroOrganizacao("tarefa não encontrada")
        # A tarefa inteira (hora, data, lembrete, notas, espaço…) continua
        # como o cartão mostrou? (revisão do Codex, 18/10)
        if "antes" not in params or _retrato(tarefa) != params["antes"]:
            raise ErroOrganizacao("a tarefa mudou depois da sugestão; peça de novo")
    elif tipo in ("conta.pagar", "conta.apagar"):
        from openjarvis.eden import financas

        conta = financas.conta(store, params["id"], conn)
        if conta is None:
            raise ErroOrganizacao("conta não encontrada")
        if "versao" not in params or any(
            conta[k] != params[k]
            for k in ("descricao", "valor_centavos", "vencimento", "versao")
        ):
            raise ErroOrganizacao("a conta mudou depois da sugestão; peça de novo")


def _executar(
    store: Organizacao,
    conn: sqlite3.Connection,
    tipo: str,
    params: Dict[str, Any],
    tz: timezone,
    acao_id: str,
) -> Dict[str, Any]:
    """Executa com os parâmetros GUARDADOS no servidor."""
    _alvo_igual(store, conn, tipo, params)
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
    if tipo.startswith("conta."):
        from openjarvis.eden import financas

        if tipo == "conta.criar":
            campos_conta = {
                k: params[k]
                for k in (
                    "descricao",
                    "valor_centavos",
                    "vencimento",
                    "repete",
                    "categoria",
                    "aviso_dias",
                    "notas",
                    "espaco",
                )
            }
            campos_conta["tipo"] = params["tipo_conta"]
            store.espaco_valido(campos_conta["espaco"])
            nova = financas.criar_limpa(store, campos_conta, quem, acao_id, conn)
            return {"conta": nova["id"]}
        if tipo == "conta.pagar":
            feito = financas.marcar_paga(store, params["id"], quem, acao_id, conn)
            proxima = feito["proxima"]
            return {
                "conta": params["id"],
                "proxima": proxima["id"] if proxima else None,
            }
        financas.apagar(store, params["id"], quem, acao_id, conn)
        return {"conta": params["id"]}
    raise ErroOrganizacao("tipo de ação desconhecido")


def _decidir(
    store: Organizacao,
    acao_id: str,
    assinatura_app: Optional[str],
    executar: Optional[
        Callable[[sqlite3.Connection, str, Dict[str, Any]], Dict[str, Any]]
    ],
    agora: int,
    externo: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
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
        esperada = assinatura(
            row["tipo"],
            params,
            row["resumo"],
            chave_assinatura(store),
            _identidade(
                row["id"], row["conversa_id"], row["criado_em"], row["expira_em"]
            ),
        )
        if not hmac.compare_digest(esperada, row["assinatura"]):
            raise ErroAcao("ação guardada inconsistente", 409, "eden_acao_assinatura")
        if row["tipo"] in TIPOS_EXTERNOS:
            # Fora do Éden (Google): marca "executando" (uso único) e faz a
            # chamada depois, sem segurar o banco.
            cur = conn.execute(
                "UPDATE acoes SET estado = 'executando', decidido_em = ? "
                "WHERE id = ? AND estado = 'pendente'",
                (agora, acao_id),
            )
            if cur.rowcount != 1:
                raise ErroAcao(
                    "essa ação já foi decidida", 409, "eden_acao_ja_decidida"
                )
            return {"__externo__": [row["tipo"], params]}
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
        pronto = store.transacao(fazer)
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
    if isinstance(pronto, dict) and "__externo__" in pronto:
        tipo, params = pronto["__externo__"]
        _executar_fora(store, acao_id, tipo, params, externo, agora_ms())
    return store.acao(acao_id)  # type: ignore[return-value]


def _executar_fora(
    store: Organizacao,
    acao_id: str,
    tipo: str,
    params: Dict[str, Any],
    externo: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]],
    agora: int,
) -> None:
    from openjarvis.eden.google import ErroGoogle

    def falhou(mensagem: str) -> None:
        erro = json.dumps({"erro": mensagem})
        store.transacao(
            lambda conn: conn.execute(
                "UPDATE acoes SET estado = 'falhou', resultado = ? "
                "WHERE id = ? AND estado = 'executando'",
                (erro, acao_id),
            )
        )

    try:
        if externo is None:
            raise ErroOrganizacao("a Google Agenda não está conectada")
        resultado = externo(tipo, params)
    except (ErroOrganizacao, ErroGoogle) as exc:
        mensagem = str(exc)
        if getattr(exc, "codigo", "") == "eden_google_rede":
            mensagem += " Confira na agenda antes de pedir de novo."
        falhou(mensagem)
        raise ErroAcao(
            f"não deu para fazer: {mensagem}", 409, "eden_acao_falhou"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - o cartão nunca fica preso
        logger.exception("Éden: falha inesperada ao falar com o Google")
        mensagem = (
            "algo deu errado ao falar com o Google; confira na agenda antes de "
            "pedir de novo"
        )
        falhou(mensagem)
        raise ErroAcao(
            f"não deu para fazer: {mensagem}", 409, "eden_acao_falhou"
        ) from exc

    def gravar(conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE acoes SET estado = 'feita', resultado = ? "
            "WHERE id = ? AND estado = 'executando'",
            (json.dumps(resultado), acao_id),
        )
        o_que = "criou evento" if tipo == "agenda.criar" else "mudou evento"
        Organizacao._registrar(
            conn, "eden", o_que, f"agenda:{resultado.get('evento')}", acao_id
        )

    store.transacao(gravar)


def confirmar(
    store: Organizacao,
    acao_id: str,
    assinatura_app: Optional[str],
    tz: timezone,
    agora: Optional[int] = None,
    google: Any = None,
) -> Dict[str, Any]:
    """``google``: cliente da Google Agenda (para as ações agenda.*)."""
    agora = agora or agora_ms()

    def externo(tipo: str, params: Dict[str, Any]) -> Dict[str, Any]:
        from openjarvis.eden.google import id_para_criar

        if google is None:
            raise ErroOrganizacao("a Google Agenda não está conectada")
        if tipo == "agenda.criar":
            # ID fixo por cartão: se a resposta do Google se perder e o
            # pedido se repetir, não nasce um segundo evento igual.
            return google.criar(params, tz, evento_id=id_para_criar(acao_id))
        if not isinstance(params.get("corpo"), dict) or "antes" not in params:
            raise ErroOrganizacao("sugestão antiga; peça de novo ao Éden")
        # agenda.editar: o evento que o cartão mostrou continua igual?
        atual = google.evento(params["id"], tz)
        antes = params["antes"]
        if (
            atual["titulo"] != params["titulo_atual"]
            or atual["inicio"] != antes["inicio"]
            or atual.get("fim") != antes["fim"]
            or bool(atual.get("dia_inteiro")) != antes["dia_inteiro"]
            or (antes.get("etag") and atual.get("etag") != antes["etag"])
        ):
            raise ErroOrganizacao("o evento mudou depois da sugestão; peça de novo")
        return google.editar(
            params["id"], params["corpo"], tz, etag=antes.get("etag") or ""
        )

    return _decidir(
        store,
        acao_id,
        assinatura_app,
        lambda conn, tipo, params: _executar(store, conn, tipo, params, tz, acao_id),
        agora,
        externo,
    )


def recusar(
    store: Organizacao, acao_id: str, agora: Optional[int] = None
) -> Dict[str, Any]:
    return _decidir(store, acao_id, None, None, agora or agora_ms())
