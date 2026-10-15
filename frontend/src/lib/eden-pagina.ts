// Éden: uma resposta vira uma página de uma folha (imprimir, salvar em PDF ou
// guardar como arquivo). A IA continua sem ferramentas: quem monta a página é
// o próprio app, a partir do texto que já está na tela.

/** Aparência da folha: igual na tela, na impressão e no arquivo salvo. */
export const PAGE_CSS = `
.eden-pagina-folha { background: #fff; color: #16181d; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.55; width: 100%; max-width: 210mm; margin: 0 auto; padding: 16mm 15mm; box-sizing: border-box; border-radius: 4px; box-shadow: 0 2px 18px rgba(0, 0, 0, 0.22); overflow-wrap: break-word; }
.eden-pagina-folha h1, .eden-pagina-folha h2, .eden-pagina-folha h3, .eden-pagina-folha h4, .eden-pagina-folha h5, .eden-pagina-folha h6 { font-weight: 700; color: #0f1115; }
.eden-pagina-folha h1 { font-size: 26px; line-height: 1.2; margin: 0 0 12px; }
.eden-pagina-folha h2 { font-size: 19px; line-height: 1.25; margin: 22px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #e6e8ec; }
.eden-pagina-folha h3 { font-size: 16px; margin: 16px 0 6px; }
.eden-pagina-folha h4, .eden-pagina-folha h5, .eden-pagina-folha h6 { font-size: 15px; margin: 14px 0 6px; }
.eden-pagina-folha > :first-child, .eden-pagina-conteudo > :first-child { margin-top: 0; }
.eden-pagina-folha p { margin: 0 0 10px; }
.eden-pagina-folha ul, .eden-pagina-folha ol { margin: 0 0 10px; padding-left: 22px; }
.eden-pagina-folha ul { list-style: disc; }
.eden-pagina-folha ol { list-style: decimal; }
.eden-pagina-folha li > ul, .eden-pagina-folha li > ol { margin: 4px 0 0; }
.eden-pagina-folha li > ul { list-style: circle; }
.eden-pagina-folha li { margin: 3px 0; }
.eden-pagina-folha strong, .eden-pagina-folha b { font-weight: 700; }
.eden-pagina-folha em { font-style: italic; }
.eden-pagina-folha hr { border: 0; border-top: 1px solid #e6e8ec; margin: 16px 0; }
.eden-pagina-folha table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 14px; }
.eden-pagina-folha th, .eden-pagina-folha td { border: 1px solid #dfe2e7; padding: 6px 8px; text-align: left; vertical-align: top; }
.eden-pagina-folha th { background: #f3f5f8; }
.eden-pagina-folha code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 13px; background: #f3f5f8; padding: 1px 4px; border-radius: 3px; }
.eden-pagina-folha pre { background: #f3f5f8; padding: 10px 12px; border-radius: 6px; white-space: pre-wrap; }
.eden-pagina-folha pre code { background: none; padding: 0; }
.eden-pagina-folha blockquote { margin: 0 0 10px; padding: 4px 12px; border-left: 3px solid #c9ced6; color: #474d57; }
.eden-pagina-folha a { color: inherit; }
.eden-pagina-rodape { margin-top: 20px; padding-top: 8px; border-top: 1px solid #e6e8ec; font-size: 11px; color: #7a808a; }
@media (max-width: 640px) { .eden-pagina-folha { padding: 22px 18px; font-size: 14px; } .eden-pagina-folha h1 { font-size: 22px; } }
@media print { .eden-pagina-folha { box-shadow: none; border-radius: 0; padding: 0; max-width: none; } }
.eden-pagina-folha blockquote > :last-child { margin-bottom: 0; }
`;

/** Tamanho do papel na impressão: folha em pé; slides deitados. */
export const FOLHA_PAGE_RULE = '@page { size: A4; margin: 14mm; }';
export const SLIDES_PAGE_RULE = '@page { size: A4 landscape; margin: 10mm; }';

/**
 * Aparência dos slides (16:9). Os tamanhos usam a largura do slide (cqw), então
 * o slide fica igual na tela, no celular e na impressão. ``--escala`` diminui a
 * letra quando o texto não cabe (o app calcula e deixa gravado no slide).
 */
export const SLIDES_CSS = `
.eden-deck { display: flex; flex-direction: column; align-items: center; gap: 24px; }
.eden-slide { container-type: inline-size; position: relative; width: 100%; max-width: 1000px; aspect-ratio: 16 / 9; background: #fff; color: #16181d; border-radius: 6px; box-shadow: 0 2px 18px rgba(0, 0, 0, 0.25); overflow: hidden; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; overflow-wrap: break-word; }
.eden-slide::before { content: ""; position: absolute; left: 7cqw; top: 3.4cqw; width: 6cqw; height: 0.5cqw; border-radius: 1cqw; background: #3b5bdb; }
.eden-slide-corpo { position: absolute; inset: 0; box-sizing: border-box; padding: 6.2cqw 7cqw 6.5cqw; font-size: calc(2.3cqw * var(--escala, 1)); line-height: 1.4; overflow: hidden; }
.eden-slide-corpo > :first-child { margin-top: 0; }
.eden-slide h1, .eden-slide h2, .eden-slide h3, .eden-slide h4, .eden-slide h5, .eden-slide h6 { font-weight: 700; color: #0f1115; }
.eden-slide h2 { font-size: 1.85em; line-height: 1.15; margin: 0 0 0.65em; }
.eden-slide h3 { font-size: 1.2em; margin: 0.8em 0 0.3em; }
.eden-slide h4, .eden-slide h5, .eden-slide h6 { font-size: 1em; margin: 0.7em 0 0.3em; }
.eden-slide p { margin: 0 0 0.6em; }
.eden-slide ul, .eden-slide ol { margin: 0 0 0.6em; padding-left: 1.3em; }
.eden-slide ul { list-style: disc; }
.eden-slide ol { list-style: decimal; }
.eden-slide li { margin: 0.25em 0; }
.eden-slide li > ul, .eden-slide li > ol { margin: 0.2em 0 0; }
.eden-slide strong, .eden-slide b { font-weight: 700; }
.eden-slide em { font-style: italic; }
.eden-slide table { border-collapse: collapse; width: 100%; font-size: 0.85em; margin: 0.3em 0 0.6em; }
.eden-slide th, .eden-slide td { border: 1px solid #dfe2e7; padding: 0.35em 0.5em; text-align: left; vertical-align: top; }
.eden-slide th { background: #f3f5f8; }
.eden-slide code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.85em; background: #f3f5f8; padding: 0.05em 0.25em; border-radius: 0.2em; }
.eden-slide pre { background: #f3f5f8; padding: 0.6em 0.8em; border-radius: 0.3em; white-space: pre-wrap; }
.eden-slide pre code { background: none; padding: 0; }
.eden-slide blockquote { margin: 0 0 0.6em; padding: 0.1em 0.8em; border-left: 0.25em solid #c9ced6; color: #474d57; }
.eden-slide blockquote > :last-child { margin-bottom: 0; }
.eden-slide hr { border: 0; border-top: 1px solid #e6e8ec; margin: 0.8em 0; }
.eden-slide a { color: inherit; }
.eden-slide-capa .eden-slide-corpo { display: flex; flex-direction: column; justify-content: center; padding: 8cqw 9cqw; }
.eden-slide-capa::before { display: none; }
.eden-slide-capa h1::before { content: ""; display: block; width: 1em; height: 0.085em; margin-bottom: 0.4em; border-radius: 0.1em; background: #3b5bdb; }
.eden-slide-capa h1 { font-size: 2.6em; line-height: 1.1; margin: 0 0 0.45em; font-weight: 800; }
.eden-slide-capa p { font-size: 1.1em; color: #474d57; }
.eden-slide-numero, .eden-slide-rodape { position: absolute; bottom: 2.6cqw; font-size: 1.35cqw; color: #8a909a; }
.eden-slide-numero { right: 3.6cqw; }
.eden-slide-rodape { left: 7cqw; }
.eden-slide-capa .eden-slide-rodape { left: 9cqw; }
@media print {
  .eden-deck { display: block; }
  .eden-slide { max-width: none; box-shadow: none; border-radius: 0; margin: 0 auto; break-inside: avoid; break-after: page; page-break-after: always; }
  .eden-slide:last-child { break-after: auto; page-break-after: auto; }
}
`;

export interface Deck {
  /** Título da apresentação (vai na capa). */
  titulo: string;
  /** Texto antes da primeira seção (vai na capa se for curto). */
  intro: string;
  /** Um markdown por slide, cada um começando com "## título" quando houver. */
  slides: string[];
}

const LINHA_H1 = /^#\s+(.+?)\s*#*$/;
const LINHA_H2 = /^##\s+(.+?)\s*#*$/;
const LINHA_NEGRITO = /^\*\*([^*]+?)\*\*:?\s*$/;
const LINHA_SEPARADOR = /^(?:-{3,}|\*{3,}|_{3,})\s*$/;
const CERCA = /^\s*(?:```|~~~)/;

/**
 * Divide a resposta em slides. Cada "## seção" vira um slide; o primeiro
 * "# título" vai para a capa. Sem "##", uma linha só em negrito (como
 * "**Plano americano**") faz o papel de seção; sem nenhum dos dois, as
 * linhas "---" separam os slides. Nada dentro de blocos de código conta.
 */
export function splitSlides(markdown: string): Deck {
  const linhas = markdown.replace(/\r\n?/g, '\n').split('\n');
  const emCodigo: boolean[] = [];
  let dentro = false;
  for (const linha of linhas) {
    const cerca = CERCA.test(linha);
    emCodigo.push(dentro || cerca);
    if (cerca) dentro = !dentro;
  }
  const fora = (i: number) => !emCodigo[i];
  const temH2 = linhas.some((l, i) => fora(i) && LINHA_H2.test(l.trim()));
  const temNegrito = !temH2 && linhas.some((l, i) => fora(i) && LINHA_NEGRITO.test(l.trim()));
  const usarSeparador = !temH2 && !temNegrito;

  let titulo = '';
  const blocos: string[][] = [[]];
  linhas.forEach((linha, i) => {
    const t = linha.trim();
    if (fora(i)) {
      const h1 = LINHA_H1.exec(t);
      if (h1 && !titulo) {
        titulo = limparMarkdown(h1[1]);
        return;
      }
      const secao = h1 ?? LINHA_H2.exec(t) ?? (temNegrito ? LINHA_NEGRITO.exec(t) : null);
      if (secao) {
        if (!titulo && temNegrito && !h1) {
          // A primeira linha em negrito é o título da apresentação.
          titulo = limparMarkdown(secao[1]);
          return;
        }
        blocos.push([`## ${secao[1].trim()}`]);
        return;
      }
      if (LINHA_SEPARADOR.test(t)) {
        if (usarSeparador) blocos.push([]);
        return;
      }
    }
    blocos[blocos.length - 1].push(linha);
  });

  const juntar = (b: string[]) => b.join('\n').trim();
  if (!titulo) {
    // Sem título marcado: usa a primeira linha e tira ela do texto da capa.
    titulo = pageTitle(markdown);
    const primeira = blocos[0].findIndex((l) => l.trim().length > 0);
    if (primeira >= 0 && limparMarkdown(blocos[0][primeira]) === titulo) {
      blocos[0].splice(primeira, 1);
    }
  }
  const intro = juntar(blocos[0]);
  const slides = blocos
    .slice(1)
    .map(juntar)
    .filter((s) => s.length > 0);
  return { titulo, intro, slides };
}

/** Capa curta: o texto antes da primeira seção vai na capa só se couber. */
export const MAX_INTRO_NA_CAPA = 280;

/** Arquivo HTML sozinho com os slides (mesmas regras do arquivo da folha). */
export function buildSlidesHtml(title: string, deckHtml: string, date: Date): string {
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${escapeHtml(title)}</title>
<style>
html, body { margin: 0; background: #3a3d42; }
body { padding: 24px 12px; }
@media print { html, body { background: #fff; } body { padding: 0; } }
${SLIDES_PAGE_RULE}
${SLIDES_CSS}
</style>
</head>
<body>
<main class="eden-deck">
${deckHtml}
</main>
<!-- Feito com o Éden · ${escapeHtml(dateLabel(date))} -->
</body>
</html>
`;
}

const MAX_TITULO = 80;

function limparMarkdown(linha: string): string {
  return linha
    .replace(/^#{1,6}\s+/, '')
    .replace(/[*_`~]/g, '')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Título da página: o primeiro título (# ...) ou a primeira linha com texto. */
export function pageTitle(markdown: string): string {
  const linhas = markdown.split(/\r?\n/).map((l) => l.trim());
  const cabecalho = linhas.find((l) => /^#{1,6}\s+\S/.test(l));
  const escolhida = cabecalho ?? linhas.find((l) => limparMarkdown(l).length > 0) ?? '';
  const titulo = limparMarkdown(escolhida);
  if (!titulo) return 'Página do Éden';
  return titulo.length > MAX_TITULO ? `${titulo.slice(0, MAX_TITULO - 1).trimEnd()}…` : titulo;
}

/** Nome do arquivo: "eden-plano-americano-x-plano-3-4-2026-10-15.html". */
export function pageFileName(title: string, date: Date): string {
  const slug = title
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50)
    .replace(/-+$/g, '');
  const dia = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
  return `eden-${slug || 'pagina'}-${dia}.html`;
}

export function dateLabel(date: Date): string {
  return [
    String(date.getDate()).padStart(2, '0'),
    String(date.getMonth() + 1).padStart(2, '0'),
    date.getFullYear(),
  ].join('/');
}

export function escapeHtml(texto: string): string {
  return texto
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Arquivo HTML sozinho, para guardar ou mandar. Sem scripts e sem buscar nada
 * fora (a regra de segurança no topo do arquivo bloqueia). ``bodyHtml`` vem do
 * que o app já desenhou na tela a partir do texto (sem HTML da IA).
 */
export function buildPageHtml(title: string, bodyHtml: string, date: Date): string {
  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>${escapeHtml(title)}</title>
<style>
html, body { margin: 0; background: #eceef1; }
body { padding: 24px 12px; }
@media print { html, body { background: #fff; } body { padding: 0; } }
${FOLHA_PAGE_RULE}
${PAGE_CSS}
</style>
</head>
<body>
<article class="eden-pagina-folha">
${bodyHtml}
<div class="eden-pagina-rodape">Feito com o Éden · ${escapeHtml(dateLabel(date))}</div>
</article>
</body>
</html>
`;
}
