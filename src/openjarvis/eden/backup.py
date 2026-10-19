"""Éden: cópia de segurança (backup) e restauração dos dados.

Roda dentro da imagem do Éden, num contêiner à parte (serviço "backup" do
docker-compose), com o volume de dados em /dados e a pasta de backups do
computador em /backups::

    python -m openjarvis.eden.backup criar /backups [--tipo manual] [--manter N]
    python -m openjarvis.eden.backup conferir /backups/eden-backup-....tar.gz
    python -m openjarvis.eden.backup restaurar /backups/eden-backup-....tar.gz

O que entra no backup: só os dados da pessoa — USER.md, MEMORY.md e a pasta
eden/ (conversas, gastos e, nas próximas partes, tarefas e notas). Não entram
chaves (o .env fica fora do volume, e arquivos .env são sempre pulados), nem
config.toml e SOUL.md (vêm da imagem a cada início).

Os bancos SQLite são copiados pela API de backup do próprio SQLite, que gera
uma cópia consistente mesmo com o Éden ligado.

Restaurar exige o Éden parado (os scripts param antes). Antes de trocar
qualquer coisa, a restauração confere o arquivo inteiro — só nomes
permitidos, sem atalhos (links) nem caminhos para fora, tamanhos e sha256
iguais aos da lista interna, bancos íntegros — e guarda o estado atual num
backup "antes-de-restaurar". Se algo falhar na conferência, nada é trocado.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

FORMATO = 1
PREFIXO = "eden-backup"
TIPOS = ("manual", "auto", "diario", "antes-de-restaurar")
ARQUIVOS_RAIZ = ("USER.md", "MEMORY.md")
PASTA_EDEN = "eden"
MANIFESTO = "manifesto.json"

# Limites do arquivo de backup (proteção contra arquivos adulterados).
LIMITE_TOTAL_BYTES = 4 * 1024**3
LIMITE_ARQUIVOS = 20_000
LIMITE_MANIFESTO_BYTES = 8 * 1024**2

_SUFIXOS_SQLITE = (".db", ".sqlite", ".sqlite3")
# Arquivos de trabalho do SQLite: a cópia pela API de backup já inclui o que
# estava neles.
_SUFIXOS_IGNORADOS = ("-wal", "-shm", "-journal", ".parcial")
_NOME_SEGURO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
# Segredos do servidor (ex.: chave dos avisos no aparelho): nunca entram no
# backup; na restauração, os atuais continuam onde estão.
_SUFIXOS_SEGREDO = (".env", ".key", ".pem")
_HORA = re.compile(r"^\d{8}-\d{6}$")
_PASTA_TEMP_RESTAURAR = ".eden-restaurar"
_PASTA_ANTIGA = ".eden-antigo"


class ErroBackup(Exception):
    """Problema no backup/restauração, com mensagem para a pessoa."""


# ── o que entra ─────────────────────────────────────────────────────────


def _nome_permitido(nome: str) -> bool:
    return bool(_NOME_SEGURO.match(nome)) and not nome.lower().endswith(
        _SUFIXOS_SEGREDO
    )


def _ignorado(nome: str) -> bool:
    return nome.endswith(_SUFIXOS_IGNORADOS)


def _arquivos_dos_dados(dados: Path) -> List[Tuple[str, Path]]:
    """Lista (caminho dentro do backup, arquivo) do que entra no backup."""
    itens: List[Tuple[str, Path]] = []
    for nome in ARQUIVOS_RAIZ:
        caminho = dados / nome
        if caminho.is_file() and not caminho.is_symlink():
            itens.append((f"dados/{nome}", caminho))
    pasta = dados / PASTA_EDEN
    if pasta.is_dir() and not pasta.is_symlink():
        for raiz, pastas, arquivos in os.walk(pasta, followlinks=False):
            raiz_p = Path(raiz)
            pastas[:] = sorted(
                p
                for p in pastas
                if _nome_permitido(p) and not (raiz_p / p).is_symlink()
            )
            for nome in sorted(arquivos):
                caminho = raiz_p / nome
                if (
                    _ignorado(nome)
                    or not _nome_permitido(nome)
                    or caminho.is_symlink()
                    or not caminho.is_file()
                ):
                    continue
                rel = caminho.relative_to(dados).as_posix()
                itens.append((f"dados/{rel}", caminho))
    return itens


def _e_sqlite(nome: str) -> bool:
    return nome.lower().endswith(_SUFIXOS_SQLITE)


def _copiar_sqlite(origem: Path, destino: Path) -> None:
    try:
        src = sqlite3.connect(str(origem), timeout=30)
        try:
            dst = sqlite3.connect(str(destino))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except sqlite3.Error as exc:
        raise ErroBackup(f"não consegui copiar o banco {origem.name}: {exc}") from exc


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _hora_agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _nome_livre(destino: Path, tipo: str, hora: str) -> Path:
    base = f"{PREFIXO}-{tipo}-{hora}"
    caminho = destino / f"{base}.tar.gz"
    n = 2
    while caminho.exists():
        caminho = destino / f"{base}-{n}.tar.gz"
        n += 1
    return caminho


def _normalizar_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = 0o700 if info.isdir() else 0o600
    return info


def backups_do_tipo(destino: Path, tipo: str) -> List[Path]:
    """Backups de um tipo, do mais antigo para o mais novo."""
    padrao = re.compile(
        rf"^{re.escape(PREFIXO)}-{re.escape(tipo)}-\d{{8}}-\d{{6}}(-\d+)?\.tar\.gz$"
    )
    return sorted(
        (p for p in destino.iterdir() if p.is_file() and padrao.match(p.name)),
        key=lambda p: p.name,
    )


def _apagar_antigos(destino: Path, tipo: str, manter: int) -> List[Path]:
    apagados: List[Path] = []
    lista = backups_do_tipo(destino, tipo)
    for antigo in lista[: max(0, len(lista) - manter)]:
        antigo.unlink()
        apagados.append(antigo)
    return apagados


def criar(
    destino: Path,
    dados: Path,
    tipo: str = "manual",
    manter: Optional[int] = None,
    hora: Optional[str] = None,
) -> Path:
    """Cria o backup em ``destino`` e devolve o caminho do arquivo.

    ``manter``: se informado, apaga os backups mais antigos do MESMO tipo,
    deixando só os ``manter`` mais novos (backups manuais nunca são apagados
    por backups de outro tipo).
    """
    if tipo not in TIPOS:
        raise ErroBackup(f"tipo de backup desconhecido: {tipo}")
    if manter is not None and manter < 1:
        raise ErroBackup("--manter precisa ser 1 ou mais")
    hora = hora or _hora_agora()
    if not _HORA.match(hora):
        raise ErroBackup("hora no formato AAAAMMDD-HHMMSS")
    destino = Path(destino)
    dados = Path(dados)
    if not destino.is_dir():
        raise ErroBackup(f"a pasta de backups não existe: {destino}")
    if not dados.is_dir():
        raise ErroBackup(f"a pasta de dados não existe: {dados}")

    itens = _arquivos_dos_dados(dados)
    final = _nome_livre(destino, tipo, hora)
    parcial = final.with_name(final.name + ".parcial")

    with tempfile.TemporaryDirectory(prefix="eden-backup-") as tmp:
        pasta_tmp = Path(tmp)
        lista: List[Dict[str, object]] = []
        copias: List[Tuple[str, Path]] = []
        for i, (rel, origem) in enumerate(itens):
            copia = pasta_tmp / f"{i:05d}"
            if _e_sqlite(origem.name):
                _copiar_sqlite(origem, copia)
            else:
                shutil.copyfile(origem, copia)
            lista.append(
                {
                    "caminho": rel,
                    "bytes": copia.stat().st_size,
                    "sha256": _sha256(copia),
                }
            )
            copias.append((rel, copia))

        manifesto = {
            "formato": FORMATO,
            "app": "eden",
            "tipo": tipo,
            "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "arquivos": lista,
        }
        bruto = json.dumps(manifesto, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with tarfile.open(parcial, "w:gz") as tar:
                info = tarfile.TarInfo(MANIFESTO)
                info.size = len(bruto)
                info.mtime = int(datetime.now(timezone.utc).timestamp())
                tar.addfile(_normalizar_tarinfo(info), io.BytesIO(bruto))
                for rel, copia in copias:
                    tar.add(
                        str(copia),
                        arcname=rel,
                        recursive=False,
                        filter=_normalizar_tarinfo,
                    )
            os.replace(parcial, final)
        finally:
            if parcial.exists():
                parcial.unlink()
    try:
        os.chmod(final, 0o600)
    except OSError:
        pass  # pasta do Windows (Docker Desktop) ignora permissões

    if manter is not None:
        _apagar_antigos(destino, tipo, manter)
    return final


# ── conferência ─────────────────────────────────────────────────────────


def _caminho_permitido(nome: str, e_pasta: bool) -> bool:
    if nome == MANIFESTO:
        return not e_pasta
    if "\\" in nome or nome.startswith("/") or nome.endswith("/"):
        return False
    partes = PurePosixPath(nome).parts
    if not partes or partes[0] != "dados" or any(p in ("", ".", "..") for p in partes):
        return False
    if len(partes) == 1:
        return e_pasta
    if len(partes) == 2:
        if partes[1] == PASTA_EDEN:
            return e_pasta
        return (not e_pasta) and partes[1] in ARQUIVOS_RAIZ
    if partes[1] != PASTA_EDEN:
        return False
    return all(_nome_permitido(p) for p in partes[2:]) and not _ignorado(partes[-1])


def _membros_validos(tar: tarfile.TarFile) -> List[tarfile.TarInfo]:
    membros: List[tarfile.TarInfo] = []
    total = 0
    vistos = set()
    for membro in tar:
        if len(membros) >= LIMITE_ARQUIVOS:
            raise ErroBackup("o backup tem arquivos demais")
        if not (membro.isfile() or membro.isdir()):
            raise ErroBackup(f"o backup tem um item não permitido: {membro.name!r}")
        if not _caminho_permitido(membro.name, membro.isdir()):
            raise ErroBackup(f"o backup tem um caminho não permitido: {membro.name!r}")
        if membro.name in vistos:
            raise ErroBackup(f"o backup tem um arquivo repetido: {membro.name!r}")
        vistos.add(membro.name)
        total += membro.size
        if total > LIMITE_TOTAL_BYTES:
            raise ErroBackup("o backup é grande demais")
        membros.append(membro)
    return membros


def _ler_manifesto(tar: tarfile.TarFile, membros: Sequence[tarfile.TarInfo]) -> dict:
    info = next((m for m in membros if m.name == MANIFESTO), None)
    if info is None:
        raise ErroBackup("isso não é um backup do Éden (falta o manifesto)")
    if info.size > LIMITE_MANIFESTO_BYTES:
        raise ErroBackup("manifesto do backup grande demais")
    fh = tar.extractfile(info)
    if fh is None:
        raise ErroBackup("manifesto do backup ilegível")
    try:
        manifesto = json.loads(fh.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ErroBackup("manifesto do backup ilegível") from exc
    if not isinstance(manifesto, dict) or manifesto.get("app") != "eden":
        raise ErroBackup("isso não é um backup do Éden")
    if manifesto.get("formato") != FORMATO:
        raise ErroBackup(
            f"backup no formato {manifesto.get('formato')!r}; "
            f"esta versão lê o formato {FORMATO}"
        )
    arquivos = manifesto.get("arquivos")
    if not isinstance(arquivos, list):
        raise ErroBackup("manifesto do backup sem lista de arquivos")
    for item in arquivos:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("caminho"), str)
            and isinstance(item.get("bytes"), int)
            and isinstance(item.get("sha256"), str)
        ):
            raise ErroBackup("manifesto do backup com item inválido")
    return manifesto


def _esperados(manifesto: dict) -> Dict[str, dict]:
    esperado: Dict[str, dict] = {}
    for item in manifesto["arquivos"]:
        if item["caminho"] in esperado:
            raise ErroBackup("manifesto do backup com arquivo repetido")
        esperado[item["caminho"]] = item
    return esperado


def conferir(arquivo: Path) -> dict:
    """Confere o backup inteiro sem mexer em nada. Devolve o manifesto."""
    arquivo = Path(arquivo)
    if not arquivo.is_file():
        raise ErroBackup(f"arquivo não encontrado: {arquivo.name}")
    try:
        with tarfile.open(arquivo, "r:gz") as tar:
            membros = _membros_validos(tar)
            manifesto = _ler_manifesto(tar, membros)
            esperado = _esperados(manifesto)
            presentes = {
                m.name: m for m in membros if m.isfile() and m.name != MANIFESTO
            }
            if set(presentes) != set(esperado):
                raise ErroBackup("a lista interna do backup não bate com os arquivos")
            for nome, membro in presentes.items():
                item = esperado[nome]
                if membro.size != item["bytes"]:
                    raise ErroBackup(f"tamanho diferente do esperado: {nome}")
                fh = tar.extractfile(membro)
                if fh is None:
                    raise ErroBackup(f"arquivo ilegível no backup: {nome}")
                h = hashlib.sha256()
                for bloco in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(bloco)
                if h.hexdigest() != item["sha256"]:
                    raise ErroBackup(f"conteúdo diferente do esperado: {nome}")
    except (tarfile.TarError, EOFError, OSError, zlib.error) as exc:
        raise ErroBackup(f"arquivo de backup danificado ou incompleto: {exc}") from exc
    return manifesto


# Tabelas que cada banco do Éden pode ter. Um backup com outra coisa é
# recusado: gatilhos (triggers) e visões rodariam sozinhos dentro do Éden
# depois de restaurar (ex.: zerar a conta de gastos, trocar o resumo de um
# cartão de confirmação).
ESQUEMA_PERMITIDO = {
    "conversations.db": {"conversations", "messages"},
    "gastos.db": {"spending"},
    "organizacao.db": {
        "espacos",
        "perfil",
        "memorias",
        "tarefas",
        "notas",
        "acoes",
        "registro",
        "push_inscricoes",
        "ajustes",
        "documentos",
        "conversa_documentos",
        "lugares",
        "trajetos",
        "contas",
        "reunioes",
        "reuniao_pedacos",
    },
}


def _conferir_esquema(caminho: Path) -> None:
    permitidas = ESQUEMA_PERMITIDO.get(caminho.name)
    if permitidas is None or caminho.parent.name != PASTA_EDEN:
        raise ErroBackup(f"banco desconhecido no backup: {caminho.name}")
    try:
        conn = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            itens = conn.execute(
                "SELECT type, name, tbl_name, COALESCE(sql, '') FROM sqlite_master"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ErroBackup(f"banco danificado no backup: {caminho.name} ({exc})") from exc
    for tipo, nome, tabela, sql in itens:
        interna = nome.startswith("sqlite_")
        # "ON CONFLICT IGNORE/REPLACE" no esquema faria o banco descartar
        # gravações sem erro (ex.: gastos que somem). O Éden nunca cria assim
        # (revisão do Codex, 18/10).
        limpo = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.S).upper()
        conflito = re.search(r"\bON\s+CONFLICT\b", limpo) is not None
        if tipo == "table":
            ok = (
                (interna or nome in permitidas)
                and "VIRTUAL" not in limpo
                and not conflito
            )
        elif tipo == "index":
            ok = (tabela in permitidas or tabela.startswith("sqlite_")) and not conflito
        else:  # trigger, view
            ok = False
        if not ok:
            raise ErroBackup(
                f"o backup tem algo que o Éden não cria ({tipo} {nome!r} em "
                f"{caminho.name}); recusado"
            )


def _conferir_banco(caminho: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        try:
            resultado = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ErroBackup(f"banco danificado no backup: {caminho.name} ({exc})") from exc
    if not resultado or resultado[0] != "ok":
        raise ErroBackup(f"banco danificado no backup: {caminho.name}")


# ── restauração ─────────────────────────────────────────────────────────

# Decisões de segurança tomadas DEPOIS do backup continuam valendo depois de
# restaurar (rodada final de segurança, 18/10):
# - contas desligadas continuam desligadas (Google, e-mail, Notion, Drive):
#   essas linhas de "ajustes" ficam como estão agora;
# - celulares desligados não voltam a receber avisos: as inscrições de avisos
#   são apagadas (os aparelhos ligados se inscrevem de novo sozinhos);
# - o gasto do mês nunca diminui: em cada mês recente fica o maior total
#   (o de agora ou o do backup).
AJUSTES_DAS_CONTAS = (
    "google_agenda",  # google.Cofre.CHAVE
    "google_email",  # gmail.CofreEmail.CHAVE
    "google_email_conta",  # gmail.AJUSTE_CONTA
    "google_drive_pasta",  # google.AJUSTE_PASTA_DRIVE
    "notion_pagina_pai",  # notion.AJUSTE_PAI
)
_DIAS_GASTOS = 45


def _abrir(caminho: Path) -> Optional[sqlite3.Connection]:
    if not caminho.is_file() or caminho.is_symlink():
        return None
    conn = sqlite3.connect(str(caminho))
    conn.row_factory = sqlite3.Row
    return conn


def _tem_tabela(conn: sqlite3.Connection, nome: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (nome,)
        ).fetchone()
        is not None
    )


def _manter_decisoes_atuais(antiga: Path, atual: Path, agora_ms: int) -> None:
    nova = _abrir(atual / "organizacao.db")
    if nova is not None:
        velha = _abrir(antiga / "organizacao.db")
        try:
            with nova:
                if _tem_tabela(nova, "push_inscricoes"):
                    nova.execute("DELETE FROM push_inscricoes")
                if _tem_tabela(nova, "ajustes"):
                    for chave in AJUSTES_DAS_CONTAS:
                        nova.execute("DELETE FROM ajustes WHERE chave = ?", (chave,))
                        if velha is not None and _tem_tabela(velha, "ajustes"):
                            row = velha.execute(
                                "SELECT valor FROM ajustes WHERE chave = ?", (chave,)
                            ).fetchone()
                            if row is not None:
                                nova.execute(
                                    "INSERT INTO ajustes (chave, valor) VALUES (?, ?)",
                                    (chave, row["valor"]),
                                )
        finally:
            nova.close()
            if velha is not None:
                velha.close()

    velho_g = _abrir(antiga / "gastos.db")
    if velho_g is None:
        return
    if not (atual / "gastos.db").exists():
        # Backup de antes do controle de gastos: o gasto de agora continua.
        destino = sqlite3.connect(str(atual / "gastos.db"))
        try:
            velho_g.backup(destino)
        finally:
            destino.close()
            velho_g.close()
        return
    novo_g = _abrir(atual / "gastos.db")
    if novo_g is None:
        velho_g.close()
        return
    try:
        if not (_tem_tabela(novo_g, "spending") and _tem_tabela(velho_g, "spending")):
            return
        desde = agora_ms - _DIAS_GASTOS * 24 * 3600 * 1000
        meses = {
            (r[0], r[1])
            for c in (novo_g, velho_g)
            for r in c.execute(
                "SELECT DISTINCT month, provider FROM spending WHERE at_ms >= ?",
                (desde,),
            )
        }
        colunas = [
            r[1] for r in velho_g.execute("PRAGMA table_info(spending)") if r[1] != "id"
        ]
        lista = ", ".join(colunas)
        marcas = ", ".join("?" for _ in colunas)
        with novo_g:
            soma = (
                "SELECT COALESCE(SUM(cost_usd), 0) FROM spending "
                "WHERE month = ? AND provider = ?"
            )
            for mes, provedor in meses:
                chave = (mes, provedor)
                total_novo = novo_g.execute(soma, chave).fetchone()[0]
                total_velho = velho_g.execute(soma, chave).fetchone()[0]
                if total_velho <= total_novo:
                    continue
                novo_g.execute(
                    "DELETE FROM spending WHERE month = ? AND provider = ?", chave
                )
                linhas = velho_g.execute(
                    f"SELECT {lista} FROM spending "  # noqa: S608
                    "WHERE month = ? AND provider = ?",
                    chave,
                ).fetchall()
                novo_g.executemany(
                    f"INSERT INTO spending ({lista}) VALUES ({marcas})",  # noqa: S608
                    [tuple(r) for r in linhas],
                )
    finally:
        novo_g.close()
        velho_g.close()


def _remover(caminho: Path) -> None:
    if caminho.is_symlink() or caminho.is_file():
        caminho.unlink()
    elif caminho.exists():
        shutil.rmtree(caminho)


def restaurar(
    arquivo: Path,
    dados: Path,
    pasta_seguranca: Optional[Path] = None,
    hora: Optional[str] = None,
) -> Optional[Path]:
    """Troca os dados pelos do backup. Devolve o backup "antes-de-restaurar"
    feito com o estado atual (ou None, se ``pasta_seguranca`` não foi dada).

    O Éden precisa estar parado.
    """
    arquivo = Path(arquivo)
    dados = Path(dados)
    if not dados.is_dir():
        raise ErroBackup(f"a pasta de dados não existe: {dados}")
    manifesto = conferir(arquivo)
    esperado = _esperados(manifesto)

    tmp = dados / _PASTA_TEMP_RESTAURAR
    _remover(tmp)
    tmp.mkdir()
    try:
        try:
            with tarfile.open(arquivo, "r:gz") as tar:
                membros = [m for m in _membros_validos(tar) if m.name != MANIFESTO]
                tar.extractall(tmp, members=membros, filter="data")
        except (tarfile.TarError, EOFError, OSError, zlib.error) as exc:
            raise ErroBackup(f"não consegui abrir o backup: {exc}") from exc

        # Confere de novo o que saiu no disco (o arquivo pode ter mudado
        # entre a conferência e a extração) e a integridade dos bancos.
        for nome, item in esperado.items():
            extraido = tmp / nome
            if (
                extraido.is_symlink()
                or not extraido.is_file()
                or _sha256(extraido) != item["sha256"]
            ):
                raise ErroBackup(f"conteúdo diferente do esperado: {nome}")
            if _e_sqlite(extraido.name):
                _conferir_banco(extraido)
                _conferir_esquema(extraido)

        seguranca = None
        if pasta_seguranca is not None:
            seguranca = criar(
                pasta_seguranca, dados, tipo="antes-de-restaurar", manter=5, hora=hora
            )

        novos = tmp / "dados"
        antiga = dados / _PASTA_ANTIGA
        _remover(antiga)
        atual = dados / PASTA_EDEN
        if atual.exists() or atual.is_symlink():
            os.replace(atual, antiga)
        nova_eden = novos / PASTA_EDEN
        if nova_eden.is_dir():
            os.replace(nova_eden, atual)
        else:
            atual.mkdir()
        if antiga.is_dir():
            agora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            try:
                _manter_decisoes_atuais(antiga, atual, agora_ms)
            except Exception as exc:  # noqa: BLE001
                # Volta tudo como estava: melhor não restaurar do que desfazer
                # um desligamento sem avisar.
                _remover(atual)
                os.replace(antiga, atual)
                raise ErroBackup(
                    f"não consegui manter as contas desligadas ({exc}); nada mudou"
                ) from exc
        # Os segredos do servidor (que não vão no backup) continuam valendo.
        if antiga.is_dir():
            for segredo in antiga.iterdir():
                if (
                    segredo.is_file()
                    and not segredo.is_symlink()
                    and segredo.name.lower().endswith(_SUFIXOS_SEGREDO)
                    and not (atual / segredo.name).exists()
                ):
                    os.replace(segredo, atual / segredo.name)
        for nome in ARQUIVOS_RAIZ:
            novo = novos / nome
            if novo.is_file():
                destino = dados / nome
                if destino.is_symlink():
                    destino.unlink()
                os.replace(novo, destino)
        _remover(antiga)
        return seguranca
    finally:
        _remover(tmp)


# ── linha de comando ────────────────────────────────────────────────────


def _tamanho(n: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"


def _resumo(manifesto: dict) -> Iterable[str]:
    for item in manifesto["arquivos"]:
        yield f"  {item['caminho'][len('dados/') :]}  ({_tamanho(item['bytes'])})"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m openjarvis.eden.backup",
        description="Backup e restauração dos dados do Éden.",
    )
    parser.add_argument(
        "--dados",
        default=os.environ.get("OPENJARVIS_HOME") or "/dados",
        help="pasta de dados do Éden (padrão: OPENJARVIS_HOME ou /dados)",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_criar = sub.add_parser("criar", help="cria um backup")
    p_criar.add_argument("pasta", help="pasta onde salvar o backup")
    p_criar.add_argument("--tipo", default="manual", choices=TIPOS)
    p_criar.add_argument("--manter", type=int, default=None)
    p_criar.add_argument("--hora", default=None, help="AAAAMMDD-HHMMSS (hora local)")

    p_conferir = sub.add_parser("conferir", help="confere um backup sem mexer em nada")
    p_conferir.add_argument("arquivo")

    p_rest = sub.add_parser("restaurar", help="troca os dados pelos do backup")
    p_rest.add_argument("arquivo")
    p_rest.add_argument("--hora", default=None, help="AAAAMMDD-HHMMSS (hora local)")

    args = parser.parse_args(argv)
    dados = Path(args.dados)
    try:
        if args.comando == "criar":
            caminho = criar(
                Path(args.pasta),
                dados,
                tipo=args.tipo,
                manter=args.manter,
                hora=args.hora,
            )
            manifesto = conferir(caminho)
            print(f"Backup criado: {caminho.name} ({_tamanho(caminho.stat().st_size)})")
            for linha in _resumo(manifesto):
                print(linha)
        elif args.comando == "conferir":
            manifesto = conferir(Path(args.arquivo))
            print(
                f"Backup em ordem: {Path(args.arquivo).name} "
                f"(feito em {manifesto.get('criado_em', '?')})"
            )
            for linha in _resumo(manifesto):
                print(linha)
        else:
            arquivo = Path(args.arquivo)
            seguranca = restaurar(
                arquivo, dados, pasta_seguranca=arquivo.parent, hora=args.hora
            )
            print(f"Restaurado: {arquivo.name}")
            if seguranca is not None:
                print(f"O estado anterior ficou guardado em: {seguranca.name}")
    except ErroBackup as exc:
        print(f"Éden (backup): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
