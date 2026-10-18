"""Éden: abre o app num navegador de verdade (Chromium) contra o contêiner e
confere, como uma pessoa faria:

1. a tela da chave aceita a chave e some;
2. a conversa guardada no servidor aparece e abre;
3. o ícone de folha abre a resposta como folha e como slides, o texto pode
   ser editado e o arquivo salvo não tem scripts; as páginas da organização
   (tarefas, notas, hoje, memória) e as Configurações abrem;
   um documento enviado pelo clipe é lido e anexado à conversa; a página
   Clima começa desligada e liga pelo botão;
4. um "aparelho novo" entra com o código curto (iPhone pela tela de início),
   e o código não vale uma segunda vez;
5. nenhuma regra de segurança da página (CSP) bloqueou nada e não houve erro
   de JavaScript.

Sem IA de verdade: a resposta da conversa é colocada direto no servidor.
Uso: EDEN_CHAVE=... python teste_navegador.py
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("EDEN_BASE", "http://127.0.0.1:8000")
CHAVE = os.environ["EDEN_CHAVE"]
FOTOS = pathlib.Path(os.environ.get("EDEN_FOTOS", "fotos-navegador"))

RESPOSTA = """# Plano americano x Plano 3/4

Diferenças de enquadramento para vídeo.

## Plano americano
- **Enquadramento:** da cabeça até os joelhos.
- **Quando usar:** cenas de ação e diálogos com movimento.

## Plano 3/4
- **Enquadramento:** da cabeça até a cintura.
- **Quando usar:** entrevistas e depoimentos.

## Diferença principal
O americano mostra mais corpo e ambiente; o 3/4 aproxima da pessoa.
"""


def api(metodo: str, caminho: str, corpo=None, chave: bool = True):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(BASE + caminho, data=dados, method=metodo)
    if dados is not None:
        pedido.add_header("Content-Type", "application/json")
    if chave:
        pedido.add_header("Authorization", f"Bearer {CHAVE}")
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, None


ULTIMO_PASSO = ["(nenhum)"]


def passo(texto: str) -> None:
    ULTIMO_PASSO[0] = texto
    print(f"ok: {texto}", flush=True)


def main() -> int:
    FOTOS.mkdir(parents=True, exist_ok=True)
    agora = int(time.time() * 1000)
    status, _ = api(
        "PUT",
        "/v1/eden/conversations/teste-pagina",
        {
            "id": "teste-pagina",
            "title": "Teste da página",
            "model": "eden-auto",
            "createdAt": agora,
            "updatedAt": agora + 1,
            "messages": [
                {
                    "id": "u1",
                    "role": "user",
                    "content": "faz uma apresentação",
                    "timestamp": agora,
                },
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": RESPOSTA,
                    "timestamp": agora + 1,
                },
            ],
        },
    )
    assert status == 200, f"conversa de teste não foi guardada ({status})"

    problemas: list[str] = []
    avisos: list[str] = []

    def vigiar(pagina, nome: str) -> None:
        def no_console(msg) -> None:
            texto = msg.text
            if "Content Security Policy" in texto or "Refused to" in texto:
                problemas.append(f"[{nome}] CSP: {texto}")
            elif msg.type == "error":
                avisos.append(f"[{nome}] {texto}")

        pagina.on("console", no_console)
        pagina.on("pageerror", lambda e: problemas.append(f"[{nome}] erro: {e}"))

    with sync_playwright() as pw:
        navegador = pw.chromium.launch()

        # ── notebook: chave, conversa, folha e slides ─────────────────────
        ctx = navegador.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        vigiar(pg, "notebook")
        pg.goto(BASE)
        pg.get_by_label("Chave de acesso", exact=True).fill(CHAVE)
        pg.get_by_role("button", name="Entrar").click()
        expect(pg.get_by_label("Chave de acesso", exact=True)).to_have_count(
            0, timeout=30_000
        )
        passo("tela da chave aceitou a chave")

        conversa = pg.get_by_text("Teste da página").first
        expect(conversa).to_be_visible(timeout=60_000)
        conversa.click()
        expect(pg.get_by_text("Diferença principal").first).to_be_visible(
            timeout=30_000
        )
        passo("conversa do servidor apareceu e abriu")

        pg.get_by_text("Diferença principal").first.hover()
        pg.get_by_label("Abrir como página").first.click()
        folha = pg.locator(".eden-pagina-folha")
        expect(folha).to_be_visible()
        expect(folha).to_contain_text("O americano mostra mais corpo")
        expect(folha.locator("h1")).to_have_text("Plano americano x Plano 3/4")
        pg.screenshot(path=str(FOTOS / "folha.png"), full_page=True)
        passo("folha abriu com o texto da resposta")

        pg.get_by_role("tab", name="Slides").click()
        slides = pg.locator(".eden-slide")
        expect(slides).to_have_count(4)
        expect(slides.nth(0)).to_contain_text("Plano americano x Plano 3/4")
        proporcao = slides.nth(1).evaluate(
            "e => e.getBoundingClientRect().width / e.getBoundingClientRect().height"
        )
        assert 1.7 < proporcao < 1.85, f"slide fora de 16:9 ({proporcao:.2f})"
        passo("slides: capa + 3 slides em 16:9")

        pg.get_by_role("button", name="Editar texto").click()
        area = pg.get_by_label("Texto da página")
        area.fill(area.input_value() + "\n\n## Slide novo\n" + "- item\n" * 40)
        expect(slides).to_have_count(5)
        escala = slides.nth(4).evaluate(
            "e => parseFloat(getComputedStyle(e).getPropertyValue('--escala') || '1')"
        )
        assert escala < 1, "slide com muito texto não encolheu a letra"
        pg.get_by_role("button", name="Pronto").click()
        pg.screenshot(path=str(FOTOS / "slides.png"), full_page=True)
        passo(f"editar texto criou um slide; texto longo encolheu ({escala})")

        with pg.expect_download() as baixado:
            pg.get_by_role("button", name="Salvar arquivo").click()
        html = pathlib.Path(baixado.value.path()).read_text(encoding="utf-8")
        assert "default-src 'none'" in html, "arquivo salvo sem a regra de segurança"
        assert "<script" not in html.lower(), "arquivo salvo com script"
        assert "Slide novo" in html, "arquivo salvo sem o texto editado"
        assert baixado.value.suggested_filename.endswith(".html")
        passo(f"arquivo salvo: {baixado.value.suggested_filename}")

        pg.get_by_label("Fechar a página").click()
        expect(folha).to_have_count(0)
        expect(pg.locator(".eden-slide")).to_have_count(0)
        passo("página fechou")

        # ── documentos na conversa (Parte 3) ──────────────────────────────
        pg.get_by_role("button", name=re.compile(r"^Documentos")).click()
        painel = pg.get_by_role("region", name="Documentos do espaço")
        expect(painel).to_be_visible()
        pg.get_by_label("Escolher arquivo").set_input_files(
            {
                "name": "Orçamento do teste.txt",
                "mimeType": "text/plain",
                "buffer": "Aluguel: 1500\nLuz: 200\n".encode(),
            }
        )
        expect(painel.get_by_role("button", name="Em uso")).to_be_visible(
            timeout=30_000
        )
        chip = pg.get_by_label("Tirar Orçamento do teste.txt da conversa")
        expect(chip).to_be_visible()
        status, anexados = api("GET", "/v1/eden/documentos/conversa/teste-pagina")
        assert status == 200 and len(anexados["documentos"]) == 1, anexados
        passo("documento enviado, lido e anexado à conversa")
        chip.click()
        expect(chip).to_have_count(0)
        status, anexados = api("GET", "/v1/eden/documentos/conversa/teste-pagina")
        assert anexados["documentos"] == [], anexados
        pg.get_by_label("Fechar documentos").click()
        expect(painel).to_have_count(0)
        passo("documento tirado da conversa")

        # ── pesquisa na internet (Parte 4): liga só para a próxima mensagem ─
        busca = pg.get_by_role("button", name="Pesquisar na internet")
        expect(busca).to_have_attribute("aria-pressed", "false")
        busca.click()
        expect(busca).to_have_attribute("aria-pressed", "true")
        expect(pg.get_by_text("Só nesta mensagem")).to_be_visible()
        busca.click()
        expect(busca).to_have_attribute("aria-pressed", "false")
        status, estado = api("GET", "/v1/eden/pesquisa/status")
        assert status == 200 and estado["disponivel"] is False, estado
        passo("pesquisa na internet: botão liga/desliga; sem chave da Anthropic")

        # ── resposta em voz (Parte 4): modo conversa liga e desliga ─────────
        voz = pg.get_by_role("button", name="Responder em voz")
        expect(voz).to_have_attribute("aria-pressed", "false")
        voz.click()
        expect(voz).to_have_attribute("aria-pressed", "true")
        expect(pg.get_by_text("O Éden fala as respostas")).to_be_visible()
        voz.click()
        expect(voz).to_have_attribute("aria-pressed", "false")
        status, estado = api("GET", "/v1/eden/voz/status")
        assert status == 200 and "marin" in estado["vozes"], estado
        passo("resposta em voz: botão liga/desliga; status da voz responde")

        # ── organização pessoal (Parte 2) e Configurações ─────────────────
        status, _ = api(
            "POST",
            "/v1/eden/tarefas",
            {"titulo": "Tarefa do teste do navegador", "espaco": "pessoal"},
        )
        assert status == 200, f"tarefa de teste não foi criada ({status})"
        status, _ = api(
            "POST",
            "/v1/eden/notas",
            {
                "titulo": "Nota do teste do navegador",
                "texto": "texto da nota",
                "tipo": "ideia",
                "espaco": "pessoal",
            },
        )
        assert status == 200, f"nota de teste não foi criada ({status})"
        for caminho, texto in (
            ("/tarefas", "Tarefa do teste do navegador"),
            ("/notas", "Nota do teste do navegador"),
            ("/hoje", None),
            ("/memoria", None),
        ):
            pg.goto(BASE + caminho)
            expect(pg.get_by_label("Chave de acesso", exact=True)).to_have_count(0)
            if texto:
                expect(pg.get_by_text(texto).first).to_be_visible(timeout=30_000)
            else:
                pg.wait_for_load_state("networkidle")
            passo(f"página {caminho} abriu")

        # Clima (Parte 4): começa desligado; ligar não chama o Open-Meteo
        # (só busca e previsão chamam, e aqui nenhum lugar é cadastrado).
        pg.goto(BASE + "/clima")
        ligar = pg.get_by_role("button", name="Ligar clima e ondas")
        expect(ligar).to_be_visible(timeout=30_000)
        ligar.click()
        expect(pg.get_by_text("Nenhum lugar ainda")).to_be_visible(timeout=30_000)
        expect(pg.get_by_label("Coordenadas")).to_be_visible()
        status, estado = api("GET", "/v1/eden/clima/status")
        assert status == 200 and estado["ligado"] is True, estado
        status, _ = api("POST", "/v1/eden/clima/ligar", {"ligado": False})
        assert status == 200
        passo("Clima: desligado no começo, liga pela página")

        # Contas (Parte 5): anotar pela página, marcar como paga e a próxima
        # (todo mês) aparece sozinha. Dados fictícios.
        pg.goto(BASE + "/contas")
        pg.get_by_label("Descrição").first.fill("Internet do teste (fictícia)")
        pg.get_by_label("Valor em reais").first.fill("99,90")
        pg.get_by_label("Vencimento").first.fill("2030-01-10")
        pg.get_by_label("Repete").first.select_option("mensal")
        pg.get_by_role("button", name="Anotar").click()
        expect(pg.get_by_text("Internet do teste (fictícia)").first).to_be_visible(
            timeout=30_000
        )
        expect(pg.get_by_text("R$ 99,90").first).to_be_visible()
        pg.get_by_role("button", name="Marcar como paga").first.click()
        status, abertas = api("GET", "/v1/eden/contas?estado=abertas")
        for _ in range(20):
            if status == 200 and any(
                c["vencimento"] == "2030-02-10" for c in abertas["contas"]
            ):
                break
            time.sleep(0.5)
            status, abertas = api("GET", "/v1/eden/contas?estado=abertas")
        assert any(c["vencimento"] == "2030-02-10" for c in abertas["contas"]), abertas
        passo("Contas: anota, marca como paga e cria a do mês seguinte")

        # E-mail (Parte 5): sem o Google configurado, a página só explica.
        pg.goto(BASE + "/email")
        expect(pg.get_by_text("E-mail ainda não conectado")).to_be_visible(
            timeout=30_000
        )
        passo("E-mail: sem conexão, explica como ligar")

        # Rotas (Parte 4): sem a chave do TomTom, a página só explica.
        pg.goto(BASE + "/rotas")
        expect(pg.get_by_text("Ainda não configurado")).to_be_visible(timeout=30_000)
        passo("Rotas: sem a chave do TomTom, explica como ligar")

        pg.goto(BASE + "/settings")
        expect(pg.get_by_role("heading", name="Configurações")).to_be_visible(
            timeout=30_000
        )
        pg.get_by_role("button", name="Mostrar código").click()
        codigo_tela = pg.get_by_label("Código para digitar no aparelho")
        expect(codigo_tela).to_have_text(re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$"))
        pg.get_by_role("button", name="Esconder código").click()
        expect(codigo_tela).to_have_count(0)
        passo("Configurações: mostrar e esconder o código curto")
        expect(pg.get_by_text("Ainda não configurada")).to_be_visible()
        passo("Configurações: Google Agenda aparece (sem configurar)")
        expect(pg.get_by_text("notion.so/profile/integrations")).to_be_visible()
        passo("Configurações: Notion aparece (sem configurar)")
        expect(pg.get_by_role("switch", name="Modo conversa")).to_be_visible()
        expect(pg.get_by_label("Voz", exact=True)).to_be_visible()
        passo("Configurações: voz (modo conversa e escolha da voz)")
        ctx.close()

        # ── aparelho novo: código curto ────────────────────────────────────
        status, criado = api("POST", "/v1/eden/pareamento")
        assert status == 200 and criado, f"código não foi criado ({status})"
        codigo = criado["codigo"]
        ctx2 = navegador.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        cel = ctx2.new_page()
        vigiar(cel, "celular")
        cel.goto(BASE)
        cel.get_by_role("button", name="Tenho um código do notebook").click()
        cel.get_by_label("Código do notebook").fill(codigo.lower().replace("-", " "))
        expect(cel.get_by_label("Código do notebook")).to_have_value(codigo)
        cel.get_by_role("button", name="Entrar").click()
        expect(cel.get_by_text("Ligar este aparelho")).to_have_count(0, timeout=30_000)
        expect(cel.get_by_label("Chave de acesso", exact=True)).to_have_count(0)
        cel.screenshot(path=str(FOTOS / "celular.png"), full_page=True)
        passo("aparelho novo entrou com o código curto")
        ctx2.close()

        status, _ = api(
            "POST", "/v1/eden/pareamento/usar", {"codigo": codigo}, chave=False
        )
        assert status == 400, f"o código valeu duas vezes ({status})"
        passo("o código não vale uma segunda vez")

        # Parte 5: o celular ganhou uma chave só dele, que aparece na lista.
        status, lista = api("GET", "/v1/eden/aparelhos")
        assert status == 200 and len(lista["aparelhos"]) == 1, lista
        aparelho = lista["aparelhos"][0]
        status, _ = api("DELETE", f"/v1/eden/aparelhos/{aparelho['id']}")
        assert status == 200, f"não desligou o aparelho ({status})"
        passo(f"chave por aparelho: {aparelho['nome']} listado e desligado")
        navegador.close()

    for aviso in avisos:
        print(f"aviso (console): {aviso}")
    if problemas:
        for problema in problemas:
            print(f"error: {problema}")
        return 1
    passo("nenhum bloqueio de CSP nem erro de JavaScript")
    print("Éden no navegador: tudo certo")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # Aparece nas anotações do GitHub (o registro completo não abre daqui).
        print(f"error: último passo que deu certo: {ULTIMO_PASSO[0]}", flush=True)
        for linha in str(exc).splitlines()[:12]:
            print(f"error: {linha}", flush=True)
        raise
