// Éden (Parte 2): tarefas e lembretes do espaço ativo (ou de todos).
// O que a pessoa faz aqui vale direto; o que o Éden sugere na conversa passa
// pelo cartão de confirmação.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bell, BellOff, Check, ChevronDown, ChevronRight, Plus, Save, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
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
import {
  atrasada,
  edenJson,
  hojeIso,
  horaDe,
  nomeEspaco,
  textoData,
  useEdenOrg,
  type Tarefa,
} from '../lib/eden-org';

const MAX_TITULO = 200;

function Circulo({ feita, onClick, label }: { feita: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={feita}
      aria-label={label}
      onClick={onClick}
      className="shrink-0 inline-flex items-center justify-center rounded-full cursor-pointer"
      style={{
        width: 24,
        height: 24,
        marginTop: 1,
        border: `2px solid ${feita ? 'var(--color-success)' : 'var(--color-border)'}`,
        background: feita ? 'var(--color-success)' : 'transparent',
        color: 'var(--color-on-accent, white)',
      }}
    >
      {feita && <Check size={14} />}
    </button>
  );
}

function EditarTarefa({ tarefa, onFechar, onMudou }: { tarefa: Tarefa; onFechar: () => void; onMudou: () => void }) {
  const espacos = useEdenOrg((s) => s.espacos);
  const [titulo, setTitulo] = useState(tarefa.titulo);
  const [data, setData] = useState(tarefa.data ?? '');
  const [hora, setHora] = useState(tarefa.hora ?? '');
  const [lembrete, setLembrete] = useState(tarefa.lembrete_em !== null);
  const [notas, setNotas] = useState(tarefa.notas);
  const [espaco, setEspaco] = useState(tarefa.espaco);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    setErro(null);
    try {
      await edenJson(`/tarefas/${tarefa.id}`, {
        method: 'PATCH',
        body: { titulo, data: data || null, hora: hora || null, lembrete: lembrete && !!data, notas, espaco },
      });
      onMudou();
      onFechar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const apagar = async () => {
    if (!window.confirm(`Apagar a tarefa “${tarefa.titulo}”?`)) return;
    try {
      await edenJson(`/tarefas/${tarefa.id}`, { method: 'DELETE' });
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="mt-2 flex flex-col gap-2">
      <input
        value={titulo}
        onChange={(e) => setTitulo(e.target.value)}
        maxLength={MAX_TITULO}
        aria-label="Título da tarefa"
        className="w-full text-sm px-3 py-2 rounded-lg outline-none"
        style={inputStyle}
      />
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="date"
          value={data}
          onChange={(e) => setData(e.target.value)}
          aria-label="Data"
          className="text-sm px-2 py-1.5 rounded-lg outline-none"
          style={inputStyle}
        />
        <input
          type="time"
          value={hora}
          disabled={!data}
          onChange={(e) => setHora(e.target.value)}
          aria-label="Horário"
          className="text-sm px-2 py-1.5 rounded-lg outline-none disabled:opacity-50"
          style={inputStyle}
        />
        <label className="inline-flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          <input type="checkbox" checked={lembrete && !!data} disabled={!data} onChange={(e) => setLembrete(e.target.checked)} />
          Lembrete
        </label>
        <select
          value={espaco}
          onChange={(e) => setEspaco(e.target.value)}
          aria-label="Espaço da tarefa"
          className="text-sm px-2 py-1.5 rounded-lg outline-none"
          style={inputStyle}
        >
          {espacos.map((e) => (
            <option key={e.id} value={e.id}>
              {e.nome}
            </option>
          ))}
        </select>
      </div>
      <textarea
        value={notas}
        onChange={(e) => setNotas(e.target.value)}
        maxLength={4000}
        rows={2}
        placeholder="Notas (opcional)"
        aria-label="Notas da tarefa"
        className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
        style={inputStyle}
      />
      <div className="flex flex-wrap gap-2">
        <PrimaryButton onClick={salvar} disabled={!titulo.trim()}>
          <Save size={14} /> Salvar
        </PrimaryButton>
        <GhostButton onClick={onFechar}>
          <X size={14} /> Fechar
        </GhostButton>
        <GhostButton onClick={apagar} className="ml-auto">
          <Trash2 size={14} /> Apagar
        </GhostButton>
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}

export function LinhaTarefa({ tarefa, mostrarEspaco, onMudou }: { tarefa: Tarefa; mostrarEspaco: boolean; onMudou: () => void }) {
  const espacos = useEdenOrg((s) => s.espacos);
  const [aberta, setAberta] = useState(false);
  const hoje = hojeIso();

  const alternar = async () => {
    try {
      await edenJson(`/tarefas/${tarefa.id}`, { method: 'PATCH', body: { feita: !tarefa.feita } });
      if (!tarefa.feita) toast.success('Feita!');
      onMudou();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <li className="py-2.5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-start gap-3">
        <Circulo feita={tarefa.feita} onClick={alternar} label={tarefa.feita ? 'Reabrir tarefa' : 'Marcar como feita'} />
        <button
          type="button"
          onClick={() => setAberta((v) => !v)}
          className="min-w-0 flex-1 text-left cursor-pointer"
          aria-expanded={aberta}
        >
          <p
            className="text-sm break-words"
            style={{
              color: tarefa.feita ? 'var(--color-text-tertiary)' : 'var(--color-text)',
              textDecoration: tarefa.feita ? 'line-through' : undefined,
            }}
          >
            {tarefa.titulo}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {tarefa.data && (
              <Badge tone={atrasada(tarefa, hoje) ? 'warning' : tarefa.data === hoje ? 'accent' : 'neutral'}>
                {textoData(tarefa.data, tarefa.hora, hoje)}
              </Badge>
            )}
            {tarefa.lembrete_em !== null && !tarefa.feita && (
              <Badge>
                <Bell size={10} /> {horaDe(tarefa.lembrete_em)}
              </Badge>
            )}
            {mostrarEspaco && <Badge>{nomeEspaco(espacos, tarefa.espaco)}</Badge>}
            {tarefa.origem === 'eden' && <Badge>pelo Éden</Badge>}
            {tarefa.notas && (
              <span className="text-[11px] truncate max-w-[14rem]" style={{ color: 'var(--color-text-tertiary)' }}>
                {tarefa.notas}
              </span>
            )}
          </div>
        </button>
      </div>
      {aberta && <EditarTarefa tarefa={tarefa} onFechar={() => setAberta(false)} onMudou={onMudou} />}
    </li>
  );
}

function NovaTarefa({ espaco, onCriada }: { espaco: string; onCriada: () => void }) {
  const [titulo, setTitulo] = useState('');
  const [data, setData] = useState('');
  const [hora, setHora] = useState('');
  const [lembrete, setLembrete] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const criar = async () => {
    if (!titulo.trim()) return;
    setOcupado(true);
    setErro(null);
    try {
      await edenJson('/tarefas', {
        method: 'POST',
        body: { titulo, espaco, data: data || null, hora: hora || null, lembrete: lembrete && !!data },
      });
      setTitulo('');
      setHora('');
      setLembrete(false);
      onCriada();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <EdenSection title="Nova tarefa">
      <div className="flex flex-col gap-2">
        <input
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          maxLength={MAX_TITULO}
          placeholder="O que precisa ser feito?"
          aria-label="Nova tarefa"
          className="w-full text-sm px-3 py-2 rounded-lg outline-none"
          style={inputStyle}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) void criar();
          }}
        />
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
            aria-label="Data da nova tarefa"
            className="text-sm px-2 py-1.5 rounded-lg outline-none"
            style={inputStyle}
          />
          <GhostButton onClick={() => setData(hojeIso())}>Hoje</GhostButton>
          <input
            type="time"
            value={hora}
            disabled={!data}
            onChange={(e) => setHora(e.target.value)}
            aria-label="Horário da nova tarefa"
            className="text-sm px-2 py-1.5 rounded-lg outline-none disabled:opacity-50"
            style={inputStyle}
          />
          <button
            type="button"
            disabled={!data}
            onClick={() => setLembrete((v) => !v)}
            aria-pressed={lembrete && !!data}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs cursor-pointer disabled:opacity-50 disabled:cursor-default"
            style={{
              background: lembrete && data ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
              color: lembrete && data ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              border: `1px solid ${lembrete && data ? 'var(--color-accent)' : 'var(--color-border)'}`,
              minHeight: 36,
            }}
          >
            {lembrete && data ? <Bell size={13} /> : <BellOff size={13} />}
            Lembrete
          </button>
          <PrimaryButton onClick={criar} disabled={ocupado || !titulo.trim()} className="ml-auto">
            <Plus size={14} /> Adicionar
          </PrimaryButton>
        </div>
        {lembrete && data && (
          <p className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
            O lembrete toca {hora ? `às ${hora}` : 'às 09:00'} do dia {textoData(data, null)}.
          </p>
        )}
      </div>
      <ErrorLine message={erro} />
    </EdenSection>
  );
}

function Grupo({ titulo, tarefas, mostrarEspaco, onMudou }: { titulo: string; tarefas: Tarefa[]; mostrarEspaco: boolean; onMudou: () => void }) {
  if (tarefas.length === 0) return null;
  return (
    <EdenSection title={`${titulo} (${tarefas.length})`}>
      <ul>
        {tarefas.map((t) => (
          <LinhaTarefa key={t.id} tarefa={t} mostrarEspaco={mostrarEspaco} onMudou={onMudou} />
        ))}
      </ul>
    </EdenSection>
  );
}

export function EdenTasksPage() {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const [todos, setTodos] = useState(false);
  const [abertas, setAbertas] = useState<Tarefa[] | null>(null);
  const [feitas, setFeitas] = useState<Tarefa[]>([]);
  const [verFeitas, setVerFeitas] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const filtro = todos ? 'todos' : espacoAtivo;

  const carregar = useCallback(() => {
    const q = `espaco=${encodeURIComponent(filtro)}`;
    Promise.all([
      edenJson<{ tarefas: Tarefa[] }>(`/tarefas?${q}&estado=abertas`),
      edenJson<{ tarefas: Tarefa[] }>(`/tarefas?${q}&estado=feitas`),
    ])
      .then(([a, f]) => {
        setAbertas(a.tarefas);
        setFeitas(f.tarefas.slice(0, 30));
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, [filtro]);

  useEffect(() => {
    carregar();
    const onFocus = () => carregar();
    window.addEventListener('eden-org-mudou', carregar);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('eden-org-mudou', carregar);
      window.removeEventListener('focus', onFocus);
    };
  }, [carregar]);

  const grupos = useMemo(() => {
    const hoje = hojeIso();
    const lista = abertas ?? [];
    return {
      atrasadas: lista.filter((t) => t.data && t.data < hoje),
      hoje: lista.filter((t) => t.data === hoje),
      proximas: lista.filter((t) => t.data && t.data > hoje),
      semData: lista.filter((t) => !t.data),
    };
  }, [abertas]);

  return (
    <EdenPage
      title="Tarefas"
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
      <NovaTarefa espaco={espacoAtivo} onCriada={carregar} />
      <ErrorLine message={erro} />
      {abertas === null ? (
        <Empty>Carregando…</Empty>
      ) : abertas.length === 0 ? (
        <EdenSection title="Abertas">
          <Empty>Nenhuma tarefa aberta. Peça ao Éden na conversa ou adicione acima.</Empty>
        </EdenSection>
      ) : (
        <>
          <Grupo titulo="Atrasadas" tarefas={grupos.atrasadas} mostrarEspaco={todos} onMudou={carregar} />
          <Grupo titulo="Hoje" tarefas={grupos.hoje} mostrarEspaco={todos} onMudou={carregar} />
          <Grupo titulo="Próximas" tarefas={grupos.proximas} mostrarEspaco={todos} onMudou={carregar} />
          <Grupo titulo="Sem data" tarefas={grupos.semData} mostrarEspaco={todos} onMudou={carregar} />
        </>
      )}
      {feitas.length > 0 && (
        <EdenSection
          title={`Feitas (${feitas.length})`}
          aside={
            <IconButton label={verFeitas ? 'Esconder feitas' : 'Mostrar feitas'} onClick={() => setVerFeitas((v) => !v)}>
              {verFeitas ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </IconButton>
          }
        >
          {verFeitas ? (
            <ul>
              {feitas.map((t) => (
                <LinhaTarefa key={t.id} tarefa={t} mostrarEspaco={todos} onMudou={carregar} />
              ))}
            </ul>
          ) : (
            <Empty>Toque na seta para ver.</Empty>
          )}
        </EdenSection>
      )}
    </EdenPage>
  );
}
