"""Éden: ligação com a Google Agenda (Parte 3).

O que faz:
- a pessoa liga a conta do Google nas Configurações (autorização do próprio
  Google, com "state" de uso único e PKCE);
- o Éden lê os eventos dos próximos dias (página Hoje e contexto da IA);
- a IA pode **sugerir** criar ou mudar um evento; só acontece quando a pessoa
  toca em Confirmar no cartão (mesmo caminho das tarefas).

Segurança:
- só a permissão de eventos da agenda (``calendar.events``); nada de e-mail,
  Drive ou contatos;
- o "refresh token" (a autorização que dura) fica **cifrado** no banco do
  Éden; a chave da cifra fica num arquivo ``.key`` que nunca entra no backup.
  Quem pegar um backup não consegue mexer na agenda; depois de restaurar
  num servidor novo, basta ligar a conta de novo;
- o ID e o segredo do cliente do Google ficam só no ``.env`` do servidor;
- o Éden só fala com endereços fixos do Google (nada vindo da IA ou de
  eventos vira endereço);
- títulos e locais dos eventos são dados de fora: entram no contexto da IA
  entre aspas, limpos de caracteres invisíveis e com tamanho limitado.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOGAR = "https://oauth2.googleapis.com/revoke"
URL_AGENDA = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
ESCOPO_AGENDA = "https://www.googleapis.com/auth/calendar.events"
# Drive: só os arquivos que o próprio Éden cria (não enxerga o resto do Drive).
ESCOPO_DRIVE = "https://www.googleapis.com/auth/drive.file"
URL_DRIVE = "https://www.googleapis.com/drive/v3/files"
URL_DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
NOME_PASTA_DRIVE = "Éden"
AJUSTE_PASTA_DRIVE = "google_drive_pasta"
MAX_HTML_DRIVE = 2 * 1024 * 1024
CAMINHO_RETORNO = "/v1/eden/google/retorno"

VALIDADE_AUTORIZACAO_S = 10 * 60
MAX_AUTORIZACOES = 5
TEMPO_LIMITE_S = 15.0
DIAS_NA_AGENDA = 7
MAX_EVENTOS = 40
MAX_TITULO = 200
MAX_LOCAL = 200

_CLIENT_ID = re.compile(r"[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com")
_EVENTO_ID = re.compile(r"[A-Za-z0-9_]{1,1024}")
# IDs maiores que isto não aparecem para a IA (convites de fora podem ter IDs
# longos escolhidos por quem mandou).
MAX_ID_PARA_IA = 64
_ESPACOS = re.compile(r"\s+")


class ErroGoogle(Exception):
    def __init__(self, mensagem: str, codigo: str = "eden_google") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


# ── configuração (no .env do servidor) ───────────────────────────────────


def configuracao() -> Optional[Dict[str, str]]:
    """ID e segredo do cliente do Google + endereço de retorno. None se
    faltar algo (a tela mostra "ainda não configurado")."""
    from openjarvis.eden.endereco import endereco_celular

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    segredo = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    endereco = endereco_celular()
    if not client_id or not segredo or not endereco:
        return None
    if not _CLIENT_ID.fullmatch(client_id) or any(c.isspace() for c in segredo):
        logger.warning("Éden: GOOGLE_CLIENT_ID ou _SECRET com formato estranho")
        return None
    return {
        "client_id": client_id,
        "client_secret": segredo,
        "retorno": endereco + CAMINHO_RETORNO,
    }


# ── cofre: refresh token cifrado ─────────────────────────────────────────


def _caminho_chave() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir() / "eden" / "google.key"


def _carregar_cifra(caminho: Optional[Path] = None):
    """Chave da cifra: criada de uma vez (arquivo temporário 0600 + link), para
    ninguém ler um arquivo pela metade; conferida ao carregar."""
    from cryptography.fernet import Fernet

    caminho = caminho or _caminho_chave()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not caminho.exists():
        temporario = caminho.with_name(f".{caminho.name}.{secrets.token_hex(8)}")
        fd = os.open(str(temporario), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as arquivo:
                arquivo.write(Fernet.generate_key())
                arquivo.flush()
                os.fsync(arquivo.fileno())
            try:
                os.link(temporario, caminho)
            except FileExistsError:
                pass  # outra linha criou antes: vale a dela
        finally:
            temporario.unlink(missing_ok=True)
    if caminho.stat().st_mode & 0o077:
        os.chmod(caminho, 0o600)
    try:
        return Fernet(caminho.read_bytes().strip())
    except ValueError as exc:
        logger.error("Éden: a chave da Google Agenda (%s) está estragada", caminho.name)
        raise ErroGoogle(
            "A chave da Google Agenda no servidor está estragada. Apague o "
            "arquivo eden/google.key e conecte de novo.",
            "eden_google_chave",
        ) from exc


class Cofre:
    """Guarda o refresh token cifrado na tabela ``ajustes``."""

    CHAVE = "google_agenda"

    def __init__(self, store, caminho_chave: Optional[Path] = None) -> None:  # noqa: ANN001
        self.store = store
        self._caminho = caminho_chave
        self._cifra = None

    def _f(self):
        if self._cifra is None:
            self._cifra = _carregar_cifra(self._caminho)
        return self._cifra

    def salvar(self, refresh_token: str, escopo: str) -> None:
        dados = json.dumps(
            {"refresh": refresh_token, "escopo": escopo, "em": int(time.time())}
        ).encode()
        cifrado = self._f().encrypt(dados).decode()
        self.store.transacao(
            lambda c: c.execute(
                "INSERT INTO ajustes (chave, valor) VALUES (?, ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (self.CHAVE, cifrado),
            )
        )

    def ler(self) -> Optional[Dict[str, Any]]:
        from cryptography.fernet import InvalidToken

        rows = self.store._ler(
            "SELECT valor FROM ajustes WHERE chave = ?", (self.CHAVE,)
        )
        if not rows:
            return None
        try:
            dados = json.loads(self._f().decrypt(rows[0][0].encode()))
        except ErroGoogle:
            raise
        except (InvalidToken, ValueError, TypeError):
            # Ex.: backup restaurado em outro servidor (a chave não vai junto).
            return None
        return dados if isinstance(dados.get("refresh"), str) else None

    def apagar(self) -> None:
        self.store.transacao(
            lambda c: c.execute("DELETE FROM ajustes WHERE chave = ?", (self.CHAVE,))
        )

    def conectado(self) -> bool:
        return self.ler() is not None


# ── autorizações em andamento (state + PKCE) ─────────────────────────────


def _resumo(valor: str) -> str:
    return hashlib.sha256(("eden-google:" + valor).encode()).hexdigest()


class Autorizacoes:
    """Pedidos de ligação em andamento: "state" de uso único, 10 minutos."""

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._lock = threading.Lock()
        self._pendentes: Dict[str, Tuple[str, float, str]] = {}

    def criar(self, tipo: str = "agenda") -> Tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verificador = secrets.token_urlsafe(64)
        with self._lock:
            agora = self._relogio()
            self._pendentes = {k: v for k, v in self._pendentes.items() if v[1] > agora}
            while len(self._pendentes) >= MAX_AUTORIZACOES:
                mais_velho = min(self._pendentes, key=lambda k: self._pendentes[k][1])
                del self._pendentes[mais_velho]
            self._pendentes[_resumo(state)] = (
                verificador,
                agora + VALIDADE_AUTORIZACAO_S,
                tipo,
            )
        return state, verificador

    def usar(self, state: Any) -> Optional[str]:
        achado = self.usar_com_tipo(state)
        return achado[0] if achado else None

    def usar_com_tipo(self, state: Any) -> Optional[Tuple[str, str]]:
        """(verificador, tipo) do pedido, uma vez só; None se não vale."""
        if not isinstance(state, str) or not 20 <= len(state) <= 200:
            return None
        with self._lock:
            item = self._pendentes.pop(_resumo(state), None)
        if item is None or item[1] <= self._relogio():
            return None
        return item[0], item[2]


def desafio_pkce(verificador: str) -> str:
    digest = hashlib.sha256(verificador.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def url_de_autorizacao(
    cfg: Dict[str, str],
    state: str,
    verificador: str,
    drive: bool = False,
    escopos: Optional[List[str]] = None,
) -> str:
    """``drive``: pede também a permissão de criar arquivos no Drive (só os
    que o Éden cria). Sem ela, só a agenda. ``escopos``: outra lista (ex.: só
    a leitura do e-mail)."""
    if escopos is None:
        escopos = [ESCOPO_AGENDA, ESCOPO_DRIVE] if drive else [ESCOPO_AGENDA]
    return (
        URL_AUTORIZAR
        + "?"
        + urlencode(
            {
                "client_id": cfg["client_id"],
                "redirect_uri": cfg["retorno"],
                "response_type": "code",
                "scope": " ".join(escopos),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
                "state": state,
                "code_challenge": desafio_pkce(verificador),
                "code_challenge_method": "S256",
            }
        )
    )


# ── textos de fora (títulos e locais dos eventos) ────────────────────────


def limpar_externo(valor: Any, maximo: int) -> str:
    from openjarvis.eden.organizacao import _visivel

    if not isinstance(valor, str):
        return ""
    limpo = "".join(c for c in valor if c in "\n\t" or _visivel(c))
    limpo = _ESPACOS.sub(" ", limpo).strip()
    if len(limpo) > maximo:
        limpo = limpo[: maximo - 1].rstrip() + "…"
    return limpo


def _momento(campo: Any, tz: timezone) -> Tuple[Optional[datetime], bool]:
    """(início, dia_inteiro) de um campo start/end do Google."""
    if not isinstance(campo, dict):
        return None, False
    if isinstance(campo.get("dateTime"), str):
        try:
            return datetime.fromisoformat(
                campo["dateTime"].replace("Z", "+00:00")
            ).astimezone(tz), False
        except ValueError:
            return None, False
    if isinstance(campo.get("date"), str):
        try:
            d = date.fromisoformat(campo["date"])
        except ValueError:
            return None, True
        return datetime(d.year, d.month, d.day, tzinfo=tz), True
    return None, False


def _situacao_convite(bruto: Dict[str, Any]) -> Optional[str]:
    """Resposta da própria pessoa a um convite: None (não é convite ou já
    aceitou), "pendente", "talvez" ou "recusado"."""
    for convidado in bruto.get("attendees") or []:
        if isinstance(convidado, dict) and convidado.get("self"):
            resposta = convidado.get("responseStatus")
            return {
                "needsAction": "pendente",
                "tentative": "talvez",
                "declined": "recusado",
            }.get(resposta)
    return None


def normalizar_evento(bruto: Any, tz: timezone) -> Optional[Dict[str, Any]]:
    try:
        return _normalizar_evento(bruto, tz)
    except (ValueError, TypeError, OverflowError):
        # Um evento estranho não derruba a agenda inteira.
        return None


def _normalizar_evento(bruto: Any, tz: timezone) -> Optional[Dict[str, Any]]:
    if not isinstance(bruto, dict) or bruto.get("status") == "cancelled":
        return None
    convite = _situacao_convite(bruto)
    if convite == "recusado":
        return None
    evento_id = bruto.get("id")
    if not isinstance(evento_id, str) or not _EVENTO_ID.fullmatch(evento_id):
        return None
    inicio, dia_inteiro = _momento(bruto.get("start"), tz)
    fim, _ = _momento(bruto.get("end"), tz)
    if inicio is None:
        return None
    convidados = [
        c
        for c in (bruto.get("attendees") or [])
        if isinstance(c, dict) and not c.get("self")
    ]
    return {
        "id": evento_id,
        "titulo": limpar_externo(bruto.get("summary"), MAX_TITULO) or "(sem título)",
        "local": limpar_externo(bruto.get("location"), MAX_LOCAL),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat() if fim else None,
        "dia_inteiro": dia_inteiro,
        "convite": convite,
        "convidados": len(convidados),
        # Versão do evento no Google: muda a cada alteração (convidados,
        # local…). O cartão de mudar só vale para a versão que mostrou.
        "etag": "".join(
            c for c in str(bruto.get("etag") or "")[:200] if 32 < ord(c) < 127
        ),
    }


def corpo_do_evento(params: Dict[str, Any], tz: timezone) -> Dict[str, Any]:
    """Parâmetros do Éden (data, hora, duração) → corpo do evento do Google."""
    d = date.fromisoformat(params["data"])
    corpo: Dict[str, Any] = {"summary": params["titulo"]}
    if params.get("local"):
        corpo["location"] = params["local"]
    if params.get("hora"):
        h, m = (int(x) for x in params["hora"].split(":"))
        inicio = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
        fim = inicio + timedelta(minutes=int(params.get("duracao_min") or 60))
        corpo["start"] = {"dateTime": inicio.isoformat()}
        corpo["end"] = {"dateTime": fim.isoformat()}
    else:
        corpo["start"] = {"date": d.isoformat()}
        corpo["end"] = {"date": (d + timedelta(days=1)).isoformat()}
    return corpo


def mudancas_do_evento(
    atual: Dict[str, Any], mudancas: Dict[str, Any], tz: timezone
) -> Dict[str, Any]:
    """Mudanças pedidas (titulo, local, data, hora, duracao_min) → campos do
    Google, completando com o que o evento já tem (ex.: muda só a hora).
    Calculado na hora da sugestão: o cartão mostra exatamente o resultado."""
    corpo: Dict[str, Any] = {}
    if "titulo" in mudancas:
        corpo["summary"] = mudancas["titulo"]
    if "local" in mudancas:
        corpo["location"] = mudancas["local"] or ""
    if not {"data", "hora", "duracao_min"} & set(mudancas):
        return corpo
    inicio = datetime.fromisoformat(atual["inicio"]).astimezone(tz)
    fim = None
    if atual.get("fim"):
        fim = datetime.fromisoformat(atual["fim"]).astimezone(tz)
    dia = inicio.date()
    if mudancas.get("data"):
        dia = date.fromisoformat(mudancas["data"])
    hora = mudancas.get("hora")
    if atual.get("dia_inteiro") and hora is None:
        if mudancas.get("duracao_min"):
            raise ValueError("evento de dia inteiro: para mudar a duração, diga a hora")
        # Continua de dia inteiro, com a mesma quantidade de dias.
        dias = max(1, (fim.date() - inicio.date()).days) if fim else 1
        corpo["start"] = {"date": dia.isoformat()}
        corpo["end"] = {"date": (dia + timedelta(days=dias)).isoformat()}
        return corpo
    if hora is None:
        hora = inicio.strftime("%H:%M")
    if mudancas.get("duracao_min"):
        duracao = int(mudancas["duracao_min"])
    elif fim and not atual.get("dia_inteiro"):
        duracao = max(5, int((fim - inicio).total_seconds() // 60))
    else:
        duracao = 60
    novo = corpo_do_evento(
        {"titulo": "", "data": dia.isoformat(), "hora": hora, "duracao_min": duracao},
        tz,
    )
    corpo["start"] = novo["start"]
    corpo["end"] = novo["end"]
    return corpo


def id_para_criar(acao_id: str) -> str:
    """ID do evento escolhido pelo Éden (base32hex do Google): se o pedido
    se repetir, o Google recusa o segundo em vez de criar outro igual."""
    return "eden" + hashlib.sha256(acao_id.encode()).hexdigest()[:32]


# ── cliente (só endereços fixos do Google) ───────────────────────────────


class ClienteGoogle:
    def __init__(
        self,
        cofre: Cofre,
        cfg: Optional[Dict[str, str]] = None,
        http: Any = None,
        relogio: Callable[[], float] = time.time,
        nome: str = "Google Agenda",
    ) -> None:
        self.cofre = cofre
        self.nome = nome
        self._cfg = cfg
        self._http = http
        self._relogio = relogio
        self._lock = threading.Lock()
        self._acesso: Optional[Tuple[str, float]] = None
        # Muda a cada desconexão: uma renovação que começou antes não guarda o
        # token depois (revisão do Codex, 18/10).
        self._geracao = 0

    @property
    def cfg(self) -> Dict[str, str]:
        cfg = self._cfg or configuracao()
        if cfg is None:
            raise ErroGoogle(
                "A Google Agenda ainda não foi configurada no servidor.",
                "eden_google_sem_config",
            )
        return cfg

    def _cliente_http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=TEMPO_LIMITE_S, follow_redirects=False)
        return self._http

    def _rede(self, metodo: str, url: str, **kw: Any) -> Any:
        """Uma chamada ao Google; qualquer falha de rede vira ErroGoogle."""
        try:
            if metodo == "POST" and "data" in kw:
                return self._cliente_http().post(url, **kw)
            return self._cliente_http().request(metodo, url, **kw)
        except ErroGoogle:
            raise
        except Exception as exc:  # noqa: BLE001 - timeout, conexão, etc.
            raise ErroGoogle(
                "Sem resposta do Google agora. Tente de novo.", "eden_google_rede"
            ) from exc

    @staticmethod
    def _json(resposta: Any) -> Dict[str, Any]:
        try:
            dados = resposta.json() if resposta.content else {}
        except ValueError as exc:
            raise ErroGoogle("Resposta estranha do Google.") from exc
        return dados if isinstance(dados, dict) else {}

    def _guardar_acesso(
        self, dados: Dict[str, Any], geracao: Optional[int] = None
    ) -> str:
        token = str(dados.get("access_token", ""))
        try:
            validade = int(dados.get("expires_in", 0))
        except (TypeError, ValueError):
            validade = 0
        with self._lock:
            if geracao is not None and geracao != self._geracao:
                raise ErroGoogle(
                    f"A conta ({self.nome}) não está conectada.",
                    "eden_google_desconectado",
                )
            self._acesso = (token, self._relogio() + max(0, validade) - 60)
        return token

    # ligação

    def trocar_codigo(
        self, codigo: str, verificador: str, exigir: str = ESCOPO_AGENDA
    ) -> None:
        """``exigir``: a permissão sem a qual a ligação não vale (a agenda,
        ou a leitura do e-mail)."""
        cfg = self.cfg
        resposta = self._rede(
            "POST",
            URL_TOKEN,
            data={
                "code": codigo,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri": cfg["retorno"],
                "grant_type": "authorization_code",
                "code_verifier": verificador,
            },
        )
        if resposta.status_code != 200:
            raise ErroGoogle("O Google recusou a ligação. Tente de novo.")
        dados = self._json(resposta)
        escopos = str(dados.get("scope", "")).split()
        refresh = dados.get("refresh_token")
        if exigir not in escopos:
            raise ErroGoogle(
                "A permissão não foi dada. Marque a caixa da permissão na tela "
                "do Google.",
                "eden_google_sem_permissao",
            )
        if not isinstance(refresh, str) or not refresh:
            raise ErroGoogle("O Google não mandou a autorização. Tente de novo.")
        self.cofre.salvar(refresh, " ".join(escopos))
        self._guardar_acesso(dados)
        # Ligou de novo: a autorização antiga sai do cofre (é sobrescrita).
        # NÃO revogar no Google: a revogação do Google vale para a
        # autorização inteira (este app + esta conta), e derrubaria também a
        # autorização nova que acabou de chegar.

    def revogar_token(self, token: str) -> bool:
        return self._revogar(token)

    def _revogar(self, token: str) -> bool:
        try:
            resposta = self._rede("POST", URL_REVOGAR, data={"token": token})
        except ErroGoogle:
            return False
        return resposta.status_code == 200

    def desconectar(self, revogar: bool = True) -> bool:
        """Apaga aqui e revoga no Google. Devolve False se o Google não
        confirmou (aí a pessoa remove o Éden na conta do Google).

        ``revogar=False``: só apaga aqui. Usado quando a agenda e o e-mail
        estão ligados ao mesmo tempo: a revogação do Google vale para a
        autorização inteira (este app + esta conta) e, se for a mesma conta,
        derrubaria a outra ligação também (revisão de 17/10)."""
        guardado = self.cofre.ler()
        self.cofre.apagar()
        with self._lock:
            self._acesso = None
            self._geracao += 1
        if not guardado:
            return True
        if not revogar:
            return False
        revogado = self._revogar(guardado["refresh"])
        if not revogado:
            logger.warning("Éden: o Google não confirmou a revogação")
        return revogado

    def conectado(self) -> bool:
        return self.cofre.conectado()

    # acesso

    def _token_de_acesso(self, forcar: bool = False) -> str:
        with self._lock:
            if (
                not forcar
                and self._acesso
                and self._acesso[0]
                and self._acesso[1] > self._relogio()
            ):
                return self._acesso[0]
            geracao = self._geracao
        guardado = self.cofre.ler()
        if not guardado:
            raise ErroGoogle(
                f"A conta ({self.nome}) não está conectada.",
                "eden_google_desconectado",
            )
        cfg = self.cfg
        resposta = self._rede(
            "POST",
            URL_TOKEN,
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "refresh_token": guardado["refresh"],
                "grant_type": "refresh_token",
            },
        )
        if resposta.status_code in (400, 401):
            erro = ""
            try:
                erro = self._json(resposta).get("error", "")
            except ErroGoogle:
                pass
            if erro == "invalid_grant":
                self.cofre.apagar()
                raise ErroGoogle(
                    "A ligação com o Google expirou ou foi retirada. Conecte de "
                    "novo nas Configurações.",
                    "eden_google_reconectar",
                )
        if resposta.status_code != 200:
            raise ErroGoogle("O Google não respondeu agora. Tente de novo.")
        token = self._guardar_acesso(self._json(resposta), geracao)
        if not self.cofre.conectado():
            with self._lock:
                self._acesso = None
            raise ErroGoogle(
                f"A conta ({self.nome}) não está conectada.",
                "eden_google_desconectado",
            )
        return token

    def _pedir(
        self,
        metodo: str,
        url: str,
        cabecalhos: Optional[Dict[str, str]] = None,
        **kw: Any,
    ) -> Any:
        for tentativa in (0, 1):
            token = self._token_de_acesso(forcar=tentativa == 1)
            resposta = self._rede(
                metodo,
                url,
                headers={**(cabecalhos or {}), "Authorization": f"Bearer {token}"},
                **kw,
            )
            if resposta.status_code == 401 and tentativa == 0:
                continue
            if resposta.status_code == 404:
                raise ErroGoogle("Evento não encontrado na agenda.", "eden_google_404")
            if resposta.status_code == 409:
                raise ErroGoogle("Esse evento já existe.", "eden_google_409")
            if resposta.status_code == 412:
                raise ErroGoogle(
                    "O evento mudou no Google depois da sugestão. Peça de novo.",
                    "eden_google_412",
                )
            if resposta.status_code == 403 and url.startswith(
                "https://gmail.googleapis.com/"
            ):
                # Quase sempre: a Gmail API não foi ativada no projeto (19/10).
                raise ErroGoogle(
                    "O Google recusou a leitura dos e-mails (403). Confira se a "
                    "Gmail API está ativada no projeto do Google Cloud (LEIA-ME, "
                    "seção E-mail).",
                    "eden_google_403",
                )
            if resposta.status_code >= 400:
                raise ErroGoogle(f"O Google recusou o pedido ({resposta.status_code}).")
            return self._json(resposta)
        raise ErroGoogle("O Google recusou o acesso.")  # pragma: no cover

    # agenda

    def listar(
        self, inicio: datetime, fim: datetime, tz: timezone
    ) -> List[Dict[str, Any]]:
        dados = self._pedir(
            "GET",
            URL_AGENDA,
            params={
                "timeMin": inicio.isoformat(),
                "timeMax": fim.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": str(MAX_EVENTOS),
            },
        )
        itens = dados.get("items") if isinstance(dados, dict) else None
        eventos = [normalizar_evento(e, tz) for e in (itens or [])]
        return [e for e in eventos if e][:MAX_EVENTOS]

    def evento(self, evento_id: str, tz: timezone) -> Dict[str, Any]:
        if not _EVENTO_ID.fullmatch(evento_id or ""):
            raise ErroGoogle("Evento não encontrado na agenda.", "eden_google_404")
        evento = normalizar_evento(
            self._pedir("GET", f"{URL_AGENDA}/{quote(evento_id, safe='')}"), tz
        )
        if evento is None:
            raise ErroGoogle("Evento não encontrado na agenda.", "eden_google_404")
        return evento

    def criar(
        self, params: Dict[str, Any], tz: timezone, evento_id: Optional[str] = None
    ) -> Dict[str, Any]:
        corpo = corpo_do_evento(params, tz)
        if evento_id:
            corpo["id"] = evento_id
        try:
            criado = self._pedir("POST", URL_AGENDA, json=corpo)
        except ErroGoogle as exc:
            if exc.codigo == "eden_google_409" and evento_id:
                return {"evento": evento_id}  # já tinha sido criado
            raise
        evento = normalizar_evento(criado, tz)
        return {"evento": evento["id"] if evento else evento_id}

    def editar(
        self,
        evento_id: str,
        mudancas: Dict[str, Any],
        tz: timezone,
        etag: str = "",
    ) -> Dict[str, Any]:
        if not _EVENTO_ID.fullmatch(evento_id or ""):
            raise ErroGoogle("Evento não encontrado na agenda.", "eden_google_404")
        # If-Match: o Google recusa (412) se o evento mudou desde o cartão.
        self._pedir(
            "PATCH",
            f"{URL_AGENDA}/{quote(evento_id, safe='')}",
            cabecalhos={"If-Match": etag} if etag else None,
            json=mudancas,
        )
        return {"evento": evento_id}


# ── Google Drive: salvar a folha como documento (só o que o Éden cria) ──


_ID_DRIVE = re.compile(r"[A-Za-z0-9_-]{10,200}")
# Nada que busque coisas de fora ou rode código vai para o Drive.
_HTML_PROIBIDO = re.compile(
    r"<\s*(img|image|script|iframe|object|embed|link|video|audio|source)\b"
    r"|\bsrc\s*=|xlink:href|url\s*\(|javascript:|@import",
    re.IGNORECASE,
)


def tem_drive(cofre: "Cofre") -> bool:
    guardado = cofre.ler()
    return bool(guardado) and ESCOPO_DRIVE in str(guardado.get("escopo", "")).split()


def _pasta_guardada(store) -> Optional[str]:  # noqa: ANN001
    rows = store._ler(
        "SELECT valor FROM ajustes WHERE chave = ?", (AJUSTE_PASTA_DRIVE,)
    )
    valor = rows[0][0] if rows else None
    return valor if isinstance(valor, str) and _ID_DRIVE.fullmatch(valor) else None


def _guardar_pasta(store, pasta_id: str) -> None:  # noqa: ANN001
    store.transacao(
        lambda c: c.execute(
            "INSERT INTO ajustes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (AJUSTE_PASTA_DRIVE, pasta_id),
        )
    )


def corpo_multipart(metadados: Dict[str, Any], html: str) -> Tuple[bytes, str]:
    """Corpo "multipart/related" do Drive: metadados (JSON) + o HTML."""
    fronteira = "eden" + secrets.token_hex(16)
    partes = (
        f"--{fronteira}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadados, ensure_ascii=False)}\r\n"
        f"--{fronteira}\r\n"
        "Content-Type: text/html; charset=UTF-8\r\n\r\n"
    ).encode("utf-8")
    corpo = partes + html.encode("utf-8") + f"\r\n--{fronteira}--\r\n".encode()
    return corpo, f"multipart/related; boundary={fronteira}"


def _criar_pasta(cliente: "ClienteGoogle") -> str:
    criada = cliente._pedir(
        "POST",
        URL_DRIVE,
        params={"fields": "id"},
        json={
            "name": NOME_PASTA_DRIVE,
            "mimeType": "application/vnd.google-apps.folder",
        },
    )
    pasta = criada.get("id") if isinstance(criada, dict) else None
    if not isinstance(pasta, str) or not _ID_DRIVE.fullmatch(pasta):
        raise ErroGoogle("O Drive não criou a pasta do Éden.")
    _guardar_pasta(cliente.cofre.store, pasta)
    return pasta


def _pasta_existe(cliente: "ClienteGoogle", pasta: str) -> bool:
    try:
        info = cliente._pedir(
            "GET", f"{URL_DRIVE}/{pasta}", params={"fields": "id,trashed"}
        )
    except ErroGoogle as exc:
        if exc.codigo == "eden_google_404":
            return False
        raise
    return isinstance(info, dict) and not info.get("trashed")


def salvar_no_drive(cliente: "ClienteGoogle", titulo: Any, html: Any) -> Dict[str, Any]:
    """Cria um Google Docs com a folha, na pasta "Éden" do Drive."""
    from openjarvis.eden.organizacao import ErroOrganizacao, texto

    if not tem_drive(cliente.cofre):
        raise ErroGoogle(
            "O Éden ainda não tem permissão para salvar no Drive "
            "(Configurações → Google).",
            "eden_google_sem_drive",
        )
    try:
        nome = texto(titulo, "titulo", 120, uma_linha=True)
    except ErroOrganizacao as exc:
        raise ErroGoogle(str(exc), "eden_google_dados") from None
    if not isinstance(html, str) or not html.strip():
        raise ErroGoogle("A folha está vazia.", "eden_google_dados")
    if _HTML_PROIBIDO.search(html):
        # O app já tira imagens e scripts da folha; o servidor confere de novo.
        raise ErroGoogle(
            "A folha tem conteúdo que não vai para o Drive.", "eden_google_dados"
        )
    if len(html.encode("utf-8")) > MAX_HTML_DRIVE:
        raise ErroGoogle(
            "A folha é grande demais para o Drive (até 2 MB).", "eden_google_dados"
        )
    pasta = _pasta_guardada(cliente.cofre.store)
    if pasta is None or not _pasta_existe(cliente, pasta):
        pasta = _criar_pasta(cliente)
    corpo, tipo = corpo_multipart(
        {
            "name": nome,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [pasta],
        },
        html,
    )
    criado = cliente._pedir(
        "POST",
        URL_DRIVE_UPLOAD,
        cabecalhos={"Content-Type": tipo},
        params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
        content=corpo,
    )
    arquivo = criado.get("id") if isinstance(criado, dict) else None
    if not isinstance(arquivo, str) or not _ID_DRIVE.fullmatch(arquivo):
        raise ErroGoogle("O Drive não confirmou o arquivo.")
    link = criado.get("webViewLink")
    # Só devolve link do próprio Google Docs/Drive.
    if not (
        isinstance(link, str)
        and (
            link.startswith("https://docs.google.com/")
            or link.startswith("https://drive.google.com/")
        )
    ):
        link = None
    return {"id": arquivo, "nome": nome, "link": link}


# ── agenda em cache (para o contexto da IA, sem esperar o Google) ────────


class AgendaEmCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.eventos: List[Dict[str, Any]] = []
        self.atualizado_em: Optional[int] = None
        self.conectado = False
        self.geracao = 0

    def guardar(
        self,
        eventos: List[Dict[str, Any]],
        agora_ms: int,
        geracao: Optional[int] = None,
    ) -> bool:
        with self._lock:
            if geracao is not None and geracao != self.geracao:
                return False  # desconectou enquanto buscava
            self.eventos = list(eventos)
            self.atualizado_em = agora_ms
            self.conectado = True
            return True

    def limpar(self) -> None:
        with self._lock:
            self.eventos = []
            self.atualizado_em = None
            self.conectado = False
            self.geracao += 1

    def retrato(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "conectado": self.conectado,
                "eventos": list(self.eventos),
                "atualizado_em": self.atualizado_em,
            }

    def por_id(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {e["id"]: e for e in self.eventos}


CACHE = AgendaEmCache()


def janela(tz: timezone, agora: Optional[datetime] = None, dias: int = DIAS_NA_AGENDA):
    agora = agora or datetime.now(tz)
    inicio = datetime(agora.year, agora.month, agora.day, tzinfo=tz)
    return inicio, inicio + timedelta(days=dias)


def atualizar_cache(
    cliente: ClienteGoogle, tz: timezone, cache: AgendaEmCache = CACHE
) -> bool:
    """Busca os próximos dias no Google e guarda. False se não estiver ligado."""
    geracao = cache.geracao
    if not cliente.conectado():
        cache.limpar()
        return False
    inicio, fim = janela(tz)
    try:
        eventos = cliente.listar(inicio, fim, tz)
    except ErroGoogle as exc:
        if exc.codigo in ("eden_google_reconectar", "eden_google_desconectado"):
            cache.limpar()
        raise
    return cache.guardar(eventos, int(time.time() * 1000), geracao)


def _organizacao_do_app(app):  # noqa: ANN001, ANN202
    from openjarvis.eden.organizacao import get_organizacao

    return getattr(app.state, "eden_organizacao", None) or get_organizacao()


def cliente_do_app(app) -> ClienteGoogle:  # noqa: ANN001
    """Um cliente por servidor (guardado em app.state)."""
    atual = getattr(app.state, "eden_google", None)
    if atual is None:
        store = _organizacao_do_app(app)
        atual = ClienteGoogle(Cofre(store))
        app.state.eden_google = atual
    return atual


INTERVALO_AGENDA_S = 5 * 60


def registrar_agenda(app) -> None:  # noqa: ANN001
    """Atualiza a agenda em cache a cada 5 minutos (se estiver ligada)."""
    import asyncio

    from openjarvis.eden.settings import get_settings

    async def laco() -> None:
        await asyncio.sleep(10)
        while True:
            try:
                if get_settings().enabled and configuracao() is not None:
                    await asyncio.to_thread(
                        atualizar_cache, cliente_do_app(app), get_settings().tz
                    )
            except asyncio.CancelledError:
                raise
            except ErroGoogle as exc:
                logger.warning("Éden: agenda não atualizada (%s)", exc.codigo)
            except Exception:  # noqa: BLE001
                logger.exception("Éden: falha ao atualizar a agenda")
            await asyncio.sleep(INTERVALO_AGENDA_S)

    @app.on_event("startup")
    async def _ligar() -> None:  # pragma: no cover - roda com o servidor de verdade
        if get_settings().enabled:
            app.state.eden_agenda_tarefa = asyncio.create_task(laco())
