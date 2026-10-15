// Éden (Parte 2): perfil e memória. O que está aqui o Éden lê nas conversas
// (o perfil sempre; as memórias do espaço ativo e as que valem para todos).
import { useCallback, useEffect, useState } from 'react';
import { Pencil, Trash2, Plus, Save, X } from 'lucide-react';
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
import { edenJson, nomeEspaco, useEdenOrg, type Memoria } from '../lib/eden-org';

const MAX_PERFIL = 4000;
const MAX_MEMORIA = 500;

function Perfil() {
  const [texto, setTexto] = useState('');
  const [salvo, setSalvo] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    edenJson<{ perfil: { texto: string } }>('/perfil')
      .then(({ perfil }) => {
        setTexto(perfil.texto);
        setSalvo(perfil.texto);
      })
      .catch((e) => setErro((e as Error).message));
  }, []);

  const salvar = async () => {
    setOcupado(true);
    setErro(null);
    try {
      const { perfil } = await edenJson<{ perfil: { texto: string } }>('/perfil', {
        method: 'PUT',
        body: { texto },
      });
      setTexto(perfil.texto);
      setSalvo(perfil.texto);
      toast.success('Perfil salvo');
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <EdenSection title="Sobre você">
      <p className="text-xs mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
        O Éden lê isto em todas as conversas: como te chamar, rotina, preferências, jeito de trabalhar.
      </p>
      <textarea
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        maxLength={MAX_PERFIL}
        rows={6}
        aria-label="Sobre você"
        placeholder="Ex.: Me chamo Levi. Trabalho com foto e vídeo (LS Visuals). Prefiro respostas curtas."
        className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
        style={inputStyle}
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
          {texto.length}/{MAX_PERFIL}
        </span>
        <PrimaryButton onClick={salvar} disabled={ocupado || texto === salvo}>
          <Save size={14} />
          Salvar
        </PrimaryButton>
      </div>
      <ErrorLine message={erro} />
    </EdenSection>
  );
}

function ItemMemoria({ memoria, onMudou }: { memoria: Memoria; onMudou: () => void }) {
  const espacos = useEdenOrg((s) => s.espacos);
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(memoria.texto);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    setErro(null);
    try {
      await edenJson(`/memorias/${memoria.id}`, { method: 'PATCH', body: { texto } });
      setEditando(false);
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const apagar = async () => {
    if (!window.confirm(`Apagar esta memória?\n\n“${memoria.texto}”`)) return;
    try {
      await edenJson(`/memorias/${memoria.id}`, { method: 'DELETE' });
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <li className="py-2.5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      {editando ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={MAX_MEMORIA}
            rows={2}
            aria-label="Texto da memória"
            className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
            style={inputStyle}
          />
          <div className="flex gap-2">
            <PrimaryButton onClick={salvar} disabled={!texto.trim()}>
              <Save size={14} /> Salvar
            </PrimaryButton>
            <GhostButton
              onClick={() => {
                setTexto(memoria.texto);
                setEditando(false);
              }}
            >
              <X size={14} /> Cancelar
            </GhostButton>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm break-words" style={{ color: 'var(--color-text)' }}>
              {memoria.texto}
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge tone={memoria.espaco === null ? 'accent' : 'neutral'}>
                {nomeEspaco(espacos, memoria.espaco)}
              </Badge>
              {memoria.origem === 'eden' && <Badge>sugerida pelo Éden</Badge>}
            </div>
          </div>
          <IconButton label="Editar memória" onClick={() => setEditando(true)}>
            <Pencil size={15} />
          </IconButton>
          <IconButton label="Apagar memória" onClick={apagar}>
            <Trash2 size={15} />
          </IconButton>
        </div>
      )}
      <ErrorLine message={erro} />
    </li>
  );
}

function Memorias() {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const espacos = useEdenOrg((s) => s.espacos);
  const [itens, setItens] = useState<Memoria[] | null>(null);
  const [novo, setNovo] = useState('');
  const [paraTodos, setParaTodos] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(() => {
    edenJson<{ memorias: Memoria[] }>(`/memorias?espaco=${encodeURIComponent(espacoAtivo)}`)
      .then(({ memorias }) => setItens(memorias))
      .catch((e) => setErro((e as Error).message));
  }, [espacoAtivo]);

  useEffect(() => {
    carregar();
    window.addEventListener('eden-org-mudou', carregar);
    return () => window.removeEventListener('eden-org-mudou', carregar);
  }, [carregar]);

  const adicionar = async () => {
    setErro(null);
    try {
      await edenJson('/memorias', {
        method: 'POST',
        body: { texto: novo, espaco: paraTodos ? null : espacoAtivo },
      });
      setNovo('');
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <EdenSection title={`Memórias — ${nomeEspaco(espacos, espacoAtivo)}`}>
      <p className="text-xs mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
        Fatos que o Éden deve lembrar. Aparecem as deste espaço e as que valem para todos. O Éden
        também pode sugerir memórias na conversa; elas só entram se você confirmar.
      </p>
      {itens === null ? (
        <Empty>Carregando…</Empty>
      ) : itens.length === 0 ? (
        <Empty>Nenhuma memória ainda.</Empty>
      ) : (
        <ul>
          {itens.map((m) => (
            <ItemMemoria key={m.id} memoria={m} onMudou={carregar} />
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-col gap-2">
        <textarea
          value={novo}
          onChange={(e) => setNovo(e.target.value)}
          maxLength={MAX_MEMORIA}
          rows={2}
          aria-label="Nova memória"
          placeholder="Ex.: Reuniões com clientes só de manhã."
          className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
          style={inputStyle}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="inline-flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            <input type="checkbox" checked={paraTodos} onChange={(e) => setParaTodos(e.target.checked)} />
            Vale para todos os espaços
          </label>
          <PrimaryButton onClick={adicionar} disabled={!novo.trim()}>
            <Plus size={14} /> Guardar
          </PrimaryButton>
        </div>
      </div>
      <ErrorLine message={erro} />
    </EdenSection>
  );
}

export function EdenMemoryPage() {
  return (
    <EdenPage title="Perfil e memória" actions={<EdenSpaceSelect />}>
      <PilotNotice />
      <Perfil />
      <Memorias />
    </EdenPage>
  );
}
