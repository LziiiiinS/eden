// Éden (Parte 3): documentos na conversa. A pessoa envia um arquivo (no
// celular, o seletor do aparelho também mostra o Google Drive) e escolhe
// quais vão junto nesta conversa. O Éden guarda só o texto.
import { useCallback, useEffect, useRef, useState } from 'react';
import { BookOpen, FileText, Paperclip, Trash2, Upload, X } from 'lucide-react';
import { EdenNotionPicker } from '../Eden/EdenNotionPicker';
import { importarDoNotion, statusNotion, type PaginaNotion } from '../../lib/eden-notion';
import { useEdenOrg } from '../../lib/eden-org';
import {
  ACCEPT,
  anexarDocumento,
  apagarDocumento,
  desanexarDocumento,
  detalhesDocumento,
  documentosDaConversa,
  enviarDocumento,
  listarDocumentos,
  vaiCortado,
  type Documento,
  type LimitesDocumentos,
} from '../../lib/eden-documentos';

interface Props {
  conversaId: string | null;
  /** Cria a conversa (se ainda não existe) e devolve o id. */
  garantirConversa: () => string;
  disabled?: boolean;
}

const chipStyle = {
  background: 'var(--color-bg-secondary)',
  border: '1px solid var(--color-border)',
  color: 'var(--color-text-secondary)',
};

export function EdenDocumentos({ conversaId, garantirConversa, disabled = false }: Props) {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const espacos = useEdenOrg((s) => s.espacos);
  const [aberto, setAberto] = useState(false);
  const [lista, setLista] = useState<Documento[] | null>(null);
  const [limites, setLimites] = useState<LimitesDocumentos | null>(null);
  const [anexados, setAnexados] = useState<Documento[]>([]);
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Éden (Parte 4): trazer uma página do Notion (se a chave estiver no .env).
  const [notionOk, setNotionOk] = useState(false);
  const [doNotion, setDoNotion] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelado = false;
    if (!conversaId) {
      setAnexados([]);
      return;
    }
    documentosDaConversa(conversaId)
      .then((r) => {
        if (!cancelado) setAnexados(r.documentos);
      })
      .catch(() => {
        if (!cancelado) setAnexados([]);
      });
    return () => {
      cancelado = true;
    };
  }, [conversaId]);

  const carregarLista = useCallback(async () => {
    try {
      const r = await listarDocumentos(espacoAtivo);
      setLista(r.documentos);
      setLimites(r.limites);
    } catch (e) {
      setErro((e as Error).message);
    }
  }, [espacoAtivo]);

  useEffect(() => {
    if (aberto) void carregarLista();
  }, [aberto, carregarLista]);

  useEffect(() => {
    if (!aberto) return;
    let ativo = true;
    statusNotion()
      .then((s) => {
        if (ativo) setNotionOk(s.configurado);
      })
      .catch(() => {});
    return () => {
      ativo = false;
    };
  }, [aberto]);

  const anexar = async (doc: Documento) => {
    setErro(null);
    try {
      const conversa = conversaId ?? garantirConversa();
      setAnexados((await anexarDocumento(conversa, doc.id)).documentos);
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const desanexar = async (doc: Documento) => {
    if (!conversaId) return;
    setErro(null);
    try {
      setAnexados((await desanexarDocumento(conversaId, doc.id)).documentos);
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const enviar = async (arquivo: File) => {
    setErro(null);
    setOcupado(`Lendo "${arquivo.name}"…`);
    try {
      const doc = await enviarDocumento(espacoAtivo, arquivo);
      await carregarLista();
      await anexar(doc);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const trazerDoNotion = async (pagina: PaginaNotion) => {
    setErro(null);
    setOcupado(`Trazendo "${pagina.titulo}" do Notion…`);
    try {
      const { documento } = await importarDoNotion(espacoAtivo, pagina.id);
      setDoNotion(false);
      await carregarLista();
      await anexar(documento);
      if (documento.aviso) setErro(documento.aviso);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(null);
    }
  };

  const apagar = async (doc: Documento) => {
    if (!window.confirm(`Apagar "${doc.nome}" do Éden? Ele sai de todas as conversas. O arquivo no seu aparelho não muda.`)) {
      return;
    }
    setErro(null);
    try {
      await apagarDocumento(doc.id);
      setAnexados((a) => a.filter((d) => d.id !== doc.id));
      await carregarLista();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const idsAnexados = new Set(anexados.map((d) => d.id));
  const anexadosAqui = anexados.filter((d) => d.espaco === espacoAtivo);
  const nomeEspaco = espacos.find((e) => e.id === espacoAtivo)?.nome ?? espacoAtivo;
  const porConversa = limites?.por_conversa ?? 3;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => setAberto((v) => !v)}
          disabled={disabled}
          aria-expanded={aberto}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
          style={chipStyle}
        >
          <Paperclip size={12} /> Documentos{anexadosAqui.length ? ` (${anexadosAqui.length})` : ''}
        </button>
        {anexados.map((d) => {
          const deOutroEspaco = d.espaco !== espacoAtivo;
          return (
            <span
              key={d.id}
              className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full text-[11px] max-w-[14rem]"
              style={{ ...chipStyle, opacity: deOutroEspaco ? 0.55 : 1 }}
              title={deOutroEspaco ? 'Documento de outro espaço: não vai para o Éden neste espaço' : detalhesDocumento(d)}
            >
              <FileText size={11} className="shrink-0" />
              <span className="truncate">{d.nome}</span>
              <button
                type="button"
                onClick={() => void desanexar(d)}
                disabled={disabled}
                aria-label={`Tirar ${d.nome} da conversa`}
                className="p-0.5 rounded-full cursor-pointer disabled:cursor-default"
              >
                <X size={11} />
              </button>
            </span>
          );
        })}
      </div>

      {aberto && (
        <div
          className="rounded-xl p-3 flex flex-col gap-2 text-xs"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
          role="region"
          aria-label="Documentos do espaço"
        >
          <div className="flex items-center justify-between gap-2">
            <span style={{ color: 'var(--color-text)' }}>Documentos de {nomeEspaco}</span>
            <button
              type="button"
              onClick={() => setAberto(false)}
              aria-label="Fechar documentos"
              className="p-1 rounded cursor-pointer"
              style={{ color: 'var(--color-text-tertiary)' }}
            >
              <X size={14} />
            </button>
          </div>
          <p className="leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
            PDF, Word (.docx), .txt ou .md, até 10 MB. O Éden guarda só o texto. Até {porConversa} por
            conversa; documento grande vai só em parte para a IA (e cada mensagem custa um pouco mais).
          </p>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            aria-label="Escolher arquivo"
            onChange={(e) => {
              const arquivo = e.target.files?.[0];
              if (arquivo) void enviar(arquivo);
            }}
          />
          <div>
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={disabled || ocupado !== null}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
              style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' }}
            >
              <Upload size={12} /> Enviar arquivo
            </button>
            {notionOk && (
              <button
                type="button"
                onClick={() => setDoNotion((v) => !v)}
                disabled={disabled || ocupado !== null}
                aria-expanded={doNotion}
                className="ml-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
                style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
              >
                <BookOpen size={12} /> Do Notion
              </button>
            )}
          </div>
          {notionOk && doNotion && (
            <EdenNotionPicker acao="Trazer" onEscolher={trazerDoNotion} disabled={disabled || ocupado !== null} />
          )}
          {ocupado && (
            <p role="status" style={{ color: 'var(--color-text-secondary)' }}>
              {ocupado}
            </p>
          )}
          {erro && (
            <p role="alert" style={{ color: 'var(--color-error)' }}>
              {erro}
            </p>
          )}
          {lista === null ? (
            <p style={{ color: 'var(--color-text-tertiary)' }}>Carregando…</p>
          ) : lista.length === 0 ? (
            <p style={{ color: 'var(--color-text-tertiary)' }}>Nenhum documento neste espaço ainda.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {lista.map((d) => {
                const emUso = idsAnexados.has(d.id);
                const cortado = vaiCortado(d.caracteres, Math.max(1, anexadosAqui.length + (emUso ? 0 : 1)), limites?.no_contexto);
                return (
                  <li
                    key={d.id}
                    className="flex items-center gap-2 rounded-lg px-2 py-1.5"
                    style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
                  >
                    <FileText size={14} className="shrink-0" style={{ color: 'var(--color-text-tertiary)' }} />
                    <div className="flex-1 min-w-0">
                      <div className="truncate" style={{ color: 'var(--color-text)' }}>
                        {d.nome}
                      </div>
                      <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                        {detalhesDocumento(d)}
                        {cortado ? ' · vai só uma parte' : ''}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void (emUso ? desanexar(d) : anexar(d))}
                      disabled={disabled || (!emUso && anexados.length >= porConversa)}
                      aria-pressed={emUso}
                      className="px-2 py-1 rounded-md text-[11px] cursor-pointer disabled:cursor-default disabled:opacity-50 shrink-0"
                      style={{
                        background: emUso ? 'var(--color-accent-subtle)' : 'transparent',
                        border: `1px solid ${emUso ? 'var(--color-accent)' : 'var(--color-border)'}`,
                        color: emUso ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                      }}
                    >
                      {emUso ? 'Em uso' : 'Usar aqui'}
                    </button>
                    <button
                      type="button"
                      onClick={() => void apagar(d)}
                      disabled={disabled}
                      aria-label={`Apagar ${d.nome}`}
                      className="p-1 rounded cursor-pointer disabled:cursor-default shrink-0"
                      style={{ color: 'var(--color-text-tertiary)' }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
