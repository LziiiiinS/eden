// Éden (Parte 4): procurar uma página do Notion (só as que a pessoa
// compartilhou com a conexão do Éden) e escolher uma.
import { useState } from 'react';
import { Search } from 'lucide-react';
import { buscarNotion, editadaEm, type PaginaNotion } from '../../lib/eden-notion';
import { inputStyle } from './EdenUi';

interface Props {
  /** Texto do botão de cada resultado (ex.: "Trazer", "Usar esta"). */
  acao: string;
  onEscolher: (pagina: PaginaNotion) => void | Promise<void>;
  disabled?: boolean;
}

export function EdenNotionPicker({ acao, onEscolher, disabled = false }: Props) {
  const [texto, setTexto] = useState('');
  const [resultados, setResultados] = useState<PaginaNotion[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const buscar = async () => {
    setErro(null);
    setOcupado(true);
    try {
      setResultados((await buscarNotion(texto.trim())).resultados);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void buscar();
            }
          }}
          placeholder="Nome da página (vazio = as mais recentes)"
          aria-label="Procurar página no Notion"
          className="flex-1 min-w-0 px-3 py-1.5 rounded-lg text-xs outline-none"
          style={inputStyle}
        />
        <button
          type="button"
          onClick={() => void buscar()}
          disabled={disabled || ocupado}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
          style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
        >
          <Search size={12} /> {ocupado ? 'Procurando…' : 'Procurar'}
        </button>
      </div>
      {erro && (
        <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
      {resultados && resultados.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
          Nada encontrado. No Notion, abra a página → ••• → Conexões e adicione a conexão do Éden.
        </p>
      )}
      {resultados && resultados.length > 0 && (
        <ul className="flex flex-col gap-1">
          {resultados.map((p) => (
            <li
              key={p.id}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs"
              style={{ background: 'var(--color-bg)', border: '1px solid var(--color-border)' }}
            >
              <div className="flex-1 min-w-0">
                <div className="truncate" style={{ color: 'var(--color-text)' }}>
                  {p.titulo}
                </div>
                {p.editado_em && (
                  <div className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                    {editadaEm(p.editado_em)}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => void onEscolher(p)}
                disabled={disabled}
                aria-label={`${acao}: ${p.titulo}`}
                className="px-2 py-1 rounded-md text-[11px] cursor-pointer disabled:cursor-default disabled:opacity-50 shrink-0"
                style={{ border: '1px solid var(--color-accent)', color: 'var(--color-accent)' }}
              >
                {acao}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
