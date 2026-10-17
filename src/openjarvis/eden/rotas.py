"""Éden (Parte 4): rotas e trânsito pelo TomTom.

- Precisa da chave do TomTom no ``.env`` do servidor (``TOMTOM_API_KEY``).
  Sem a chave, nada aqui fala com a internet.
- A conta grátis do TomTom não pede cartão (20 mil rotas e 20 mil buscas de
  endereço por mês). O Éden guarda o resultado por 5 minutos.
- A pessoa salva **trajetos** (ex.: Casa → Trabalho). O TomTom recebe só as
  coordenadas de origem e destino e o texto da busca de endereço.
- A chave vai no endereço do pedido (é assim que o TomTom pede): os
  registros do httpx passam por um filtro que apaga a chave, e nenhum erro
  mostra o endereço.
- A IA recebe os tempos guardados só quando a pergunta é sobre trânsito ou
  caminho; antes dessas perguntas, o servidor atualiza os trajetos.
- **Caminhos** (alternativas): para um destino (salvo ou falado na conversa),
  o TomTom devolve até 3 caminhos com o tempo de agora e as vias principais
  de cada um. Na conversa, o ponto de partida é a localização do aparelho (se
  a pessoa ligou e permitiu) ou a origem do primeiro trajeto salvo. A
  localização não é guardada.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

from openjarvis.eden.organizacao import (
    ErroOrganizacao,
    Organizacao,
    agora_ms,
    inteiro,
    texto,
)

logger = logging.getLogger(__name__)

HOST = "api.tomtom.com"
URL_GEOCODE = f"https://{HOST}/search/2/geocode/{{q}}.json"
URL_BUSCA = f"https://{HOST}/search/2/search/{{q}}.json"
URL_ROTA = f"https://{HOST}/routing/1/calculateRoute/{{pontos}}/json"
FONTE = "TomTom"

MAX_TRAJETOS = 10
MAX_NOME = 60
MAX_BUSCA = 100
TEMPO_LIMITE_S = 10.0
TEMPO_TOTAL_S = 20.0
MAX_RESPOSTA = 1024 * 1024
CACHE_S = 5 * 60
CACHE_CONTEXTO_S = 30 * 60
MAX_ATUALIZAR_NA_CONVERSA = 3
MAX_ALTERNATIVAS = 2  # + o caminho principal = até 3
MAX_RESPOSTA_CAMINHOS = 4 * 1024 * 1024  # caminhos vêm com os pontos da rota
MAX_VIAS = 3
MAX_DESTINO = 80

_CHAVE = re.compile(r"[A-Za-z0-9]{16,64}")


class ErroRotas(Exception):
    def __init__(self, mensagem: str, codigo: str = "eden_rotas") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


class _Passageiro(Exception):
    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


# ── chave (no .env) e registros sem a chave ──────────────────────────────


def chave() -> Optional[str]:
    valor = os.environ.get("TOMTOM_API_KEY", "").strip()
    if not valor:
        return None
    if not _CHAVE.fullmatch(valor):
        logger.warning("Éden: TOMTOM_API_KEY com formato estranho")
        return None
    return valor


def configurado() -> bool:
    return chave() is not None


_KEY_NA_URL = re.compile(r"(?i)([?&]key=)[^&\s\"']+")


class _SemChaveNoRegistro(logging.Filter):
    """O httpx registra cada pedido com o endereço inteiro: tira a chave."""

    name = "openjarvis.eden.rotas.sem_chave"

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if record.args:
                record.args = tuple(
                    _KEY_NA_URL.sub(r"\1…", str(a)) if "key=" in str(a) else a
                    for a in (
                        record.args
                        if isinstance(record.args, tuple)
                        else (record.args,)
                    )
                )
            if isinstance(record.msg, str) and "key=" in record.msg:
                record.msg = _KEY_NA_URL.sub(r"\1…", record.msg)
        except Exception:  # noqa: BLE001 - registrar nunca derruba nada
            pass
        return True


for _nome in ("httpx", "httpcore"):
    _registro = logging.getLogger(_nome)
    if not any(
        getattr(f, "name", None) == _SemChaveNoRegistro.name for f in _registro.filters
    ):
        _registro.addFilter(_SemChaveNoRegistro())


# ── textos ───────────────────────────────────────────────────────────────


def _sem_acento(valor: str) -> str:
    return (
        unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode().lower()
    )


_ASSUNTO = re.compile(
    r"\b(transito|rota\w*|caminho\w*|engarraf\w*|congestion\w*|trajet\w*|"
    r"demor\w*|chegar|chego|chegada|sair|saio|saida|distancia|estrada\w*|"
    r"quanto tempo|de carro|vou pr\w*|ir pr\w*|ir para|ir ao|ir a)\b"
)


def pergunta_sobre_rotas(pergunta: Optional[str]) -> bool:
    return bool(pergunta) and bool(_ASSUNTO.search(_sem_acento(pergunta or "")))


def minutos_texto(segundos: Optional[int]) -> str:
    if segundos is None:
        return "?"
    minutos = max(1, round(segundos / 60))
    if minutos < 60:
        return f"{minutos} min"
    return f"{minutos // 60} h {minutos % 60:02d} min"


# ── trajetos (banco) ─────────────────────────────────────────────────────


def _coordenada(valor: Any, campo: str, limite: float) -> float:
    if isinstance(valor, bool):
        raise ErroOrganizacao(f"'{campo}' precisa ser um número")
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ErroOrganizacao(f"'{campo}' precisa ser um número") from None
    if not math.isfinite(numero) or abs(numero) > limite:
        raise ErroOrganizacao(f"'{campo}' fora do mapa")
    return round(numero, 6)


def _ponto(dados: Any, campo: str) -> Dict[str, Any]:
    if not isinstance(dados, dict):
        raise ErroOrganizacao(f"'{campo}' precisa de nome, latitude e longitude")
    return {
        "nome": texto(dados.get("nome"), f"{campo}.nome", 120, uma_linha=True),
        "latitude": _coordenada(dados.get("latitude"), f"{campo}.latitude", 90),
        "longitude": _coordenada(dados.get("longitude"), f"{campo}.longitude", 180),
    }


def _trajeto(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "origem": {
            "nome": row["origem_nome"],
            "latitude": row["origem_lat"],
            "longitude": row["origem_lon"],
        },
        "destino": {
            "nome": row["destino_nome"],
            "latitude": row["destino_lat"],
            "longitude": row["destino_lon"],
        },
    }


def listar_trajetos(store: Organizacao) -> List[Dict[str, Any]]:
    return [_trajeto(r) for r in store._ler("SELECT * FROM trajetos ORDER BY id")]


def trajeto(store: Organizacao, trajeto_id: Any) -> Optional[Dict[str, Any]]:
    rows = store._ler("SELECT * FROM trajetos WHERE id = ?", (inteiro(trajeto_id),))
    return _trajeto(rows[0]) if rows else None


def criar_trajeto(store: Organizacao, dados: Dict[str, Any]) -> Dict[str, Any]:
    origem = _ponto(dados.get("origem"), "origem")
    destino = _ponto(dados.get("destino"), "destino")
    nome = dados.get("nome")
    if not nome:
        nome = f"{origem['nome']} → {destino['nome']}"
        if len(nome) > MAX_NOME:
            nome = nome[: MAX_NOME - 1] + "…"
    nome = texto(nome, "nome", MAX_NOME, uma_linha=True)

    def fazer(conn: sqlite3.Connection) -> int:
        quantos = conn.execute("SELECT COUNT(*) FROM trajetos").fetchone()[0]
        if quantos >= MAX_TRAJETOS:
            raise ErroOrganizacao(f"no máximo {MAX_TRAJETOS} trajetos", 409)
        cur = conn.execute(
            "INSERT INTO trajetos (nome, origem_nome, origem_lat, origem_lon, "
            "destino_nome, destino_lat, destino_lon, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nome,
                origem["nome"],
                origem["latitude"],
                origem["longitude"],
                destino["nome"],
                destino["latitude"],
                destino["longitude"],
                agora_ms(),
            ),
        )
        return int(cur.lastrowid)

    return trajeto(store, store.transacao(fazer))  # type: ignore[return-value]


def apagar_trajeto(store: Organizacao, trajeto_id: Any) -> bool:
    tid = inteiro(trajeto_id)
    apagou = store.transacao(
        lambda c: c.execute("DELETE FROM trajetos WHERE id = ?", (tid,)).rowcount
    )
    CACHE.esquecer(tid)
    return bool(apagou)


# ── TomTom ───────────────────────────────────────────────────────────────


def _inteiro_ok(valor: Any, maximo: int) -> Optional[int]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not math.isfinite(float(valor)) or not 0 <= valor <= maximo:
        return None
    return int(valor)


_HORA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}[+\-Z0-9:.]*")


def _ler_resumo(resumo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tempo_s = _inteiro_ok(resumo.get("travelTimeInSeconds"), 7 * 24 * 3600)
    if tempo_s is None:
        return None
    chegada = resumo.get("arrivalTime")
    return {
        "segundos": tempo_s,
        "sem_transito_s": _inteiro_ok(
            resumo.get("noTrafficTravelTimeInSeconds"), 7 * 24 * 3600
        ),
        "atraso_s": _inteiro_ok(resumo.get("trafficDelayInSeconds"), 7 * 24 * 3600)
        or 0,
        "metros": _inteiro_ok(resumo.get("lengthInMeters"), 20_000_000),
        "chegada": chegada
        if isinstance(chegada, str) and _HORA.fullmatch(chegada)
        else None,
    }


def _nome_via(instrucao: Dict[str, Any]) -> str:
    from openjarvis.eden.google import limpar_externo

    nome = instrucao.get("street")
    if not isinstance(nome, str) or not nome.strip():
        numeros = instrucao.get("roadNumbers")
        nome = numeros[0] if isinstance(numeros, list) and numeros else ""
    return limpar_externo(nome, 60).replace("\n", " ").strip() if nome else ""


def vias_principais(rota: Dict[str, Any]) -> List[str]:
    """As vias mais longas do caminho (até 3), na ordem em que aparecem.

    Cada instrução do TomTom diz em que via se entra; o trecho até a
    instrução seguinte é feito nessa via."""
    guia = rota.get("guidance") if isinstance(rota.get("guidance"), dict) else {}
    instrucoes = [i for i in (guia.get("instructions") or []) if isinstance(i, dict)]
    total = _inteiro_ok((rota.get("summary") or {}).get("lengthInMeters"), 20_000_000)
    metros: Dict[str, int] = {}
    primeiro: Dict[str, int] = {}
    for atual, seguinte in zip(instrucoes, instrucoes[1:]):
        inicio = _inteiro_ok(atual.get("routeOffsetInMeters"), 20_000_000)
        fim = _inteiro_ok(seguinte.get("routeOffsetInMeters"), 20_000_000)
        nome = _nome_via(atual)
        if inicio is None or fim is None or fim <= inicio or not nome:
            continue
        metros[nome] = metros.get(nome, 0) + (fim - inicio)
        primeiro.setdefault(nome, inicio)
    minimo = max(500, int((total or 0) * 0.1))
    grandes = sorted(
        (n for n, m in metros.items() if m >= minimo),
        key=lambda n: metros[n],
        reverse=True,
    )[:MAX_VIAS]
    return sorted(grandes, key=lambda n: primeiro[n])


class CacheRotas:
    def __init__(self, relogio: Callable[[], float] = time.time) -> None:
        self._relogio = relogio
        self._lock = threading.Lock()
        self._dados: Dict[Tuple, Tuple[float, Dict[str, Any]]] = {}

    @staticmethod
    def _chave(t: Dict[str, Any]) -> Tuple:
        return (
            t["id"],
            t["origem"]["latitude"],
            t["origem"]["longitude"],
            t["destino"]["latitude"],
            t["destino"]["longitude"],
        )

    def pegar(self, t: Dict[str, Any], idade_max: float) -> Optional[Dict[str, Any]]:
        with self._lock:
            achado = self._dados.get(self._chave(t))
        if achado is None or self._relogio() - achado[0] > idade_max:
            return None
        return achado[1]

    def guardar(self, t: Dict[str, Any], resultado: Dict[str, Any]) -> None:
        with self._lock:
            self._dados[self._chave(t)] = (self._relogio(), resultado)

    def pegar_por(self, chave: Tuple, idade_max: float) -> Optional[Dict[str, Any]]:
        with self._lock:
            achado = self._dados.get(chave)
        if achado is None or self._relogio() - achado[0] > idade_max:
            return None
        return achado[1]

    def guardar_por(self, chave: Tuple, resultado: Dict[str, Any]) -> None:
        with self._lock:
            if len(self._dados) > 500:  # só memória; nunca cresce sem fim
                self._dados.clear()
            self._dados[chave] = (self._relogio(), resultado)

    def esquecer(self, trajeto_id: int) -> None:
        with self._lock:
            for k in [k for k in self._dados if k[0] == trajeto_id]:
                del self._dados[k]

    def limpar(self) -> None:
        with self._lock:
            self._dados.clear()


CACHE = CacheRotas()


class ClienteTomTom:
    """Só fala com api.tomtom.com, nos três caminhos fixos acima."""

    def __init__(self, http: Any = None, cache: CacheRotas = CACHE) -> None:
        self._http = http
        self.cache = cache

    def _cliente_http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=TEMPO_LIMITE_S, follow_redirects=False)
        return self._http

    def _get(
        self, url: str, params: Dict[str, Any], maximo: int = MAX_RESPOSTA
    ) -> Dict[str, Any]:
        if not url.startswith(f"https://{HOST}/"):
            raise ErroRotas("endereço não permitido")
        k = chave()
        if k is None:
            raise ErroRotas(
                "As rotas ainda não foram configuradas (falta a chave do TomTom).",
                "eden_rotas_sem_chave",
            )
        for tentativa in (1, 2):
            try:
                return self._get_uma_vez(url, {**params, "key": k}, maximo)
            except _Passageiro as exc:
                logger.warning(
                    "Éden: TomTom sem resposta (%s, tentativa %d)",
                    exc.motivo,
                    tentativa,
                )
                if tentativa == 2:
                    raise ErroRotas(
                        "Sem resposta do TomTom agora. Tente de novo.",
                        "eden_rotas_rede",
                    ) from None
                time.sleep(1)
        raise ErroRotas("Sem resposta do TomTom agora.")  # pragma: no cover

    def _get_uma_vez(
        self, url: str, params: Dict[str, Any], maximo: int = MAX_RESPOSTA
    ) -> Dict[str, Any]:
        inicio = time.monotonic()
        try:
            with self._cliente_http().stream(
                "GET", url, params=params, headers={"Accept-Encoding": "identity"}
            ) as resposta:
                status = resposta.status_code
                if status >= 500:
                    raise _Passageiro(f"erro {status}")
                if status in (401, 403):
                    raise ErroRotas(
                        "O TomTom recusou a chave (confira a TOMTOM_API_KEY no .env).",
                        "eden_rotas_chave",
                    )
                if status == 429:
                    raise ErroRotas(
                        "Limite do TomTom atingido por agora. Tente mais tarde.",
                        "eden_rotas_limite",
                    )
                if status != 200:
                    raise ErroRotas(f"O TomTom recusou o pedido ({status}).")
                pedacos = []
                tamanho = 0
                for pedaco in resposta.iter_bytes():
                    tamanho += len(pedaco)
                    if tamanho > maximo:
                        raise ErroRotas("Resposta grande demais do TomTom.")
                    if time.monotonic() - inicio > TEMPO_TOTAL_S:
                        raise _Passageiro("demorou demais")
                    pedacos.append(pedaco)
        except (ErroRotas, _Passageiro):
            raise
        except Exception as exc:  # noqa: BLE001 - rede; nunca mostra o endereço
            raise _Passageiro(type(exc).__name__) from None
        try:
            dados = json.loads(b"".join(pedacos))
        except (ValueError, RecursionError):
            raise ErroRotas("Resposta estranha do TomTom.") from None
        if not isinstance(dados, dict):
            raise ErroRotas("Resposta estranha do TomTom.")
        return dados

    def buscar(
        self, consulta: str, perto: Optional[Tuple[float, float]] = None
    ) -> List[Dict[str, Any]]:
        """Endereço ou lugar pelo nome (Brasil). Primeiro o geocode (endereços);
        se não achar, a busca de lugares (praias, shoppings…). ``perto`` dá
        preferência a resultados perto desse ponto."""
        consulta = texto(consulta, "busca", MAX_BUSCA, uma_linha=True)
        if len(consulta) < 3:
            return []
        params: Dict[str, Any] = {"limit": 6, "countrySet": "BR", "language": "pt-BR"}
        if perto is not None:
            params["lat"] = f"{perto[0]:.3f}"
            params["lon"] = f"{perto[1]:.3f}"
        q = quote(consulta, safe="")
        resultados = self._resultados(self._get(URL_GEOCODE.format(q=q), params))
        if not resultados:
            resultados = self._resultados(self._get(URL_BUSCA.format(q=q), params))
        return resultados

    @staticmethod
    def _resultados(dados: Dict[str, Any]) -> List[Dict[str, Any]]:
        saida = []
        for r in dados.get("results") or []:
            if not isinstance(r, dict):
                continue
            pos = r.get("position") if isinstance(r.get("position"), dict) else {}
            lat, lon = pos.get("lat"), pos.get("lon")
            if (
                isinstance(lat, bool)
                or isinstance(lon, bool)
                or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float))
                or not math.isfinite(lat)
                or not math.isfinite(lon)
                or abs(lat) > 90
                or abs(lon) > 180
            ):
                continue
            endereco = r.get("address") if isinstance(r.get("address"), dict) else {}
            poi = r.get("poi") if isinstance(r.get("poi"), dict) else {}
            nome = poi.get("name") or endereco.get("freeformAddress") or ""
            try:
                saida.append(
                    {
                        "nome": texto(nome, "nome", 120, uma_linha=True),
                        "endereco": texto(
                            endereco.get("freeformAddress") or "",
                            "endereco",
                            200,
                            obrigatorio=False,
                            uma_linha=True,
                        ),
                        "latitude": round(float(lat), 6),
                        "longitude": round(float(lon), 6),
                    }
                )
            except ErroOrganizacao:
                continue
        return saida[:6]

    def tempo(self, t: Dict[str, Any], forcar: bool = False) -> Dict[str, Any]:
        """Tempo agora, com trânsito, do trajeto (guardado por 5 minutos)."""
        if not forcar:
            guardado = self.cache.pegar(t, CACHE_S)
            if guardado is not None:
                return guardado
        pontos = "{:.6f},{:.6f}:{:.6f},{:.6f}".format(
            t["origem"]["latitude"],
            t["origem"]["longitude"],
            t["destino"]["latitude"],
            t["destino"]["longitude"],
        )
        dados = self._get(
            URL_ROTA.format(pontos=pontos),
            {
                "traffic": "true",
                "travelMode": "car",
                "routeType": "fastest",
                "computeTravelTimeFor": "all",
            },
        )
        rotas = dados.get("routes")
        resumo = (
            rotas[0].get("summary")
            if isinstance(rotas, list) and rotas and isinstance(rotas[0], dict)
            else None
        )
        if not isinstance(resumo, dict):
            raise ErroRotas("O TomTom não achou caminho entre esses pontos.")
        resultado = _ler_resumo(resumo)
        if resultado is None:
            raise ErroRotas("Resposta estranha do TomTom.")
        resultado.update({"calculado_em": agora_ms(), "fonte": FONTE})
        self.cache.guardar(t, resultado)
        return resultado

    def caminhos(
        self,
        origem: Dict[str, Any],
        destino: Dict[str, Any],
        forcar: bool = False,
    ) -> Dict[str, Any]:
        """Até 3 caminhos de carro, com o trânsito de agora e as vias
        principais de cada um (o mais rápido primeiro). Guardado 5 minutos."""
        o = (
            _coordenada(origem.get("latitude"), "origem.latitude", 90),
            _coordenada(origem.get("longitude"), "origem.longitude", 180),
        )
        d = (
            _coordenada(destino.get("latitude"), "destino.latitude", 90),
            _coordenada(destino.get("longitude"), "destino.longitude", 180),
        )
        chave_cache = (
            "caminhos",
            round(o[0], 5),
            round(o[1], 5),
            round(d[0], 5),
            round(d[1], 5),
        )
        if not forcar:
            guardado = self.cache.pegar_por(chave_cache, CACHE_S)
            if guardado is not None:
                return guardado
        pontos = "{:.6f},{:.6f}:{:.6f},{:.6f}".format(o[0], o[1], d[0], d[1])
        dados = self._get(
            URL_ROTA.format(pontos=pontos),
            {
                "traffic": "true",
                "travelMode": "car",
                "routeType": "fastest",
                "computeTravelTimeFor": "all",
                "maxAlternatives": str(MAX_ALTERNATIVAS),
                "alternativeType": "anyRoute",
                "instructionsType": "text",
                "language": "pt-BR",
            },
            MAX_RESPOSTA_CAMINHOS,
        )
        lista = []
        for rota in (dados.get("routes") or [])[: MAX_ALTERNATIVAS + 1]:
            if not isinstance(rota, dict) or not isinstance(rota.get("summary"), dict):
                continue
            resumo = _ler_resumo(rota["summary"])
            if resumo is None:
                continue
            resumo["vias"] = vias_principais(rota)
            lista.append(resumo)
        if not lista:
            raise ErroRotas("O TomTom não achou caminho entre esses pontos.")
        lista.sort(key=lambda r: r["segundos"])
        resultado = {"rotas": lista, "calculado_em": agora_ms(), "fonte": FONTE}
        self.cache.guardar_por(chave_cache, resultado)
        return resultado


def cliente_do_app(app) -> ClienteTomTom:  # noqa: ANN001
    atual = getattr(app.state, "eden_rotas", None)
    if atual is None:
        atual = ClienteTomTom()
        app.state.eden_rotas = atual
    return atual


# ── contexto da IA ───────────────────────────────────────────────────────


def atualizar_para_pergunta(
    store: Organizacao, pergunta: Optional[str], cliente: ClienteTomTom
) -> int:
    """Antes de uma pergunta sobre trânsito: atualiza os trajetos (até 3)."""
    if not pergunta_sobre_rotas(pergunta) or not configurado():
        return 0
    feitos = 0
    for t in listar_trajetos(store)[:MAX_ATUALIZAR_NA_CONVERSA]:
        try:
            cliente.tempo(t)
            feitos += 1
        except ErroRotas as exc:
            logger.warning("Éden: trajeto não atualizado (%s)", exc.codigo)
    return feitos


# ── destino falado na conversa ───────────────────────────────────────────

_ANTES_DO_DESTINO = re.compile(
    r"(?:\b(?:chegar|chego|ir|vou)\s+(?:n[oa]s?|em|ao|à)\b|\bpara\s+(?:o|a|os|as)\b|\bat[eé]\s+(?:o|a|os|as)\b|\bpra\b|\bpro\b|"
    r"\bpras\b|\bpros\b|\bat[eé]\b|\bpara\b|\baos?\b|\bàs?\b)\s+",
    re.IGNORECASE,
)
_NAO_E_LUGAR = re.compile(
    r"^(?:ir|chegar|voltar|sair|ver|saber|pegar|fazer|dirigir|andar|me|mim|eu|"
    r"voc[eê]|que|o|a|os|as|l[aá]|aqui|ali)\b",
    re.IGNORECASE,
)
_FIM_DO_DESTINO = re.compile(
    r"[?!.,;:]|\s(?:que|agora|hoje|amanh[ãa]|de carro|pelo|pela|por|saindo|"
    r"partindo|e|com|daqui|j[aá]|neste|nesse|nesta|nessa)\b",
    re.IGNORECASE,
)


def destino_da_pergunta(pergunta: Optional[str]) -> Optional[str]:
    """ "melhor rota agora pro posto 4 da Barra?" → "posto 4 da Barra".

    Pega o último "para/pra/pro/até/ao" seguido de um lugar (não de um
    verbo como "ir")."""
    if not pergunta_sobre_rotas(pergunta):
        return None
    texto_p = " ".join((pergunta or "").split())[:400]
    candidatos = []
    for achado in _ANTES_DO_DESTINO.finditer(texto_p):
        resto = texto_p[achado.end() :]
        if not resto or _NAO_E_LUGAR.match(resto):
            continue
        fim = _FIM_DO_DESTINO.search(resto)
        lugar = (resto[: fim.start()] if fim else resto).strip(" \"'")
        if 3 <= len(lugar) <= MAX_DESTINO:
            candidatos.append(lugar)
    return candidatos[-1] if candidatos else None


def _parecido(a: str, b: str) -> bool:
    a, b = _sem_acento(a).strip(), _sem_acento(b).strip()
    return len(a) >= 3 and len(b) >= 3 and (a in b or b in a)


def _ponto_simples(p: Dict[str, Any], nome: Optional[str] = None) -> Dict[str, Any]:
    return {
        "nome": nome or p["nome"],
        "latitude": p["latitude"],
        "longitude": p["longitude"],
    }


def _perto_demais(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    # ~100 m: mesma lugar (não faz sentido pedir caminho).
    return (
        abs(a["latitude"] - b["latitude"]) < 0.001
        and abs(a["longitude"] - b["longitude"]) < 0.001
    )


def ler_local(valor: Any) -> Optional[Dict[str, Any]]:
    """Localização mandada pelo app ("lat,lon"), arredondada (~10 m)."""
    if not isinstance(valor, str) or len(valor) > 60:
        return None
    partes = valor.split(",")
    if len(partes) != 2:
        return None
    try:
        lat = _coordenada(partes[0], "latitude", 90)
        lon = _coordenada(partes[1], "longitude", 180)
    except ErroOrganizacao:
        return None
    return {
        "nome": "sua localização agora",
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
    }


def preparar_caminhos(
    store: Organizacao,
    pergunta: Optional[str],
    cliente: "ClienteTomTom",
    local: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Antes de uma pergunta como "melhor caminho para X agora?": acha o
    destino (trajeto salvo ou busca do endereço), o ponto de partida
    (localização do aparelho ou origem do primeiro trajeto) e pede os
    caminhos ao TomTom. Devolve o que vai para o contexto da IA."""
    if not configurado():
        return None
    lugar = destino_da_pergunta(pergunta)
    if lugar is None:
        return None
    trajetos = listar_trajetos(store)
    destino = origem = None
    # 1) destino de um trajeto; 2) origem de um trajeto ("pra casa" com Casa →
    # Trabalho = o caminho de volta); 3) nome do trajeto (ex.: "Praia").
    for campo, ida in (("destino", True), ("origem", False), ("nome", True)):
        for t in trajetos:
            nome = t["nome"] if campo == "nome" else t[campo]["nome"]
            if _parecido(lugar, nome):
                de, para = (
                    (t["origem"], t["destino"]) if ida else (t["destino"], t["origem"])
                )
                destino = _ponto_simples(para)
                origem = local or _ponto_simples(de)
                break
        if destino is not None:
            break
    if destino is None:
        origem = local or (_ponto_simples(trajetos[0]["origem"]) if trajetos else None)
        perto = (origem["latitude"], origem["longitude"]) if origem else None
        try:
            achados = cliente.buscar(lugar, perto)
        except (ErroRotas, ErroOrganizacao) as exc:
            return {"lugar": lugar, "erro": str(exc)}
        if not achados:
            return {"lugar": lugar, "erro": "o TomTom não achou esse lugar"}
        primeiro = achados[0]
        destino = _ponto_simples(primeiro)
        destino["endereco"] = primeiro.get("endereco") or ""
    if origem is None:
        return {"lugar": lugar, "destino": destino, "erro": "sem_origem"}
    if _perto_demais(origem, destino):
        return {
            "lugar": lugar,
            "destino": destino,
            "origem": origem,
            "erro": "a origem e o destino são o mesmo lugar",
        }
    try:
        achado = cliente.caminhos(origem, destino)
    except (ErroRotas, ErroOrganizacao) as exc:
        return {"lugar": lugar, "destino": destino, "origem": origem, "erro": str(exc)}
    return {
        "lugar": lugar,
        "destino": destino,
        "origem": origem,
        "rotas": achado["rotas"],
        "calculado_em": achado["calculado_em"],
    }


def _linha_caminho(numero: int, r: Dict[str, Any]) -> str:
    partes = [f"{minutos_texto(r['segundos'])} agora"]
    if r.get("atraso_s"):
        partes.append(f"+{minutos_texto(r['atraso_s'])} de trânsito")
    if r.get("metros"):
        partes.append(f"{r['metros'] / 1000:.1f} km".replace(".", ","))
    if r.get("vias"):
        partes.append(
            "via " + ", ".join(json.dumps(v, ensure_ascii=False) for v in r["vias"])
        )
    if r.get("chegada"):
        partes.append(f"chegada ~{r['chegada'][11:16]}")
    return f"{numero}) " + "; ".join(partes)


def secao_caminhos(caminhos: Optional[Dict[str, Any]]) -> str:
    if not caminhos:
        return ""
    lugar = json.dumps(caminhos.get("lugar", ""), ensure_ascii=False)
    destino = caminhos.get("destino")
    erro = caminhos.get("erro")
    if erro == "sem_origem":
        return (
            f"## Caminhos\nA pessoa pediu caminho para {lugar}, mas não sei de onde "
            "ela sai: não há trajeto salvo e a localização do aparelho está "
            'desligada. Diga que dá para ligar "usar minha localização" na '
            "página Rotas e trânsito, ou salvar um trajeto. Não invente caminho."
        )
    if erro:
        return (
            f"## Caminhos\nNão consegui os caminhos para {lugar} agora "
            f"({json.dumps(erro, ensure_ascii=False)}). Não invente caminho nem tempo."
        )
    origem = caminhos["origem"]
    nome_destino = json.dumps(destino["nome"], ensure_ascii=False)
    endereco = destino.get("endereco")
    linhas = [
        f"## Caminhos agora (dados do {FONTE}, de carro)",
        f"De: {json.dumps(origem['nome'], ensure_ascii=False)} → Para: {nome_destino}"
        + (f" ({json.dumps(endereco, ensure_ascii=False)})" if endereco else ""),
    ]
    for numero, r in enumerate(caminhos.get("rotas") or [], 1):
        linhas.append(_linha_caminho(numero, r))
    linhas.append(
        "Diga qual caminho é o mais rápido agora e quanto ganha em relação aos "
        "outros, citando as vias principais. Use só esses caminhos e nomes de "
        "vias (vieram do TomTom); não invente outros. Diga de onde para onde foi "
        "calculado; se o destino entendido parecer errado, peça para confirmar."
    )
    return "\n".join(linhas)


def _linha_tempo(t: Dict[str, Any], r: Dict[str, Any]) -> str:
    partes = [f"{minutos_texto(r['segundos'])} agora"]
    if r.get("sem_transito_s"):
        partes.append(f"sem trânsito {minutos_texto(r['sem_transito_s'])}")
    if r.get("atraso_s"):
        partes.append(f"+{minutos_texto(r['atraso_s'])} de trânsito")
    if r.get("metros"):
        partes.append(f"{r['metros'] / 1000:.1f} km".replace(".", ","))
    if r.get("chegada"):
        partes.append(f"chegada ~{r['chegada'][11:16]} se sair agora")
    nome = json.dumps(t["nome"], ensure_ascii=False)
    return f"- {nome}: " + "; ".join(partes)


def secao_contexto(
    store: Organizacao,
    pergunta: Optional[str],
    caminhos: Optional[Dict[str, Any]] = None,
) -> str:
    if not pergunta_sobre_rotas(pergunta):
        return ""
    extra = secao_caminhos(caminhos) if configurado() else ""
    base = _secao_trajetos(store)
    return base + ("\n\n" + extra if extra else "")


def _secao_trajetos(store: Organizacao) -> str:
    if not configurado():
        return (
            "## Trânsito\nRotas não configuradas (falta a chave do TomTom). Não "
            "invente tempo de viagem."
        )
    trajetos = listar_trajetos(store)
    if not trajetos:
        return (
            "## Trânsito\nNenhum trajeto salvo. Para outro destino, a pessoa pode "
            'perguntar "melhor caminho para <lugar>". Não invente tempo.'
        )
    linhas = [f"## Trânsito agora (dados do {FONTE}, de carro)"]
    for t in trajetos:
        r = CACHE.pegar(t, CACHE_CONTEXTO_S)
        if r is None:
            linhas.append(
                f"- {json.dumps(t['nome'], ensure_ascii=False)}: sem dado agora"
            )
        else:
            linhas.append(_linha_tempo(t, r))
    linhas.append(
        "Esses são os trajetos salvos. Para outro destino, a pessoa pode perguntar "
        '"melhor caminho para <lugar>" (o Éden calcula na hora); não invente '
        "tempo."
    )
    return "\n".join(linhas)
