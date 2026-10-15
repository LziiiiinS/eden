"""Éden: notificações no aparelho (Web Push) para os lembretes.

Como funciona:

- O servidor tem um par de chaves VAPID (criado na primeira vez, em
  <dados>/eden/push-vapid.key, só o servidor lê). A chave pública vai para o
  app, que pede ao navegador uma "inscrição" (endereço do serviço de avisos do
  Google, da Apple, da Mozilla ou da Microsoft + chaves do aparelho).
- Na hora do lembrete, o servidor cifra o aviso com as chaves do aparelho
  (RFC 8291, aes128gcm) e manda ao serviço de avisos, assinado com a chave
  VAPID (RFC 8292). O serviço de avisos não consegue ler o conteúdo.
- Só são aceitos endereços dos serviços de avisos conhecidos (um endereço
  qualquer faria o servidor chamar sites que não deveria).
- Endereço que o serviço diz que não existe mais (404/410) é apagado.

Nenhuma conta é criada: os serviços de avisos são os do próprio navegador.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)

# Contato pedido pelo padrão VAPID (sem dado pessoal).
VAPID_SUB = "https://github.com/LziiiiinS/eden"
MAX_INSCRICOES = 10
TTL_SEGUNDOS = 12 * 3600
INTERVALO_LEMBRETES = 30

# Serviços de avisos aceitos (host exato ou terminação).
_HOSTS_EXATOS = {
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
}
_HOSTS_TERMINACAO = (".notify.windows.com", ".push.apple.com")


class ErroPush(ValueError):
    pass


def b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def de_b64url(texto: str) -> bytes:
    if not isinstance(texto, str) or not re.match(r"^[A-Za-z0-9_\-=]+$", texto):
        raise ErroPush("chave em formato inválido")
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# ── chaves VAPID ─────────────────────────────────────────────────────────


def _caminho_chave() -> Path:
    return get_config_dir() / "eden" / "push-vapid.key"


def carregar_chave(caminho: Optional[Path] = None) -> ec.EllipticCurvePrivateKey:
    """Lê (ou cria, na primeira vez) a chave VAPID do servidor."""
    caminho = caminho or _caminho_chave()
    if caminho.exists():
        chave = serialization.load_pem_private_key(caminho.read_bytes(), password=None)
        if not isinstance(chave, ec.EllipticCurvePrivateKey):
            raise ErroPush("chave VAPID inválida")
        return chave
    caminho.parent.mkdir(parents=True, exist_ok=True)
    chave = ec.generate_private_key(ec.SECP256R1())
    pem = chave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(str(caminho), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    return chave


def chave_publica_b64(chave: ec.EllipticCurvePrivateKey) -> str:
    return b64url(
        chave.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )


def jwt_vapid(
    endpoint: str, chave: ec.EllipticCurvePrivateKey, agora: Optional[int] = None
) -> str:
    agora = agora or int(time.time())
    url = urlparse(endpoint)
    cabecalho = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    dados = b64url(
        json.dumps(
            {
                "aud": f"{url.scheme}://{url.netloc}",
                "exp": agora + 12 * 3600,
                "sub": VAPID_SUB,
            }
        ).encode()
    )
    assinado = f"{cabecalho}.{dados}".encode("ascii")
    der = chave.sign(assinado, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return (
        f"{cabecalho}.{dados}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    )


# ── cifra (RFC 8291) ─────────────────────────────────────────────────────


def _hmac(chave: bytes, dados: bytes) -> bytes:
    h = hmac.HMAC(chave, hashes.SHA256())
    h.update(dados)
    return h.finalize()


def cifrar(
    mensagem: bytes,
    p256dh: bytes,
    auth: bytes,
    efemera: Optional[ec.EllipticCurvePrivateKey] = None,
    sal: Optional[bytes] = None,
) -> bytes:
    """Corpo cifrado (aes128gcm) para o aparelho dono de ``p256dh``/``auth``."""
    if len(p256dh) != 65 or p256dh[0] != 4:
        raise ErroPush("chave do aparelho inválida")
    if len(auth) != 16:
        raise ErroPush("segredo do aparelho inválido")
    efemera = efemera or ec.generate_private_key(ec.SECP256R1())
    sal = sal or os.urandom(16)
    publica_aparelho = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), p256dh
    )
    publica_servidor = efemera.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    segredo = efemera.exchange(ec.ECDH(), publica_aparelho)
    prk_chave = _hmac(auth, segredo)
    ikm = _hmac(prk_chave, b"WebPush: info\x00" + p256dh + publica_servidor + b"\x01")
    prk = _hmac(sal, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    cifrado = AESGCM(cek).encrypt(nonce, mensagem + b"\x02", None)
    cabecalho = (
        sal
        + struct.pack("!L", 4096)
        + bytes([len(publica_servidor)])
        + publica_servidor
    )
    return cabecalho + cifrado


# ── inscrições ───────────────────────────────────────────────────────────


def endpoint_permitido(endpoint: Any) -> bool:
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        return False
    try:
        url = urlparse(endpoint)
    except ValueError:
        return False
    if url.scheme != "https" or url.username or url.password:
        return False
    if url.port not in (None, 443):
        return False
    host = (url.hostname or "").lower()
    return host in _HOSTS_EXATOS or any(host.endswith(t) for t in _HOSTS_TERMINACAO)


def validar_inscricao(dados: Any) -> Tuple[str, str, str, str]:
    """(endpoint, p256dh, auth, nome) conferidos."""
    if not isinstance(dados, dict):
        raise ErroPush("inscrição inválida")
    endpoint = dados.get("endpoint")
    if not endpoint_permitido(endpoint):
        raise ErroPush("serviço de avisos não reconhecido")
    chaves = dados.get("keys") or {}
    if not isinstance(chaves, dict):
        raise ErroPush("inscrição sem chaves")
    p256dh = chaves.get("p256dh", "")
    auth = chaves.get("auth", "")
    pub = de_b64url(p256dh)
    seg = de_b64url(auth)
    if len(pub) != 65 or pub[0] != 4:
        raise ErroPush("chave do aparelho inválida")
    if len(seg) != 16:
        raise ErroPush("segredo do aparelho inválido")
    # O ponto precisa estar na curva.
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub)
    except ValueError as exc:
        raise ErroPush("chave do aparelho inválida") from exc
    nome = dados.get("nome") or ""
    if not isinstance(nome, str):
        nome = ""
    nome = re.sub(r"[^\w .,()-]", "", nome)[:60].strip()
    return endpoint, p256dh, auth, nome


def salvar_inscricao(store, dados: Any) -> Dict[str, Any]:
    endpoint, p256dh, auth, nome = validar_inscricao(dados)
    agora = int(time.time() * 1000)

    def fazer(conn):
        existe = conn.execute(
            "SELECT id FROM push_inscricoes WHERE endpoint = ?", (endpoint,)
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE push_inscricoes SET p256dh = ?, auth = ?, nome = ?, falhas = 0 "
                "WHERE id = ?",
                (p256dh, auth, nome, existe["id"]),
            )
            return existe["id"]
        total = conn.execute("SELECT COUNT(*) FROM push_inscricoes").fetchone()[0]
        if total >= MAX_INSCRICOES:
            raise ErroPush(f"limite de {MAX_INSCRICOES} aparelhos com avisos")
        cur = conn.execute(
            "INSERT INTO push_inscricoes (endpoint, p256dh, auth, nome, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (endpoint, p256dh, auth, nome, agora),
        )
        return cur.lastrowid

    novo_id = store.transacao(fazer)
    return {"id": novo_id, "nome": nome, "servico": urlparse(endpoint).hostname}


def remover_inscricao(store, endpoint: Any) -> bool:
    if not isinstance(endpoint, str):
        return False

    def fazer(conn):
        cur = conn.execute(
            "DELETE FROM push_inscricoes WHERE endpoint = ?", (endpoint,)
        )
        return cur.rowcount > 0

    return bool(store.transacao(fazer))


def remover_inscricao_id(store, insc_id: int) -> bool:
    def fazer(conn):
        cur = conn.execute("DELETE FROM push_inscricoes WHERE id = ?", (insc_id,))
        return cur.rowcount > 0

    return bool(store.transacao(fazer))


def conferir_troca_de_chave(store, chave_acesso: str) -> bool:
    """Se a chave de acesso do servidor mudou desde a última vez, apaga as
    inscrições de avisos: quem só tinha a chave antiga não continua
    recebendo os lembretes. Os aparelhos do dono se inscrevem de novo
    sozinhos quando ele entra com a chave nova. Devolve True se apagou."""
    if not chave_acesso:
        return False
    marca = hashlib.sha256(f"eden-push:{chave_acesso}".encode("utf-8")).hexdigest()

    def fazer(conn):
        row = conn.execute(
            "SELECT valor FROM ajustes WHERE chave = 'marca_chave_acesso'"
        ).fetchone()
        apagou = False
        if row is not None and row["valor"] != marca:
            conn.execute("DELETE FROM push_inscricoes")
            apagou = True
        conn.execute(
            "INSERT INTO ajustes (chave, valor) VALUES ('marca_chave_acesso', ?) "
            "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
            (marca,),
        )
        return apagou

    return bool(store.transacao(fazer))


def listar_inscricoes(store) -> List[Dict[str, Any]]:
    """Sem o endereço completo (ele funciona como senha do aparelho)."""
    return [
        {
            "id": i["id"],
            "nome": i["nome"],
            "servico": urlparse(i["endpoint"]).hostname,
            "criado_em": i["criado_em"],
            "usado_em": i["usado_em"],
        }
        for i in store.inscricoes_push()
    ]


# ── envio ────────────────────────────────────────────────────────────────


async def enviar(
    store,
    chave: ec.EllipticCurvePrivateKey,
    aviso: Dict[str, Any],
    client: Any,
) -> Dict[str, int]:
    """Manda o aviso para todos os aparelhos inscritos. Devolve contagens."""
    mensagem = json.dumps(aviso, ensure_ascii=False).encode("utf-8")
    publica = chave_publica_b64(chave)
    resultado = {"enviados": 0, "falhas": 0, "removidos": 0}
    for insc in store.inscricoes_push():
        endpoint = insc["endpoint"]
        host = urlparse(endpoint).hostname
        if not endpoint_permitido(endpoint):
            remover_inscricao(store, endpoint)
            resultado["removidos"] += 1
            continue
        try:
            corpo = cifrar(mensagem, de_b64url(insc["p256dh"]), de_b64url(insc["auth"]))
            autorizacao = f"vapid t={jwt_vapid(endpoint, chave)}, k={publica}"
            resposta = await client.post(
                endpoint,
                content=corpo,
                headers={
                    "TTL": str(TTL_SEGUNDOS),
                    "Urgency": "high",
                    "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream",
                    "Authorization": autorizacao,
                },
                timeout=15,
            )
            status = resposta.status_code
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Éden: aviso não enviado para %s: %s", host, type(exc).__name__
            )
            status = 0
        if status in (200, 201, 202):
            resultado["enviados"] += 1
            _marcar(store, insc["id"], ok=True)
        elif status in (404, 410):
            remover_inscricao(store, endpoint)
            resultado["removidos"] += 1
        else:
            resultado["falhas"] += 1
            logger.warning("Éden: serviço de avisos %s respondeu %s", host, status)
            _marcar(store, insc["id"], ok=False)
    return resultado


def _marcar(store, insc_id: int, ok: bool) -> None:
    def fazer(conn):
        if ok:
            conn.execute(
                "UPDATE push_inscricoes SET usado_em = ?, falhas = 0 WHERE id = ?",
                (int(time.time() * 1000), insc_id),
            )
        else:
            conn.execute(
                "UPDATE push_inscricoes SET falhas = falhas + 1 WHERE id = ?",
                (insc_id,),
            )
            # Muitas falhas seguidas: o aparelho provavelmente não existe mais.
            conn.execute(
                "DELETE FROM push_inscricoes WHERE id = ? AND falhas >= 20", (insc_id,)
            )

    store.transacao(fazer)


async def enviar_lembretes_vencidos(
    store, chave, client, agora_ms: Optional[int] = None
) -> int:
    """Avisa os lembretes que chegaram na hora. Devolve quantos foram tratados."""
    agora_ms = agora_ms or int(time.time() * 1000)
    tratados = 0
    for tarefa in store.lembretes_vencidos(agora_ms):
        # Marca antes de mandar: nunca avisa duas vezes o mesmo lembrete.
        if not store.marcar_lembrete_enviado(tarefa["id"], agora_ms):
            continue
        tratados += 1
        if not store.inscricoes_push():
            continue
        await enviar(
            store,
            chave,
            {
                "titulo": "Lembrete do Éden",
                "corpo": tarefa["titulo"],
                "tag": f"tarefa-{tarefa['id']}",
                "url": "/tarefas",
            },
            client,
        )
    return tratados


def registrar_lembretes(app) -> None:
    """Liga a verificação de lembretes (a cada 30 s) quando o servidor sobe."""
    from openjarvis.eden.settings import get_settings

    estado: Dict[str, Any] = {}

    async def laco() -> None:
        import httpx

        from openjarvis.eden.organizacao import Organizacao

        async with httpx.AsyncClient() as client:
            while True:
                # Espera antes de conferir (também na primeira vez, logo
                # depois de ligar).
                await asyncio.sleep(INTERVALO_LEMBRETES)
                try:
                    store = getattr(app.state, "eden_organizacao", None)
                    if store is None:
                        store = Organizacao()
                        app.state.eden_organizacao = store
                    chave = estado.get("chave")
                    if chave is None:
                        chave = await asyncio.to_thread(carregar_chave)
                        estado["chave"] = chave
                    await enviar_lembretes_vencidos(store, chave, client)
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("Éden: falha ao conferir lembretes")

    def _conferir_chave() -> None:
        from openjarvis.eden.organizacao import Organizacao

        store = getattr(app.state, "eden_organizacao", None)
        if store is None:
            store = Organizacao()
            app.state.eden_organizacao = store
        if conferir_troca_de_chave(store, os.environ.get("OPENJARVIS_API_KEY", "")):
            logger.info("Éden: chave de acesso nova; avisos dos aparelhos reiniciados")

    @app.on_event("startup")
    async def _ligar() -> None:  # pragma: no cover - roda com o servidor de verdade
        if get_settings().enabled:
            try:
                await asyncio.to_thread(_conferir_chave)
            except Exception:  # noqa: BLE001
                logger.exception("Éden: não consegui conferir a chave de acesso")
            estado["tarefa"] = asyncio.create_task(laco())

    @app.on_event("shutdown")
    async def _desligar() -> None:  # pragma: no cover
        tarefa = estado.get("tarefa")
        if tarefa is not None:
            tarefa.cancel()
