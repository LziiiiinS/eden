// Éden (Parte 5): contas e impostos do espaço ativo (ou de todos).
// O Éden só anota e avisa: não paga nada, não liga em banco e não emite nota.
// O que a pessoa faz aqui vale direto; o que o Éden sugere na conversa passa
// pelo cartão de confirmação.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bell, Check, ChevronDown, ChevronRight, Plus, Repeat, RotateCcw, Save, Trash2, X } from 'lucide-react';
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
import { edenJson, hojeIso, nomeEspaco, textoData, useEdenOrg } from '../lib/eden-org';
import {
  agrupar,
  MODELOS,
  reais,
  TEXTO_REPETE,
  textoAviso,
  valorParaCampo,
  type Conta,
  type Modelo,
  type Repete,
  type ResumoContas,
  type TipoConta,
} from '../lib/eden-contas';

const MAX_DESCRICAO = 120;
const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

interface Campos {
  tipo: TipoConta;
  descricao: string;
  valor: string;
  vencimento: string;
  repete: Repete;
  categoria: string;
  aviso_dias: number;
  notas: string;
  espaco: string;
}

function camposDe(conta: Conta): Campos {
  return {
    tipo: conta.tipo,
    descricao: conta.descricao,
    valor: valorParaCampo(conta.valor_centavos),
    vencimento: conta.vencimento,
    repete: conta.repete,
    categoria: conta.categoria,
    aviso_dias: conta.aviso_dias,
    notas: conta.notas,
    espaco: conta.espaco,
  };
}

function Formulario({
  campos,
  mudar,
  mostrarNotas = true,
}: {
  campos: Campos;
  mudar: (parcial: Partial<Campos>) => void;
  mostrarNotas?: boolean;
}) {
  const espacos = useEdenOrg((s) => s.espacos);
  const sel = 'text-sm px-2 py-1.5 rounded-lg outline-none';
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={campos.tipo}
          onChange={(e) => mudar({ tipo: e.target.value as TipoConta })}
          aria-label="Tipo"
          className={sel}
          style={inputStyle}
        >
          <option value="pagar">A pagar</option>
          <option value="receber">A receber</option>
        </select>
        <input
          value={campos.descricao}
          onChange={(e) => mudar({ descricao: e.target.value })}
          maxLength={MAX_DESCRICAO}
          placeholder={campos.tipo === 'pagar' ? 'Ex.: Aluguel, internet, DAS' : 'Ex.: Cliente, nota emitida'}
          aria-label="Descrição"
          className="flex-1 min-w-[12rem] text-sm px-3 py-2 rounded-lg outline-none"
          style={inputStyle}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={campos.valor}
          onChange={(e) => mudar({ valor: e.target.value })}
          inputMode="decimal"
          placeholder="Valor (ex.: 150,00)"
          aria-label="Valor em reais"
          className="w-36 text-sm px-3 py-2 rounded-lg outline-none"
          style={inputStyle}
        />
        <input
          type="date"
          value={campos.vencimento}
          onChange={(e) => mudar({ vencimento: e.target.value })}
          aria-label="Vencimento"
          className={sel}
          style={inputStyle}
        />
        <select
          value={campos.repete}
          onChange={(e) => mudar({ repete: e.target.value as Repete })}
          aria-label="Repete"
          className={sel}
          style={inputStyle}
        >
          <option value="nao">Uma vez</option>
          <option value="mensal">Todo mês</option>
          <option value="anual">Todo ano</option>
        </select>
        <select
          value={campos.aviso_dias}
          onChange={(e) => mudar({ aviso_dias: Number(e.target.value) })}
          aria-label="Aviso no celular"
          className={sel}
          style={inputStyle}
        >
          <option value={-1}>Sem aviso</option>
          <option value={0}>Aviso no dia</option>
          <option value={1}>Aviso 1 dia antes</option>
          <option value={2}>Aviso 2 dias antes</option>
          <option value={3}>Aviso 3 dias antes</option>
          <option value={7}>Aviso 7 dias antes</option>
          <option value={15}>Aviso 15 dias antes</option>
        </select>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={campos.categoria}
          onChange={(e) => mudar({ categoria: e.target.value })}
          maxLength={40}
          placeholder="Categoria (opcional)"
          aria-label="Categoria"
          className="w-48 text-sm px-3 py-2 rounded-lg outline-none"
          style={inputStyle}
        />
        <select
          value={campos.espaco}
          onChange={(e) => mudar({ espaco: e.target.value })}
          aria-label="Espaço"
          className={sel}
          style={inputStyle}
        >
          {espacos.map((e) => (
            <option key={e.id} value={e.id}>
              {e.nome}
            </option>
          ))}
        </select>
      </div>
      {mostrarNotas && (
        <textarea
          value={campos.notas}
          onChange={(e) => mudar({ notas: e.target.value })}
          maxLength={1000}
          rows={2}
          placeholder="Notas (opcional)"
          aria-label="Notas"
          className="w-full text-sm px-3 py-2 rounded-lg outline-none resize-y"
          style={inputStyle}
        />
      )}
    </div>
  );
}

function EditarConta({ conta, onFechar, onMudou }: { conta: Conta; onFechar: () => void; onMudou: () => void }) {
  const [campos, setCampos] = useState<Campos>(() => camposDe(conta));
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    setErro(null);
    try {
      await edenJson(`/contas/${conta.id}`, { method: 'PATCH', body: campos });
      onMudou();
      onFechar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const apagar = async () => {
    if (!window.confirm(`Apagar a conta “${conta.descricao}”?`)) return;
    try {
      await edenJson(`/contas/${conta.id}`, { method: 'DELETE' });
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const reabrir = async () => {
    try {
      await edenJson(`/contas/${conta.id}/reabrir`, { method: 'POST' });
      onMudou();
      onFechar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="mt-2 flex flex-col gap-2">
      <Formulario campos={campos} mudar={(p) => setCampos((c) => ({ ...c, ...p }))} />
      <div className="flex flex-wrap gap-2">
        <PrimaryButton onClick={salvar} disabled={!campos.descricao.trim() || !campos.vencimento}>
          <Save size={14} /> Salvar
        </PrimaryButton>
        <GhostButton onClick={onFechar}>
          <X size={14} /> Fechar
        </GhostButton>
        {conta.paga && (
          <GhostButton onClick={reabrir}>
            <RotateCcw size={14} /> Voltar para em aberto
          </GhostButton>
        )}
        <GhostButton onClick={apagar} className="ml-auto">
          <Trash2 size={14} /> Apagar
        </GhostButton>
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}

function LinhaConta({ conta, mostrarEspaco, onMudou }: { conta: Conta; mostrarEspaco: boolean; onMudou: () => void }) {
  const espacos = useEdenOrg((s) => s.espacos);
  const [aberta, setAberta] = useState(false);
  const hoje = hojeIso();
  const atrasada = !conta.paga && conta.vencimento < hoje;

  const pagar = async () => {
    const verbo = conta.tipo === 'pagar' ? 'paga' : 'recebida';
    try {
      const r = await edenJson<{ proxima: Conta | null }>(`/contas/${conta.id}/pagar`, { method: 'POST' });
      toast.success(
        r.proxima ? `Marcada como ${verbo}. A próxima ficou para ${textoData(r.proxima.vencimento, null)}.` : `Marcada como ${verbo}.`,
      );
      onMudou();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <li className="py-2.5" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-start gap-3">
        {!conta.paga ? (
          <button
            type="button"
            onClick={pagar}
            aria-label={conta.tipo === 'pagar' ? 'Marcar como paga' : 'Marcar como recebida'}
            title={conta.tipo === 'pagar' ? 'Marcar como paga' : 'Marcar como recebida'}
            className="shrink-0 inline-flex items-center justify-center rounded-full cursor-pointer"
            style={{ width: 24, height: 24, marginTop: 1, border: '2px solid var(--color-border)', background: 'transparent' }}
          />
        ) : (
          <span
            className="shrink-0 inline-flex items-center justify-center rounded-full"
            style={{ width: 24, height: 24, marginTop: 1, background: 'var(--color-success)', color: 'var(--color-on-accent, white)' }}
          >
            <Check size={14} />
          </span>
        )}
        <button
          type="button"
          onClick={() => setAberta((v) => !v)}
          className="min-w-0 flex-1 text-left cursor-pointer"
          aria-expanded={aberta}
        >
          <div className="flex items-baseline justify-between gap-2">
            <p
              className="text-sm break-words"
              style={{
                color: conta.paga ? 'var(--color-text-tertiary)' : 'var(--color-text)',
                textDecoration: conta.paga ? 'line-through' : undefined,
              }}
            >
              {conta.descricao}
            </p>
            <span
              className="text-sm font-medium shrink-0 tabular-nums"
              style={{ color: conta.tipo === 'receber' ? 'var(--color-success)' : 'var(--color-text)' }}
            >
              {conta.tipo === 'receber' && conta.valor_centavos ? '+ ' : ''}
              {reais(conta.valor_centavos)}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <Badge tone={atrasada ? 'warning' : conta.vencimento === hoje ? 'accent' : 'neutral'}>
              {atrasada ? 'venceu ' : ''}
              {textoData(conta.vencimento, null, hoje)}
            </Badge>
            {conta.tipo === 'receber' && <Badge tone="success">a receber</Badge>}
            {conta.repete !== 'nao' && (
              <Badge>
                <Repeat size={10} /> {TEXTO_REPETE[conta.repete]}
              </Badge>
            )}
            {!conta.paga && conta.aviso_dias >= 0 && (
              <Badge>
                <Bell size={10} /> {textoAviso(conta.aviso_dias)}
              </Badge>
            )}
            {conta.categoria && <Badge>{conta.categoria}</Badge>}
            {mostrarEspaco && <Badge>{nomeEspaco(espacos, conta.espaco)}</Badge>}
            {conta.origem === 'eden' && <Badge>pelo Éden</Badge>}
          </div>
        </button>
      </div>
      {aberta && <EditarConta conta={conta} onFechar={() => setAberta(false)} onMudou={onMudou} />}
    </li>
  );
}

function vazia(espaco: string): Campos {
  return {
    tipo: 'pagar',
    descricao: '',
    valor: '',
    vencimento: '',
    repete: 'nao',
    categoria: '',
    aviso_dias: 2,
    notas: '',
    espaco,
  };
}

function NovaConta({ espaco, onCriada }: { espaco: string; onCriada: () => void }) {
  const [campos, setCampos] = useState<Campos>(() => vazia(espaco));
  const [dica, setDica] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    setCampos((c) => ({ ...c, espaco }));
  }, [espaco]);

  const usarModelo = (m: Modelo) => {
    setCampos((c) => ({
      ...c,
      tipo: m.tipo,
      descricao: m.descricao,
      repete: m.repete,
      categoria: m.categoria,
      vencimento: m.vencimento(),
      aviso_dias: m.aviso_dias,
    }));
    setDica(m.dica);
  };

  const criar = async () => {
    setOcupado(true);
    setErro(null);
    try {
      await edenJson('/contas', { method: 'POST', body: campos });
      setCampos(vazia(espaco));
      setDica(null);
      onCriada();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <EdenSection title="Nova conta">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs" style={cor3}>
          Modelos:
          {MODELOS.map((m) => (
            <GhostButton key={m.rotulo} onClick={() => usarModelo(m)}>
              {m.rotulo}
            </GhostButton>
          ))}
        </div>
        <Formulario campos={campos} mudar={(p) => setCampos((c) => ({ ...c, ...p }))} mostrarNotas={false} />
        {dica && (
          <p className="text-[11px]" style={cor3}>
            {dica}
          </p>
        )}
        <div className="flex">
          <PrimaryButton
            onClick={criar}
            disabled={ocupado || !campos.descricao.trim() || !campos.vencimento}
            className="ml-auto"
          >
            <Plus size={14} /> Anotar
          </PrimaryButton>
        </div>
      </div>
      <ErrorLine message={erro} />
    </EdenSection>
  );
}

function Grupo({ titulo, contas, mostrarEspaco, onMudou }: { titulo: string; contas: Conta[]; mostrarEspaco: boolean; onMudou: () => void }) {
  if (contas.length === 0) return null;
  return (
    <EdenSection title={`${titulo} (${contas.length})`}>
      <ul>
        {contas.map((c) => (
          <LinhaConta key={c.id} conta={c} mostrarEspaco={mostrarEspaco} onMudou={onMudou} />
        ))}
      </ul>
    </EdenSection>
  );
}

function Quadro({ resumo }: { resumo: ResumoContas | null }) {
  if (!resumo) return null;
  const itens = [
    { rotulo: 'A pagar neste mês', valor: reais(resumo.a_pagar_no_mes) },
    { rotulo: 'A receber neste mês', valor: reais(resumo.a_receber_no_mes) },
    { rotulo: 'Atrasado', valor: reais(resumo.atrasado_a_pagar), alerta: resumo.atrasado_a_pagar > 0 },
    { rotulo: 'Recebido no ano', valor: reais(resumo.recebido_no_ano) },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
      {itens.map((i) => (
        <div
          key={i.rotulo}
          className="rounded-xl px-3 py-2"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
        >
          <p className="text-[11px]" style={cor3}>
            {i.rotulo}
          </p>
          <p
            className="text-sm font-medium tabular-nums"
            style={{ color: i.alerta ? 'var(--color-warning)' : 'var(--color-text)' }}
          >
            {i.valor === 'sem valor' ? 'R$ 0,00' : i.valor}
          </p>
        </div>
      ))}
    </div>
  );
}

export function EdenContasPage() {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const [todos, setTodos] = useState(false);
  const [abertas, setAbertas] = useState<Conta[] | null>(null);
  const [pagas, setPagas] = useState<Conta[]>([]);
  const [resumo, setResumo] = useState<ResumoContas | null>(null);
  const [verPagas, setVerPagas] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const filtro = todos ? 'todos' : espacoAtivo;

  const carregar = useCallback(() => {
    const q = `espaco=${encodeURIComponent(filtro)}`;
    Promise.all([
      edenJson<{ contas: Conta[] }>(`/contas?${q}&estado=abertas`),
      edenJson<{ contas: Conta[] }>(`/contas?${q}&estado=pagas`),
      edenJson<ResumoContas>(`/contas/resumo?${q}`),
    ])
      .then(([a, p, r]) => {
        setAbertas(a.contas);
        setPagas(p.contas.slice(0, 30));
        setResumo(r);
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

  const grupos = useMemo(() => agrupar(abertas ?? []), [abertas]);

  return (
    <EdenPage
      title="Contas"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {!todos && <EdenSpaceSelect />}
          <label className="inline-flex items-center gap-1.5 text-xs" style={cor3}>
            <input type="checkbox" checked={todos} onChange={(e) => setTodos(e.target.checked)} />
            Todos os espaços
          </label>
        </div>
      }
    >
      <PilotNotice />
      <p className="text-xs" style={cor2}>
        O Éden só anota e avisa no celular: ele não paga nada, não liga no banco e não emite nota. Valores de impostos: confira
        sempre no site oficial.
      </p>
      <Quadro resumo={resumo} />
      <NovaConta espaco={espacoAtivo} onCriada={carregar} />
      <ErrorLine message={erro} />
      {abertas === null ? (
        <Empty>Carregando…</Empty>
      ) : abertas.length === 0 ? (
        <EdenSection title="Em aberto">
          <Empty>Nenhuma conta em aberto. Anote acima ou peça ao Éden na conversa.</Empty>
        </EdenSection>
      ) : (
        <>
          <Grupo titulo="Atrasadas" contas={grupos.atrasadas} mostrarEspaco={todos} onMudou={carregar} />
          <Grupo titulo="Próximos 7 dias" contas={grupos.semana} mostrarEspaco={todos} onMudou={carregar} />
          <Grupo titulo="Depois" contas={grupos.depois} mostrarEspaco={todos} onMudou={carregar} />
        </>
      )}
      {pagas.length > 0 && (
        <EdenSection
          title={`Pagas e recebidas (${pagas.length})`}
          aside={
            <IconButton label={verPagas ? 'Esconder pagas' : 'Mostrar pagas'} onClick={() => setVerPagas((v) => !v)}>
              {verPagas ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </IconButton>
          }
        >
          {verPagas ? (
            <ul>
              {pagas.map((c) => (
                <LinhaConta key={c.id} conta={c} mostrarEspaco={todos} onMudou={carregar} />
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
