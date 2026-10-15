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
@page { size: A4; margin: 14mm; }
`;

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
