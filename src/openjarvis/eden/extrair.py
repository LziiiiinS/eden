"""Éden: tira o texto de um arquivo (PDF, Word .docx, texto).

Roda num **processo separado**, chamado por ``documentos.extrair_texto``:
arquivos vêm de fora e um PDF malfeito pode travar ou encher a memória de
quem lê. Por isso, antes de abrir qualquer coisa, este processo se limita:

- memória (RLIMIT_AS), tempo de processador (RLIMIT_CPU);
- não pode criar nem aumentar arquivos (RLIMIT_FSIZE = 0);
- lê o arquivo pela entrada padrão e devolve JSON na saída padrão.

Usa só a biblioteca padrão e o pdfminer.six (para PDF). Não importa nada do
OpenJarvis (o processo começa leve e isolado, com ``python -I``).
"""

from __future__ import annotations

import io
import json
import sys

MEMORIA_MAX = 768 * 1024 * 1024
CPU_MAX_S = 30
ENTRADA_MAX = 10 * 1024 * 1024
TEXTO_MAX = 400_000  # o servidor corta de novo, com aviso
PAGINAS_MAX = 300
DOCX_XML_MAX = 40 * 1024 * 1024  # word/document.xml descompactado
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ErroExtracao(Exception):
    pass


def _limitar() -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover - Windows (só nos testes locais)
        return
    for nome, valor in (
        ("RLIMIT_AS", MEMORIA_MAX),
        ("RLIMIT_CPU", CPU_MAX_S),
        ("RLIMIT_FSIZE", 0),
        ("RLIMIT_CORE", 0),
    ):
        limite = getattr(resource, nome, None)
        if limite is None:
            continue
        try:
            atual_suave, atual_duro = resource.getrlimit(limite)
            novo = valor
            if atual_duro != resource.RLIM_INFINITY:
                novo = min(valor, atual_duro)
            resource.setrlimit(limite, (novo, novo))
        except (ValueError, OSError):
            pass


def texto_simples(dados: bytes) -> str:
    if dados.startswith(b"\xef\xbb\xbf"):
        dados = dados[3:]
    if b"\x00" in dados[:4096]:
        # UTF-16 com BOM é texto; zeros sem BOM costumam ser arquivo binário.
        if dados[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return dados.decode("utf-16", errors="replace")
        raise ErroExtracao("o arquivo não parece ser texto")
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


def texto_docx(dados: bytes) -> str:
    import zipfile
    from xml.etree import ElementTree

    try:
        pacote = zipfile.ZipFile(io.BytesIO(dados))
        info = pacote.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ErroExtracao("arquivo do Word danificado ou não é .docx") from exc
    if info.file_size > DOCX_XML_MAX:
        raise ErroExtracao("documento do Word grande demais")
    partes = []
    paragrafo = []
    with pacote.open(info) as xml:
        # Lê no máximo o tamanho declarado (+1): um zip que mente o tamanho
        # para no limite em vez de encher a memória.
        conteudo = xml.read(DOCX_XML_MAX + 1)
    if len(conteudo) > DOCX_XML_MAX:
        raise ErroExtracao("documento do Word grande demais")
    # Word de verdade grava o XML em UTF-8. UTF-16 escaparia da conferência
    # de DOCTYPE/ENTITY abaixo (que procura os bytes em ASCII).
    if conteudo[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in conteudo[:200]:
        raise ErroExtracao("documento do Word com conteúdo estranho")
    if b"<!DOCTYPE" in conteudo or b"<!ENTITY" in conteudo:
        raise ErroExtracao("documento do Word com conteúdo estranho")
    total = 0
    try:
        for evento, elemento in ElementTree.iterparse(
            io.BytesIO(conteudo), events=("end",)
        ):
            tag = elemento.tag
            if tag == f"{_W}t" and elemento.text:
                paragrafo.append(elemento.text)
            elif tag == f"{_W}tab":
                paragrafo.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr"):
                paragrafo.append("\n")
            elif tag == f"{_W}p":
                linha = "".join(paragrafo)
                partes.append(linha)
                total += len(linha) + 1
                paragrafo = []
                elemento.clear()
                if total > TEXTO_MAX:
                    break
    except ElementTree.ParseError as exc:
        raise ErroExtracao("arquivo do Word danificado") from exc
    if paragrafo:
        partes.append("".join(paragrafo))
    return "\n".join(partes)


def texto_pdf(dados: bytes) -> tuple:
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTTextContainer
        from pdfminer.pdfdocument import PDFPasswordIncorrect
    except ImportError as exc:  # pragma: no cover - imagem sem o pdfminer
        raise ErroExtracao("este servidor não lê PDF") from exc
    partes = []
    tamanho = 0
    paginas = 0
    try:
        for pagina in extract_pages(io.BytesIO(dados), maxpages=PAGINAS_MAX):
            paginas += 1
            for elemento in pagina:
                if isinstance(elemento, LTTextContainer):
                    pedaco = elemento.get_text()
                    partes.append(pedaco)
                    tamanho += len(pedaco)
            partes.append("\n")
            if tamanho > TEXTO_MAX:
                break
        texto = "".join(partes)
    except PDFPasswordIncorrect as exc:
        raise ErroExtracao("o PDF está protegido por senha") from exc
    except MemoryError as exc:
        raise ErroExtracao("o PDF é pesado demais para ler") from exc
    except Exception as exc:  # noqa: BLE001 - PDF malfeito tem mil formas
        nome = type(exc).__name__
        if "Encrypt" in nome or "Password" in nome:
            raise ErroExtracao("o PDF está protegido por senha") from exc
        raise ErroExtracao("não deu para ler este PDF") from exc
    return texto, paginas


def extrair(tipo: str, dados: bytes) -> dict:
    if len(dados) > ENTRADA_MAX:
        raise ErroExtracao("arquivo grande demais")
    paginas = None
    if tipo in ("txt", "md"):
        texto = texto_simples(dados)
    elif tipo == "docx":
        texto = texto_docx(dados)
    elif tipo == "pdf":
        texto, paginas = texto_pdf(dados)
    else:
        raise ErroExtracao("tipo de arquivo não aceito")
    return {"texto": texto[:TEXTO_MAX], "paginas": paginas}


def main() -> int:
    _limitar()
    tipo = sys.argv[1] if len(sys.argv) > 1 else ""
    dados = sys.stdin.buffer.read(ENTRADA_MAX + 1)
    try:
        resultado = extrair(tipo, dados)
    except ErroExtracao as exc:
        _responder({"erro": str(exc)})
        return 2
    except MemoryError:
        _responder({"erro": "o arquivo é pesado demais para ler"})
        return 2
    _responder(resultado)
    return 0


def _responder(dados: dict) -> None:
    sys.stdout.buffer.write(json.dumps(dados, ensure_ascii=False).encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    sys.exit(main())
