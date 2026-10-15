// Éden (Parte 2): notas e ideias por espaço.
import { useCallback, useEffect, useState } from 'react';
import { Lightbulb, Pencil, Pin, PinOff, Plus, Save, Search, StickyNote, Trash2, X } from 'lucide-react';
import { EdenSpaceSelect } from '../components/Chat/EdenSpaceSelect';
import {
  Badge,
  EdenPage,
  EdenSection,
  Empty,
  ErrorLine,
  GhostButton,
  IconButton,
  PilotNotice,
  PrimaryButton,
  inputStyle,
} from '../components/Eden/EdenUi';
import { edenJson, nomeEspaco, useEdenOrg, type Nota } from '../lib/eden-org';

const MAX_TEXTO = 20000;
const PREVIA = 280;

type Filtro = 'tudo' | 'nota' | 'ideia';

function TipoBotao({ tipo, ativo, onClick }: { tipo: 'nota' | 'ideia'; ativo: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={ativo}
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs cursor-pointer"
      style={{
        background: ativo ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
        color: ativo ? 'var(--color-accent)' : 'var(--color-text-secondary)',
        border: `1px solid ${ativo ? 'var(--color-accent)' : 'var(--color-border)'}`,
        minHeight: 36,
      }}
    >
      {tipo === 'ideia' ? <Lightbulb size={13} /> : <StickyNote size={13} />}
      {tipo === 'ideia' ? 'Ideia' : 'Nota'}
    </button>
  );
}

function CartaoNota({ nota, mostrarEspaco, onMudou }: { nota: Nota; mostrarEspaco: boolean; onMudou: () => void }) {
  const espacos = useEdenOrg((s) => s.espacos);
  const [editando, setEditando] = useState(false);
  const [expandida, setExpandida] = useState(false);
  const [titulo, setTitulo] = useState(nota.titulo);
  const [texto, setTexto] = useState(nota.texto);
  const [tipo, setTipo] = useState<'nota' | 'ideia'>(nota.tipo);
  const [erro, setErro] = useState<string | null>(null);

  const mudar = async (campos: Record<string, unknown>) => {
    setErro(null);
    try {
      await edenJson(`/notas/${nota.id}`, { method: 'PATCH', body: campos });
      onMudou();
      return true;
    } catch (e) {
      setErro((e as Error).message);
      return false;
    }
  };

  const apagar = async () => {
    if (!window.confirm(`Apagar ${nota.tipo === 'ideia' ? 'esta ideia' : 'esta nota'}?`)) return;
    try {
      await edenJson(`/notas/${nota.id}`, { method: 'DELETE' });
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const longo = nota.texto.length > PREVIA;

  return (
    <li
      className="rounded-xl p-3"
      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
    >
      {editando ? (
        <div className="flex flex-col gap-2">
          <input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            maxLength={200}
            placeholder="Título (opcional)"
            aria-label="Título da nota"
            className="w-full text-sm px-3 py-2 rounded-lg outline-none"
            style={inputStyle}
          />
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={MAX_TEXTO}
            rows={6}
            aria-label="Texto da nota"
            className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
            style={inputStyle}
          />
          <div className="flex flex-wrap gap-2">
            <TipoBotao tipo="nota" ativo={tipo === 'nota'} onClick={() => setTipo('nota')} />
            <TipoBotao tipo="ideia" ativo={tipo === 'ideia'} onClick={() => setTipo('ideia')} />
            <PrimaryButton
              className="ml-auto"
              disabled={!texto.trim()}
              onClick={async () => {
                if (await mudar({ titulo, texto, tipo })) setEditando(false);
              }}
            >
              <Save size={14} /> Salvar
            </PrimaryButton>
            <GhostButton
              onClick={() => {
                setTitulo(nota.titulo);
                setTexto(nota.texto);
                setTipo(nota.tipo);
                setEditando(false);
              }}
            >
              <X size={14} /> Cancelar
            </GhostButton>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              {nota.titulo && (
                <p className="text-sm font-medium break-words" style={{ color: 'var(--color-text)' }}>
                  {nota.titulo}
                </p>
              )}
              <p
                className="text-sm break-words"
                style={{ color: 'var(--color-text-secondary)', whiteSpace: 'pre-wrap' }}
              >
                {longo && !expandida ? `${nota.texto.slice(0, PREVIA)}…` : nota.texto}
              </p>
              {longo && (
                <button
                  type="button"
                  onClick={() => setExpandida((v) => !v)}
                  className="mt-1 text-xs underline cursor-pointer"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  {expandida ? 'Mostrar menos' : 'Mostrar tudo'}
                </button>
              )}
            </div>
            <div className="flex shrink-0">
              <IconButton label={nota.fixada ? 'Desafixar' : 'Fixar no topo'} onClick={() => void mudar({ fixada: !nota.fixada })}>
                {nota.fixada ? <PinOff size={15} /> : <Pin size={15} />}
              </IconButton>
              <IconButton label="Editar" onClick={() => setEditando(true)}>
                <Pencil size={15} />
              </IconButton>
              <IconButton label="Apagar" onClick={apagar}>
                <Trash2 size={15} />
              </IconButton>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">
            {nota.tipo === 'ideia' && (
              <Badge tone="accent">
                <Lightbulb size={10} /> ideia
              </Badge>
            )}
            {nota.fixada && (
              <Badge>
                <Pin size={10} /> fixada
              </Badge>
            )}
            {mostrarEspaco && <Badge>{nomeEspaco(espacos, nota.espaco)}</Badge>}
            {nota.origem === 'eden' && <Badge>pelo Éden</Badge>}
            <Badge>{new Date(nota.atualizado_em).toLocaleDateString('pt-BR')}</Badge>
          </div>
        </>
      )}
      <ErrorLine message={erro} />
    </li>
  );
}

function NovaNota({ espaco, onCriada }: { espaco: string; onCriada: () => void }) {
  const [titulo, setTitulo] = useState('');
  const [texto, setTexto] = useState('');
  const [tipo, setTipo] = useState<'nota' | 'ideia'>('nota');
  const [erro, setErro] = useState<string | null>(null);

  const criar = async () => {
    setErro(null);
    try {
      await edenJson('/notas', { method: 'POST', body: { titulo, texto, tipo, espaco } });
      setTitulo('');
      setTexto('');
      onCriada();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <EdenSection title="Nova nota ou ideia">
      <div className="flex flex-col gap-2">
        <input
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          maxLength={200}
          placeholder="Título (opcional)"
          aria-label="Título da nova nota"
          className="w-full text-sm px-3 py-2 rounded-lg outline-none"
          style={inputStyle}
        />
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          maxLength={MAX_TEXTO}
          rows={4}
          placeholder="Escreva aqui…"
          aria-label="Texto da nova nota"
          className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
          style={inputStyle}
        />
        <div className="flex flex-wrap items-center gap-2">
          <TipoBotao tipo="nota" ativo={tipo === 'nota'} onClick={() => setTipo('nota')} />
          <TipoBotao tipo="ideia" ativo={tipo === 'ideia'} onClick={() => setTipo('ideia')} />
          <PrimaryButton className="ml-auto" onClick={criar} disabled={!texto.trim()}>
            <Plus size={14} /> Guardar
          </PrimaryButton>
        </div>
      </div>
      <ErrorLine message={erro} />
    </EdenSection>
  );
}

export function EdenNotesPage() {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const [todos, setTodos] = useState(false);
  const [filtro, setFiltro] = useState<Filtro>('tudo');
  const [busca, setBusca] = useState('');
  const [buscaAplicada, setBuscaAplicada] = useState('');
  const [notas, setNotas] = useState<Nota[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // Espera a pessoa parar de digitar antes de buscar.
  useEffect(() => {
    const t = setTimeout(() => setBuscaAplicada(busca.trim()), 300);
    return () => clearTimeout(t);
  }, [busca]);

  const carregar = useCallback(() => {
    const params = new URLSearchParams({ espaco: todos ? 'todos' : espacoAtivo });
    if (filtro !== 'tudo') params.set('tipo', filtro);
    if (buscaAplicada) params.set('busca', buscaAplicada);
    edenJson<{ notas: Nota[] }>(`/notas?${params.toString()}`)
      .then(({ notas: lista }) => {
        setNotas(lista);
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, [todos, espacoAtivo, filtro, buscaAplicada]);

  useEffect(() => {
    carregar();
    window.addEventListener('eden-org-mudou', carregar);
    return () => window.removeEventListener('eden-org-mudou', carregar);
  }, [carregar]);

  return (
    <EdenPage
      title="Notas e ideias"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {!todos && <EdenSpaceSelect />}
          <label className="inline-flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} />
            Todos os espaços
          </label>
        </div>
      }
    >
      <PilotNotice />
      <NovaNota espaco={espacoAtivo} onCriada={carregar} />
      <EdenSection
        title="Guardadas"
        aside={
          <div className="flex gap-1" role="radiogroup" aria-label="Mostrar">
            {(['tudo', 'nota', 'ideia'] as Filtro[]).map((f) => (
              <button
                key={f}
                type="button"
                role="radio"
                aria-checked={filtro === f}
                onClick={() => setFiltro(f)}
                className="px-2 py-1 rounded-full text-xs cursor-pointer"
                style={{
                  background: filtro === f ? 'var(--color-accent-subtle)' : 'transparent',
                  color: filtro === f ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
                }}
              >
                {f === 'tudo' ? 'Tudo' : f === 'nota' ? 'Notas' : 'Ideias'}
              </button>
            ))}
          </div>
        }
      >
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm mb-3"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
        >
          <Search size={14} style={{ color: 'var(--color-text-tertiary)' }} />
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar nas notas…"
            aria-label="Buscar nas notas"
            className="flex-1 bg-transparent outline-none text-sm"
            style={{ color: 'var(--color-text)' }}
          />
        </div>
        <ErrorLine message={erro} />
        {notas === null ? (
          <Empty>Carregando…</Empty>
        ) : notas.length === 0 ? (
          <Empty>{buscaAplicada ? 'Nada encontrado.' : 'Nenhuma nota ainda.'}</Empty>
        ) : (
          <ul className="flex flex-col gap-2">
            {notas.map((n) => (
              <CartaoNota key={n.id} nota={n} mostrarEspaco={todos} onMudou={carregar} />
            ))}
          </ul>
        )}
      </EdenSection>
    </EdenPage>
  );
}
