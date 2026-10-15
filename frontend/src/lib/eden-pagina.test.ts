// Éden: testes da página de uma folha.
import { describe, expect, it } from 'vitest';
import {
  buildPageHtml,
  buildSlidesHtml,
  dateLabel,
  escapeHtml,
  pageFileName,
  pageTitle,
  splitSlides,
} from './eden-pagina';

const DIA = new Date(2026, 9, 15, 18, 30);

describe('pageTitle', () => {
  it('uses the first heading', () => {
    expect(pageTitle('Intro\n\n## **Plano americano** x Plano 3/4\n\ntexto')).toBe(
      'Plano americano x Plano 3/4',
    );
  });

  it('falls back to the first line with text', () => {
    expect(pageTitle('\n\n  Uma resposta *simples* com [link](https://x.y)\nmais')).toBe(
      'Uma resposta simples com link',
    );
    expect(pageTitle('   \n ')).toBe('Página do Éden');
  });

  it('keeps titles short', () => {
    const titulo = pageTitle(`# ${'a'.repeat(200)}`);
    expect(titulo.length).toBeLessThanOrEqual(80);
    expect(titulo.endsWith('…')).toBe(true);
  });
});

describe('pageFileName', () => {
  it('makes a safe file name with the date', () => {
    expect(pageFileName('Plano americano x Plano 3/4', DIA)).toBe(
      'eden-plano-americano-x-plano-3-4-2026-10-15.html',
    );
    expect(pageFileName('Ação & reação: ../../etc', DIA)).toBe('eden-acao-reacao-etc-2026-10-15.html');
    expect(pageFileName('???', DIA)).toBe('eden-pagina-2026-10-15.html');
  });
});

describe('buildPageHtml', () => {
  it('blocks scripts and outside requests in the saved file', () => {
    const html = buildPageHtml('Título', '<p>Oi</p>', DIA);
    expect(html).toContain(`content="default-src 'none'; style-src 'unsafe-inline'"`);
    expect(html).toContain('<p>Oi</p>');
    expect(html).toContain('Feito com o Éden · 15/10/2026');
    expect(html).not.toContain('<script');
  });

  it('escapes the title', () => {
    const html = buildPageHtml('</title><script>alert(1)</script>', '', DIA);
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;/title&gt;&lt;script&gt;');
  });

  it('formats dates the Brazilian way', () => {
    expect(dateLabel(DIA)).toBe('15/10/2026');
    expect(escapeHtml(`a<b>"c"&'d'`)).toBe('a&lt;b&gt;&quot;c&quot;&amp;&#39;d&#39;');
  });
});

describe('splitSlides', () => {
  it('uses # for the cover and ## for each slide, ignoring code blocks', () => {
    const md = '# Título\n\nIntro curta.\n\n## A\n- a1\n\n```\n## não é seção\n```\n\n## B\ntexto';
    expect(splitSlides(md)).toEqual({
      titulo: 'Título',
      intro: 'Intro curta.',
      slides: ['## A\n- a1\n\n```\n## não é seção\n```', '## B\ntexto'],
    });
  });

  it('treats bold-only lines as sections when there is no ##', () => {
    const md = [
      'Não tenho como gerar o arquivo daqui.',
      '',
      '---',
      '',
      '**Plano americano x Plano 3/4**',
      '',
      '**Plano americano**',
      '- **Enquadramento:** até os joelhos.',
      '',
      '**Plano 3/4**',
      '- **Enquadramento:** até a cintura.',
    ].join('\n');
    const deck = splitSlides(md);
    expect(deck.titulo).toBe('Plano americano x Plano 3/4');
    expect(deck.intro).toBe('Não tenho como gerar o arquivo daqui.');
    expect(deck.slides).toEqual([
      '## Plano americano\n- **Enquadramento:** até os joelhos.',
      '## Plano 3/4\n- **Enquadramento:** até a cintura.',
    ]);
  });

  it('falls back to --- separators and does not repeat the title', () => {
    expect(splitSlides('um\n\n---\n\ndois\n\n---\n\ntrês')).toEqual({
      titulo: 'um',
      intro: '',
      slides: ['dois', 'três'],
    });
    expect(splitSlides('só um texto')).toEqual({ titulo: 'só um texto', intro: '', slides: [] });
  });

  it('turns a later # into a new slide', () => {
    expect(splitSlides('# T\n## A\nx\n# B\ny').slides).toEqual(['## A\nx', '## B\ny']);
  });
});

describe('buildSlidesHtml', () => {
  it('saves slides without scripts, landscape, with escaped title', () => {
    const html = buildSlidesHtml('<b>T</b>', '<section class="eden-slide"></section>', DIA);
    expect(html).toContain(`content="default-src 'none'; style-src 'unsafe-inline'"`);
    expect(html).toContain('size: A4 landscape');
    expect(html).toContain('&lt;b&gt;T&lt;/b&gt;');
    expect(html).not.toContain('<script');
  });

  it('keeps the page in portrait for the single sheet', () => {
    expect(buildPageHtml('T', '', DIA)).toContain('@page { size: A4; margin: 14mm; }');
  });
});
