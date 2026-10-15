// Éden: a resposta numa folha limpa, para imprimir, salvar em PDF ou guardar
// como arquivo. Quem monta a página é o app, a partir do texto que já está na
// tela — a IA não ganha nenhuma ferramenta e não gasta nada a mais.
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Download, Printer, X } from 'lucide-react';
import { SafeImage, SafeLink } from './EdenSafeMarkdown';
import { PAGE_CSS, buildPageHtml, dateLabel, pageFileName, pageTitle } from '../../lib/eden-pagina';

// Na impressão, só a folha aparece (o resto do app some).
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
const REMOVER = 'script,style,iframe,object,embed,img,picture,video,audio,source,link,meta,form,input,button,svg';
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

interface Props {
  content: string;
  onClose: () => void;
}

export function EdenPageView({ content, onClose }: Props) {
  const conteudoRef = useRef<HTMLDivElement>(null);
  const [aviso, setAviso] = useState('');
  const hoje = useMemo(() => new Date(), []);
  const titulo = useMemo(() => pageTitle(content), [content]);

  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', tecla);
    const tituloAntes = document.title;
    // O título vira o nome sugerido do PDF.
    document.title = titulo;
    return () => {
      window.removeEventListener('keydown', tecla);
      document.title = tituloAntes;
    };
  }, [onClose, titulo]);

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
    const conteudo = conteudoRef.current;
    if (!conteudo) return;
    try {
      const html = buildPageHtml(titulo, htmlParaArquivo(conteudo), hoje);
      await guardarArquivo(html, pageFileName(titulo, hoje), titulo);
    } catch {
      setAviso('Não consegui salvar o arquivo neste aparelho.');
    }
  };

  const botao =
    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer whitespace-nowrap';

  return createPortal(
    <div
      className="eden-pagina-raiz fixed inset-0 z-[60] overflow-y-auto"
      style={{ background: '#3a3d42' }}
      role="dialog"
      aria-modal="true"
      aria-label={`Página: ${titulo}`}
    >
      <style>{PAGE_CSS + PRINT_CSS}</style>
      <div
        className="eden-pagina-barra sticky top-0 z-10 flex items-center gap-2 px-3 py-2 flex-wrap"
        style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)' }}
      >
        <button
          type="button"
          onClick={imprimir}
          className={botao}
          style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' }}
        >
          <Printer size={14} />
          Imprimir ou salvar PDF
        </button>
        <button
          type="button"
          onClick={salvar}
          className={botao}
          style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
        >
          <Download size={14} />
          Salvar arquivo
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
        {aviso && (
          <p className="w-full text-xs" role="alert" style={{ color: 'var(--color-warning)' }}>
            {aviso}
          </p>
        )}
      </div>
      <div className="eden-pagina-moldura px-3 py-6 sm:px-6">
        <article className="eden-pagina-folha">
          <div ref={conteudoRef} className="eden-pagina-conteudo">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: SafeImage, a: SafeLink }}>
              {content}
            </ReactMarkdown>
          </div>
          <div className="eden-pagina-rodape">Feito com o Éden · {dateLabel(hoje)}</div>
        </article>
      </div>
    </div>,
    document.body,
  );
}
