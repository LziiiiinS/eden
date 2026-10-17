"""Éden (Parte 4): clima, vento e ondas pelo Open-Meteo.

- Começa **desligado**. A pessoa liga pela página Clima: é a aprovação dela
  para o Éden consultar o Open-Meteo.
- O Open-Meteo é grátis para uso pessoal sem fins comerciais, sem conta e
  sem chave. Os dados são CC BY 4.0 (a tela mostra a fonte).
- O que sai do Éden: só as coordenadas dos lugares cadastrados (e o nome
  digitado na busca de lugares). Nada da conversa.
- Endereços fixos do Open-Meteo; os números que voltam são conferidos.
- A IA só recebe a previsão quando a pergunta é sobre tempo, vento ou mar,
  e só do que já está guardado (a conversa nunca espera o Open-Meteo).
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple

from openjarvis.eden.organizacao import (
    ErroOrganizacao,
    Organizacao,
    agora_ms,
    inteiro,
    texto,
)

logger = logging.getLogger(__name__)

URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"
URL_MAR = "https://marine-api.open-meteo.com/v1/marine"
URL_BUSCA = "https://geocoding-api.open-meteo.com/v1/search"
FONTE = "Open-Meteo (CC BY 4.0)"

AJUSTE_LIGADO = "clima_ligado"
TIPOS_LUGAR = ("cidade", "praia")
MAX_LUGARES = 10
MAX_NOME_LUGAR = 60
TEMPO_LIMITE_S = 10.0
TEMPO_TOTAL_S = 20.0  # prazo da chamada inteira (não só de cada etapa)
MAX_RESPOSTA = 2 * 1024 * 1024
# Coordenadas no pedido com 2 casas (~1 km): o Open-Meteo não precisa do
# endereço exato (as grades dos modelos são de quilômetros).
CASAS_NO_PEDIDO = 2
DIAS = 3
CACHE_S = 30 * 60
CACHE_CONTEXTO_S = 6 * 3600  # na conversa, aceita previsão de até 6 h
INTERVALO_S = 60 * 60

_HORA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", re.ASCII)
_DIA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)

HORARIAS = (
    "temperature_2m",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
)
DIARIAS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
)
MARINHAS = (
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "swell_wave_period",
    "swell_wave_direction",
)
# Nome no Éden ← nome no Open-Meteo.
_CAMPOS_HORA = {
    "temperatura": "temperature_2m",
    "chuva_prob": "precipitation_probability",
    "chuva_mm": "precipitation",
    "codigo": "weather_code",
    "vento_kmh": "wind_speed_10m",
    "rajada_kmh": "wind_gusts_10m",
    "vento_dir": "wind_direction_10m",
}
_CAMPOS_MAR = {
    "ondas_m": "wave_height",
    "ondas_s": "wave_period",
    "ondas_dir": "wave_direction",
    "swell_m": "swell_wave_height",
    "swell_s": "swell_wave_period",
    "swell_dir": "swell_wave_direction",
}
_CAMPOS_DIA = {
    "codigo": "weather_code",
    "max": "temperature_2m_max",
    "min": "temperature_2m_min",
    "chuva_mm": "precipitation_sum",
    "chuva_prob": "precipitation_probability_max",
    "vento_kmh": "wind_speed_10m_max",
    "rajada_kmh": "wind_gusts_10m_max",
    "vento_dir": "wind_direction_10m_dominant",
}

TEMPO = {
    0: "céu limpo",
    1: "quase limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina",
    51: "garoa fraca",
    53: "garoa",
    55: "garoa forte",
    56: "garoa congelante",
    57: "garoa congelante",
    61: "chuva fraca",
    63: "chuva",
    65: "chuva forte",
    66: "chuva congelante",
    67: "chuva congelante",
    71: "neve fraca",
    73: "neve",
    75: "neve forte",
    77: "grãos de neve",
    80: "pancadas fracas",
    81: "pancadas de chuva",
    82: "pancadas fortes",
    85: "neve",
    86: "neve forte",
    95: "trovoada",
    96: "trovoada com granizo",
    99: "trovoada com granizo",
}
_RUMOS = ("N", "NE", "L", "SE", "S", "SO", "O", "NO")


class _Passageiro(Exception):
    """Falha de rede ou 5xx: vale tentar de novo uma vez."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class ErroClima(Exception):
    def __init__(self, mensagem: str, codigo: str = "eden_clima") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


# ── textos ───────────────────────────────────────────────────────────────


def rumo(graus: Optional[float]) -> str:
    """Direção de onde vem (vento/onda): 0° = N, 90° = L…"""
    if graus is None:
        return "?"
    return _RUMOS[int(((graus % 360) + 22.5) // 45) % 8]


def nos(kmh: Optional[float]) -> Optional[int]:
    return None if kmh is None else round(kmh / 1.852)


def descricao(codigo: Optional[float]) -> str:
    if codigo is None:
        return ""
    return TEMPO.get(int(codigo), "")


def _sem_acento(valor: str) -> str:
    return (
        unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode().lower()
    )


_ASSUNTO = re.compile(
    r"\b(tempo|clima|chuv\w*|chove\w*|sol|ensolarad\w*|nublad\w*|frio|calor|"
    r"temperatura\w*|graus|previsao|vent\w*|rajada\w*|onda\w*|mar|swell|surf\w*|"
    r"kite\w*|praia\w*|tempestade\w*|trovoada\w*|garoa|guarda.?chuva|"
    r"maritimo|marinho|ondulacao)\b"
)


def pergunta_sobre_clima(pergunta: Optional[str]) -> bool:
    return bool(pergunta) and bool(_ASSUNTO.search(_sem_acento(pergunta or "")))


# ── lugares (banco) ──────────────────────────────────────────────────────


def ligado(store: Organizacao) -> bool:
    rows = store._ler("SELECT valor FROM ajustes WHERE chave = ?", (AJUSTE_LIGADO,))
    return bool(rows) and rows[0][0] == "1"


def definir_ligado(store: Organizacao, valor: bool) -> bool:
    store.transacao(
        lambda c: c.execute(
            "INSERT INTO ajustes (chave, valor) VALUES (?, ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (AJUSTE_LIGADO, "1" if valor else "0"),
        )
    )
    if not valor:
        CACHE.limpar()
    return valor


def coordenada(valor: Any, campo: str, limite: float) -> float:
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
    return round(numero, 4)


def _lugar(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "nome": row["nome"],
        "tipo": row["tipo"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "principal": bool(row["principal"]),
    }


def listar_lugares(store: Organizacao) -> List[Dict[str, Any]]:
    rows = store._ler("SELECT * FROM lugares ORDER BY principal DESC, criado_em, id")
    return [_lugar(r) for r in rows]


def lugar(store: Organizacao, lugar_id: Any) -> Optional[Dict[str, Any]]:
    rows = store._ler("SELECT * FROM lugares WHERE id = ?", (inteiro(lugar_id),))
    return _lugar(rows[0]) if rows else None


def criar_lugar(store: Organizacao, dados: Dict[str, Any]) -> Dict[str, Any]:
    nome = texto(dados.get("nome"), "nome", MAX_NOME_LUGAR, uma_linha=True)
    tipo = dados.get("tipo") or "cidade"
    if tipo not in TIPOS_LUGAR:
        raise ErroOrganizacao("'tipo' precisa ser cidade ou praia")
    lat = coordenada(dados.get("latitude"), "latitude", 90)
    lon = coordenada(dados.get("longitude"), "longitude", 180)

    def fazer(conn: sqlite3.Connection) -> int:
        quantos = conn.execute("SELECT COUNT(*) FROM lugares").fetchone()[0]
        if quantos >= MAX_LUGARES:
            raise ErroOrganizacao(f"no máximo {MAX_LUGARES} lugares", 409)
        cur = conn.execute(
            "INSERT INTO lugares (nome, tipo, latitude, longitude, principal, "
            "criado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (nome, tipo, lat, lon, int(quantos == 0), agora_ms()),
        )
        return int(cur.lastrowid)

    return lugar(store, store.transacao(fazer))  # type: ignore[return-value]


def apagar_lugar(store: Organizacao, lugar_id: Any) -> bool:
    lid = inteiro(lugar_id)

    def fazer(conn: sqlite3.Connection) -> bool:
        era = conn.execute(
            "SELECT principal FROM lugares WHERE id = ?", (lid,)
        ).fetchone()
        if era is None:
            return False
        conn.execute("DELETE FROM lugares WHERE id = ?", (lid,))
        if era[0]:
            conn.execute(
                "UPDATE lugares SET principal = 1 WHERE id = "
                "(SELECT id FROM lugares ORDER BY criado_em, id LIMIT 1)"
            )
        return True

    apagou = store.transacao(fazer)
    CACHE.esquecer(lid)
    return apagou


def tornar_principal(store: Organizacao, lugar_id: Any) -> Dict[str, Any]:
    lid = inteiro(lugar_id)

    def fazer(conn: sqlite3.Connection) -> None:
        if not conn.execute("SELECT 1 FROM lugares WHERE id = ?", (lid,)).fetchone():
            raise ErroOrganizacao("lugar não encontrado", 404)
        conn.execute("UPDATE lugares SET principal = (id = ?)", (lid,))

    store.transacao(fazer)
    return lugar(store, lid)  # type: ignore[return-value]


# ── Open-Meteo ───────────────────────────────────────────────────────────


def _numero(valor: Any) -> Optional[float]:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


# Faixas plausíveis: fora delas, o valor vira vazio (nada de 1e308 no
# contexto da IA).
_FAIXAS = {
    "temperature_2m": (-90, 60),
    "temperature_2m_max": (-90, 60),
    "temperature_2m_min": (-90, 60),
    "precipitation_probability": (0, 100),
    "precipitation_probability_max": (0, 100),
    "precipitation": (0, 500),
    "precipitation_sum": (0, 2000),
    "weather_code": (0, 99),
    "wind_speed_10m": (0, 400),
    "wind_speed_10m_max": (0, 400),
    "wind_gusts_10m": (0, 500),
    "wind_gusts_10m_max": (0, 500),
    "wind_direction_10m": (0, 360),
    "wind_direction_10m_dominant": (0, 360),
    "wave_height": (0, 40),
    "swell_wave_height": (0, 40),
    "wave_period": (0, 60),
    "swell_wave_period": (0, 60),
    "wave_direction": (0, 360),
    "swell_wave_direction": (0, 360),
}


def _serie(bloco: Any, nome: str, tamanho: int) -> List[Optional[float]]:
    valores = bloco.get(nome) if isinstance(bloco, dict) else None
    if not isinstance(valores, list):
        return [None] * tamanho
    minimo, maximo = _FAIXAS.get(nome, (-1e6, 1e6))
    saida = []
    for v in valores[:tamanho]:
        numero = _numero(v)
        saida.append(
            numero if numero is not None and minimo <= numero <= maximo else None
        )
    return saida + [None] * (tamanho - len(saida))


def _tempos(bloco: Any, padrao: re.Pattern) -> List[str]:
    tempos = bloco.get("time") if isinstance(bloco, dict) else None
    if not isinstance(tempos, list):
        return []
    saida = []
    for t in tempos:
        if not isinstance(t, str) or not padrao.fullmatch(t):
            break
        saida.append(t)
    return saida


def montar_previsao(
    tempo: Dict[str, Any], mar: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Respostas do Open-Meteo → previsão do Éden (só números conferidos)."""
    horas_t = _tempos(tempo.get("hourly"), _HORA)[: DIAS * 24]
    horas = [{"hora": t} for t in horas_t]
    for nosso, deles in _CAMPOS_HORA.items():
        for item, valor in zip(horas, _serie(tempo.get("hourly"), deles, len(horas))):
            item[nosso] = valor
    if mar:
        mar_t = _tempos(mar.get("hourly"), _HORA)
        indice = {t: i for i, t in enumerate(mar_t)}
        series = {
            nosso: _serie(mar.get("hourly"), deles, len(mar_t))
            for nosso, deles in _CAMPOS_MAR.items()
        }
        for item in horas:
            i = indice.get(item["hora"])
            for nosso, serie in series.items():
                item[nosso] = serie[i] if i is not None else None
    dias_t = _tempos(tempo.get("daily"), _DIA)[:DIAS]
    dias = [{"dia": t} for t in dias_t]
    for nosso, deles in _CAMPOS_DIA.items():
        for item, valor in zip(dias, _serie(tempo.get("daily"), deles, len(dias))):
            item[nosso] = valor
    return {"horas": horas, "dias": dias, "mar": bool(mar)}


class CacheClima:
    def __init__(self, relogio: Callable[[], float] = time.time) -> None:
        self._relogio = relogio
        self._lock = threading.Lock()
        self._dados: Dict[Tuple[int, float, float], Tuple[float, Dict[str, Any]]] = {}

    @staticmethod
    def _chave(item: Dict[str, Any]) -> Tuple[int, float, float]:
        return (item["id"], item["latitude"], item["longitude"])

    def pegar(self, item: Dict[str, Any], idade_max: float) -> Optional[Dict[str, Any]]:
        with self._lock:
            achado = self._dados.get(self._chave(item))
        if achado is None or self._relogio() - achado[0] > idade_max:
            return None
        return achado[1]

    def guardar(self, item: Dict[str, Any], previsao: Dict[str, Any]) -> None:
        with self._lock:
            self._dados[self._chave(item)] = (self._relogio(), previsao)

    def esquecer(self, lugar_id: int) -> None:
        with self._lock:
            for chave in [k for k in self._dados if k[0] == lugar_id]:
                del self._dados[chave]

    def limpar(self) -> None:
        with self._lock:
            self._dados.clear()


CACHE = CacheClima()


class ClienteClima:
    """Só fala com os três endereços fixos do Open-Meteo."""

    def __init__(self, http: Any = None, cache: CacheClima = CACHE) -> None:
        self._http = http
        self.cache = cache

    def _cliente_http(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=TEMPO_LIMITE_S, follow_redirects=False)
        return self._http

    def _get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Uma consulta ao Open-Meteo. Falha de rede ou erro 5xx tenta mais
        uma vez (falhas passageiras acontecem); o resto vira ErroClima."""
        if url not in (URL_PREVISAO, URL_MAR, URL_BUSCA):
            raise ErroClima("endereço não permitido")
        for tentativa in (1, 2):
            try:
                return self._get_uma_vez(url, params)
            except _Passageiro as exc:
                logger.warning(
                    "Éden: Open-Meteo sem resposta (%s, tentativa %d)",
                    exc.motivo,
                    tentativa,
                )
                if tentativa == 2:
                    raise ErroClima(
                        "Sem resposta do serviço de previsão agora. Tente de novo.",
                        "eden_clima_rede",
                    ) from exc
                time.sleep(1)
        raise ErroClima(
            "Sem resposta do serviço de previsão agora."
        )  # pragma: no cover

    def _get_uma_vez(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        inicio = time.monotonic()
        try:
            # Lê em pedaços, contando: para no teto (sem descompactar, com
            # Accept-Encoding: identity) e no prazo total.
            with self._cliente_http().stream(
                "GET", url, params=params, headers={"Accept-Encoding": "identity"}
            ) as resposta:
                if resposta.status_code >= 500:
                    raise _Passageiro(f"erro {resposta.status_code}")
                if resposta.status_code != 200:
                    raise ErroClima(
                        "O serviço de previsão recusou o pedido "
                        f"({resposta.status_code})."
                    )
                pedacos = []
                tamanho = 0
                for pedaco in resposta.iter_bytes():
                    tamanho += len(pedaco)
                    if tamanho > MAX_RESPOSTA:
                        raise ErroClima(
                            "Resposta grande demais do serviço de previsão."
                        )
                    if time.monotonic() - inicio > TEMPO_TOTAL_S:
                        raise ErroClima(
                            "O serviço de previsão demorou demais.", "eden_clima_rede"
                        )
                    pedacos.append(pedaco)
        except (ErroClima, _Passageiro):
            raise
        except Exception as exc:  # noqa: BLE001 - rede, tempo esgotado
            raise _Passageiro(type(exc).__name__) from exc
        try:
            dados = json.loads(b"".join(pedacos))
        except (ValueError, RecursionError) as exc:
            raise ErroClima("Resposta estranha do serviço de previsão.") from exc
        if not isinstance(dados, dict):
            raise ErroClima("Resposta estranha do serviço de previsão.")
        return dados

    def buscar(self, nome: str) -> List[Dict[str, Any]]:
        nome = texto(nome, "nome", MAX_NOME_LUGAR, uma_linha=True)
        if len(nome) < 2:
            return []
        dados = self._get(
            URL_BUSCA, {"name": nome, "count": 8, "language": "pt", "format": "json"}
        )
        saida = []
        for r in dados.get("results") or []:
            if not isinstance(r, dict):
                continue
            lat, lon = _numero(r.get("latitude")), _numero(r.get("longitude"))
            if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                continue
            partes = [
                p
                for p in (r.get("admin1"), r.get("country"))
                if isinstance(p, str) and p
            ]
            saida.append(
                {
                    "nome": texto(r.get("name"), "nome", 100, uma_linha=True),
                    "regiao": texto(
                        ", ".join(partes), "regiao", 200, obrigatorio=False
                    ),
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                }
            )
        return saida

    def previsao(self, item: Dict[str, Any], forcar: bool = False) -> Dict[str, Any]:
        if not forcar:
            guardada = self.cache.pegar(item, CACHE_S)
            if guardada is not None:
                return guardada
        base = {
            "latitude": round(item["latitude"], CASAS_NO_PEDIDO),
            "longitude": round(item["longitude"], CASAS_NO_PEDIDO),
            "timezone": "auto",
            "forecast_days": DIAS,
        }
        tempo = self._get(
            URL_PREVISAO,
            {**base, "hourly": ",".join(HORARIAS), "daily": ",".join(DIARIAS)},
        )
        mar = None
        if item["tipo"] == "praia":
            try:
                mar = self._get(URL_MAR, {**base, "hourly": ",".join(MARINHAS)})
            except ErroClima as exc:
                logger.warning("Éden: previsão do mar indisponível (%s)", exc.codigo)
        previsao = montar_previsao(tempo, mar)
        previsao["atualizado_em"] = agora_ms()
        previsao["fonte"] = FONTE
        self.cache.guardar(item, previsao)
        return previsao


def cliente_do_app(app) -> ClienteClima:  # noqa: ANN001
    atual = getattr(app.state, "eden_clima", None)
    if atual is None:
        atual = ClienteClima()
        app.state.eden_clima = atual
    return atual


# ── contexto da IA ───────────────────────────────────────────────────────


def _fmt(valor: Optional[float], casas: int = 0) -> str:
    if valor is None:
        return "?"
    texto_num = f"{valor:.{casas}f}"
    return texto_num.replace(".", ",")


def _linha_dia(d: Dict[str, Any], rotulo: str) -> str:
    partes = [rotulo + ":"]
    tempo_txt = descricao(d.get("codigo"))
    if tempo_txt:
        partes.append(tempo_txt + ",")
    partes.append(f"{_fmt(d.get('min'))}–{_fmt(d.get('max'))} °C,")
    partes.append(
        f"chuva {_fmt(d.get('chuva_prob'))}% ({_fmt(d.get('chuva_mm'), 1)} mm),"
    )
    partes.append(
        f"vento até {_fmt(d.get('vento_kmh'))} km/h ({nos(d.get('vento_kmh'))} nós), "
        f"rajadas {_fmt(d.get('rajada_kmh'))} km/h, de {rumo(d.get('vento_dir'))}"
    )
    return " ".join(partes)


def _linhas_mar(horas: List[Dict[str, Any]]) -> List[str]:
    linhas = []
    for h in horas[:48:3]:  # de 3 em 3 horas, 48 h
        if h.get("ondas_m") is None and h.get("vento_kmh") is None:
            continue
        dia, hora = h["hora"].split("T")
        linhas.append(
            f"  - {dia[8:10]}/{dia[5:7]} {hora[:2]}h: "
            f"ondas {_fmt(h.get('ondas_m'), 1)} m "
            f"{_fmt(h.get('ondas_s'))} s de {rumo(h.get('ondas_dir'))}; "
            f"vento {nos(h.get('vento_kmh'))} nós (rajadas "
            f"{nos(h.get('rajada_kmh'))}) de {rumo(h.get('vento_dir'))}"
        )
    return linhas


def secao_contexto(store: Organizacao, pergunta: Optional[str]) -> str:
    """Previsão guardada dos lugares, só se a pergunta for sobre tempo/mar."""
    if not pergunta_sobre_clima(pergunta):
        return ""
    if not ligado(store):
        # Sem previsão: melhor dizer que não sabe do que inventar.
        return (
            "## Clima\nDesligado: o Éden não tem previsão do tempo agora. Se a "
            "pessoa pedir previsão, diga isso e que dá para ligar no menu "
            "Clima e ondas. Não invente previsão."
        )
    lugares = listar_lugares(store)
    if not lugares:
        return (
            "## Clima\nO clima está ligado, mas nenhum lugar foi cadastrado "
            "(página Clima)."
        )
    texto_pergunta = _sem_acento(pergunta or "")
    citados = [lg for lg in lugares if _sem_acento(lg["nome"]) in texto_pergunta]
    escolhidos = (citados or [lg for lg in lugares if lg["principal"]])[:3]
    if not citados:
        # Pergunta sobre mar sem citar lugar: inclui as praias também.
        escolhidos += [lg for lg in lugares if lg["tipo"] == "praia"][:2]
    vistos = set()
    linhas = [f"## Clima (dados de {FONTE}; tempo local de cada lugar)"]
    for lg in escolhidos:
        if lg["id"] in vistos:
            continue
        vistos.add(lg["id"])
        previsao = CACHE.pegar(lg, CACHE_CONTEXTO_S)
        nome = '"' + lg["nome"].replace('"', "'") + '"'
        if previsao is None:
            linhas.append(f"### {nome} ({lg['tipo']}): previsão ainda não carregada")
            continue
        linhas.append(f"### {nome} ({lg['tipo']})")
        rotulos = ("hoje", "amanhã", "depois de amanhã")
        for d, rotulo in zip(previsao["dias"], rotulos):
            linhas.append(
                "- " + _linha_dia(d, f"{rotulo} ({d['dia'][8:10]}/{d['dia'][5:7]})")
            )
        if previsao.get("mar"):
            linhas.append("- mar e vento, de 3 em 3 h:")
            linhas.extend(_linhas_mar(previsao["horas"]))
    return "\n".join(linhas)


# ── atualização de hora em hora ──────────────────────────────────────────


def atualizar_todos(store: Organizacao, cliente: ClienteClima) -> int:
    if not ligado(store):
        return 0
    feitos = 0
    for lg in listar_lugares(store):
        try:
            cliente.previsao(lg)
            feitos += 1
        except ErroClima as exc:
            logger.warning("Éden: previsão não atualizada (%s)", exc.codigo)
    return feitos


def registrar_clima(app) -> None:  # noqa: ANN001
    import asyncio

    from openjarvis.eden.settings import get_settings

    async def laco() -> None:
        await asyncio.sleep(20)
        while True:
            try:
                store = getattr(app.state, "eden_organizacao", None)
                if get_settings().enabled and store is not None:
                    await asyncio.to_thread(atualizar_todos, store, cliente_do_app(app))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Éden: falha ao atualizar o clima")
            await asyncio.sleep(INTERVALO_S)

    estado: Dict[str, Any] = {}

    @app.on_event("startup")
    async def _ligar() -> None:  # pragma: no cover - roda com o servidor de verdade
        if get_settings().enabled:
            estado["tarefa"] = asyncio.create_task(laco())

    @app.on_event("shutdown")
    async def _desligar() -> None:  # pragma: no cover
        tarefa = estado.get("tarefa")
        if tarefa is not None:
            tarefa.cancel()
