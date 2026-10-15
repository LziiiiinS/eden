// Éden: a resposta numa folha limpa ou em slides, para imprimir, salvar em PDF
// ou guardar como arquivo. Quem monta a página é o app, a partir do texto que
// já está na tela — a IA não ganha nenhuma ferramenta e não gasta nada a mais.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Download, Pencil, Printer, X } from 'lucide-react';
import { SafeImage, SafeLink } from './EdenSafeMarkdown';
import {
  FOLHA_PAGE_RULE,
  MAX_INTRO_NA_CAPA,
  PAGE_CSS,
  SLIDES_CSS,
  SLIDES_PAGE_RULE,
  buildPageHtml,
  buildSlidesHtml,
  dateLabel,
  pageFileName,
  pageTitle,
  splitSlides,
} from '../../lib/eden-pagina';

type Modo = 'folha' | 'slides';

// Na impressão, só a folha (ou os slides) aparece; o resto do app some.
const PRINT_CSS = `
@media print {
  html, body { background: #fff !important; height: auto !important; overflow: visible !important; }
  body > *:not(.eden-pagina-raiz) { display: none !important; }
  .eden-pagina-raiz { position: static !important; inset: auto !important; overflow: visible !important; background: #fff !important; padding: 0 !important; display: block !important; }
  .eden-pagina-barra { display: none !important; }
  .eden-pagina-moldura { padding: 0 !important; }
}
`;

// No arquivo salvo, os links viram texto (o site continua escrito ao lado) e
// nada que busque coisas fora ou rode código fica.
const REMOVER =
  'script,style,iframe,object,embed,img,picture,video,audio,source,link,meta,form,input,button,svg,textarea';
const ATRIBUTOS_PROIBIDOS = new Set(['href', 'src', 'srcset', 'action', 'formaction', 'xlink:href', 'poster', 'background']);

function htmlParaArquivo(conteudo: HTMLElement): string {
  const copia = conteudo.cloneNode(true) as HTMLElement;
  copia.querySelectorAll('a').forEach((a) => {
    const span = document.createElement('span');
    span.textContent = a.textContent ?? '';
    a.replaceWith(span);
  });
  copia.querySelectorAll(REMOVER).forEach((el) => el.remove());
  copia.querySelectorAll('*').forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      const nome = attr.name.toLowerCase();
      if (nome.startsWith('on') || ATRIBUTOS_PROIBIDOS.has(nome)) el.removeAttribute(attr.name);
    }
  });
  return copia.innerHTML;
}

function aparelhoDeToque(): boolean {
  try {
    return window.matchMedia('(hover: none)').matches;
  } catch {
    return false;
  }
}

/** iPhone/iPad com o Éden aberto pelo ícone da tela de início. */
function appDoIphone(): boolean {
  return (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

async function guardarArquivo(html: string, nome: string, titulo: string): Promise<void> {
  const arquivo = new File([html], nome, { type: 'text/html' });
  const nav = navigator as Navigator & { canShare?: (dados: ShareData) => boolean };
  // Celular: abre o "Compartilhar" (salvar em Arquivos, imprimir, mandar).
  if (aparelhoDeToque() && nav.canShare?.({ files: [arquivo] })) {
    try {
      await navigator.share({ files: [arquivo], title: titulo });
      return;
    } catch (e) {
      if ((e as DOMException)?.name === 'AbortError') return;
      // Se o compartilhar falhar, cai no download normal.
    }
  }
  const url = URL.createObjectURL(arquivo);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Diminui a letra de cada slide até o texto caber (no mínimo 50%). */
function ajustarSlides(deck: HTMLElement) {
  deck.querySelectorAll<HTMLElement>('.eden-slide').forEach((slide) => {
    const corpo = slide.querySelector<HTMLElement>('.eden-slide-corpo');
    if (!corpo) return;
    let escala = 1;
    slide.style.setProperty('--escala', '1');
    while (corpo.scrollHeight > corpo.clientHeight + 1 && escala > 0.5) {
      escala = Math.round((escala - 0.05) * 100) / 100;
      slide.style.setProperty('--escala', String(escala));
    }
  });
}

const markdownComponents = { img: SafeImage, a: SafeLink };

interface Props {
  content: string;
  onClose: () => void;
}

export function EdenPageView({ content, onClose }: Props) {
  const conteudoRef = useRef<HTMLDivElement>(null);
  const deckRef = useRef<HTMLDivElement>(null);
  const [modo, setModo] = useState<Modo>('folha');
  const [texto, setTexto] = useState(content);
  const [editando, setEditando] = useState(false);
  const [aviso, setAviso] = useState('');
  const hoje = useMemo(() => new Date(), []);
  const deck = useMemo(() => splitSlides(texto), [texto]);
  const titulo = modo === 'slides' ? deck.titulo : pageTitle(texto);
  const iphoneApp = useMemo(appDoIphone, []);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', tecla);
    return () => window.removeEventListener('keydown', tecla);
  }, [onClose]);

  useEffect(() => {
    // O título vira o nome sugerido do PDF.
    const tituloAntes = document.title;
    document.title = titulo;
    return () => {
      document.title = tituloAntes;
    };
  }, [titulo]);

  // Slides: a letra encolhe quando o texto não cabe.
  useLayoutEffect(() => {
    if (modo !== 'slides' || !deckRef.current) return;
    const deckEl = deckRef.current;
    ajustarSlides(deckEl);
    let espera: ReturnType<typeof setTimeout> | undefined;
    const aoMudar = () => {
      clearTimeout(espera);
      espera = setTimeout(() => ajustarSlides(deckEl), 150);
    };
    window.addEventListener('resize', aoMudar);
    return () => {
      clearTimeout(espera);
      window.removeEventListener('resize', aoMudar);
    };
  }, [modo, deck]);

  const imprimir = () => {
    setAviso('');
    try {
      window.print();
    } catch {
      setAviso('Este aparelho não abriu a impressão. Use "Salvar arquivo" e imprima a partir dele.');
    }
  };

  const salvar = async () => {
    setAviso('');
    try {
      if (modo === 'slides') {
        if (!deckRef.current) return;
        const html = buildSlidesHtml(titulo, htmlParaArquivo(deckRef.current), hoje);
        await guardarArquivo(html, pageFileName(`${titulo} slides`, hoje), titulo);
      } else {
        if (!conteudoRef.current) return;
        const html = buildPageHtml(titulo, htmlParaArquivo(conteudoRef.current), hoje);
        await guardarArquivo(html, pageFileName(titulo, hoje), titulo);
      }
    } catch {
      setAviso('Não consegui salvar o arquivo neste aparelho.');
    }
  };

  const introNaCapa = deck.intro.length > 0 && deck.intro.length <= MAX_INTRO_NA_CAPA;
  const slidesConteudo = introNaCapa || !deck.intro ? deck.slides : [deck.intro, ...deck.slides];
  const totalSlides = slidesConteudo.length + 1;

  const botao =
    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer whitespace-nowrap';
  const botaoPrincipal = { background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' };
  const botaoNormal = {
    background: 'var(--color-bg-secondary)',
    color: 'var(--color-text)',
    border: '1px solid var(--color-border)',
  };
  const aba = (ativa: boolean) => ({
    background: ativa ? 'var(--color-surface)' : 'transparent',
    color: ativa ? 'var(--color-text)' : 'var(--color-text-secondary)',
    boxShadow: ativa ? 'var(--shadow-sm, 0 1px 2px rgba(0,0,0,.2))' : 'none',
  });

  return createPortal(
    <div
      className="eden-pagina-raiz fixed inset-0 z-[60] overflow-y-auto"
      style={{ background: '#3a3d42' }}
      role="dialog"
      aria-modal="true"
      aria-label={`Página: ${titulo}`}
    >
      <style>
        {(modo === 'slides' ? SLIDES_PAGE_RULE + SLIDES_CSS : FOLHA_PAGE_RULE + PAGE_CSS) + PRINT_CSS}
      </style>
      <div
        className="eden-pagina-barra sticky top-0 z-10 flex items-center gap-2 px-3 py-2 flex-wrap"
        style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)' }}
      >
        <div
          className="flex items-center p-0.5 rounded-lg"
          style={{ background: 'var(--color-bg-secondary)' }}
          role="tablist"
          aria-label="Formato"
        >
          {(['folha', 'slides'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={modo === m}
              onClick={() => setModo(m)}
              className="px-3 py-1 rounded-md text-xs font-medium cursor-pointer"
              style={aba(modo === m)}
            >
              {m === 'folha' ? 'Folha' : 'Slides'}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setEditando((v) => !v)}
          className={botao}
          style={botaoNormal}
          aria-pressed={editando}
        >
          <Pencil size={14} />
          {editando ? 'Pronto' : 'Editar texto'}
        </button>
        {/* No app do iPhone a impressão pode não abrir: lá, o arquivo vem primeiro. */}
        <button type="button" onClick={salvar} className={botao} style={iphoneApp ? botaoPrincipal : botaoNormal}>
          <Download size={14} />
          {aparelhoDeToque() ? 'Salvar ou compartilhar' : 'Salvar arquivo'}
        </button>
        <button type="button" onClick={imprimir} className={botao} style={iphoneApp ? botaoNormal : botaoPrincipal}>
          <Printer size={14} />
          Imprimir ou salvar PDF
        </button>
        <button
          type="button"
          onClick={onClose}
          className={`${botao} ml-auto`}
          style={{ color: 'var(--color-text-secondary)' }}
          aria-label="Fechar a página"
        >
          <X size={14} />
          Fechar
        </button>
        {iphoneApp && (
          <p className="w-full text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            No iPhone, se a impressão não abrir, toque em "Salvar ou compartilhar" e escolha Imprimir.
          </p>
        )}
        {aviso && (
          <p className="w-full text-xs" role="alert" style={{ color: 'var(--color-warning)' }}>
            {aviso}
          </p>
        )}
        {editando && (
          <div className="w-full flex flex-col gap-1">
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={10}
              spellCheck
              aria-label="Texto da página"
              className="w-full text-xs font-mono p-2 rounded-lg outline-none resize-y"
              style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
            />
            <p className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
              Muda só esta página, não a conversa. Nos slides, cada linha que começa com "## " vira um slide novo.
            </p>
          </div>
        )}
      </div>
      <div className="eden-pagina-moldura px-3 py-6 sm:px-6">
        {modo === 'folha' ? (
          <article className="eden-pagina-folha">
            <div ref={conteudoRef} className="eden-pagina-conteudo">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                {texto}
              </ReactMarkdown>
            </div>
            <div className="eden-pagina-rodape">Feito com o Éden · {dateLabel(hoje)}</div>
          </article>
        ) : (
          <div ref={deckRef} className="eden-deck">
            <section className="eden-slide eden-slide-capa">
              <div className="eden-slide-corpo">
                <h1>{deck.titulo}</h1>
                {introNaCapa && (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {deck.intro}
                  </ReactMarkdown>
                )}
              </div>
              <span className="eden-slide-rodape">Éden · {dateLabel(hoje)}</span>
              <span className="eden-slide-numero">1 / {totalSlides}</span>
            </section>
            {slidesConteudo.map((md, i) => (
              <section key={i} className="eden-slide">
                <div className="eden-slide-corpo">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {md}
                  </ReactMarkdown>
                </div>
                <span className="eden-slide-numero">
                  {i + 2} / {totalSlides}
                </span>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
