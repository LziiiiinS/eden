// Éden: casa. Luzes, tomadas, ar-condicionado e rotinas ("Chegando em casa")
// pelo Home Assistant. O toque na tela já é a confirmação; o que o Éden sugere
// na conversa vem num cartão. Endereço e token ficam só no servidor.
import { useCallback, useEffect, useState } from 'react';
import { House, Lightbulb, Plug, Wind, Sparkles, Power, Play, Pencil, Trash2, Plus, Minus, RefreshCw, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Badge, EdenPage, EdenSection, Empty, ErrorLine, GhostButton, IconButton, PrimaryButton, inputStyle } from '../components/Eden/EdenUi';
import {
  apagarRotina,
  comandar,
  lerCasa,
  lerEstados,
  NOME_ACAO,
  passoValido,
  rodarRotina,
  salvarRotina,
  textoPasso,
  valorPadrao,
  type AparelhoCasa,
  type EstadoAparelho,
  type FeitoCasa,
  type PassoCasa,
  type RotinaCasa,
  type SituacaoCasa,
} from '../lib/eden-casa';

function IconeAparelho({ dominio }: { dominio: string }) {
  if (dominio === 'light') return <Lightbulb size={18} />;
  if (dominio === 'switch') return <Plug size={18} />;
  if (dominio === 'climate') return <Wind size={18} />;
  if (dominio === 'scene') return <Sparkles size={18} />;
  return <Power size={18} />;
}

function textoEstado(e?: EstadoAparelho): { texto: string; tom: 'neutral' | 'success' | 'warning' } {
  if (!e) return { texto: '…', tom: 'neutral' };
  if (e.erro) return { texto: 'sem resposta', tom: 'warning' };
  if (e.estado === 'on' || e.estado === 'heat' || e.estado === 'cool' || e.estado === 'auto') {
    return { texto: e.temperatura ? `ligado · ${e.temperatura} °C` : 'ligado', tom: 'success' };
  }
  if (e.estado === 'off') return { texto: 'desligado', tom: 'neutral' };
  return { texto: e.estado ?? '—', tom: 'neutral' };
}

function avisarFeito(r: FeitoCasa) {
  const extra = r.demo ? ' (demonstração)' : '';
  toast.success(`Feito${extra}: ${r.feitos.join('; ')}`);
}

function CartaoAparelho({
  aparelho,
  estado,
  cores,
  ocupado,
  aoComandar,
}: {
  aparelho: AparelhoCasa;
  estado?: EstadoAparelho;
  cores: string[];
  ocupado: boolean;
  aoComandar: (p: PassoCasa) => void;
}) {
  const [temp, setTemp] = useState(estado?.temperatura ?? 22);
  const [brilho, setBrilho] = useState(70);
  const [cor, setCor] = useState(cores[0] ?? 'branca');
  const st = textoEstado(estado);
  const tem = (a: string) => aparelho.acoes.includes(a);
  const ligado = st.tom === 'success';

  return (
    <div className="eden-vidro eden-aparelho rounded-2xl p-3 flex flex-col gap-3" data-ligado={ligado ? 'sim' : 'nao'}>
      <div className="flex items-center gap-2 min-w-0">
        <span className="eden-aparelho-icone" aria-hidden>
          <IconeAparelho dominio={aparelho.dominio} />
        </span>
        <span className="text-sm font-medium truncate flex-1" style={{ color: 'var(--color-text)' }}>
          {aparelho.nome}
        </span>
        <Badge tone={st.tom}>{st.texto}</Badge>
      </div>
      <div className="flex flex-wrap gap-2">
        {tem('ligar') && (
          <GhostButton disabled={ocupado} onClick={() => aoComandar({ entidade: aparelho.entidade, acao: 'ligar' })}>
            Ligar
          </GhostButton>
        )}
        {tem('desligar') && (
          <GhostButton disabled={ocupado} onClick={() => aoComandar({ entidade: aparelho.entidade, acao: 'desligar' })}>
            Desligar
          </GhostButton>
        )}
        {tem('ativar') && (
          <GhostButton disabled={ocupado} onClick={() => aoComandar({ entidade: aparelho.entidade, acao: 'ativar' })}>
            Ativar
          </GhostButton>
        )}
        {tem('apertar') && (
          <GhostButton disabled={ocupado} onClick={() => aoComandar({ entidade: aparelho.entidade, acao: 'apertar' })}>
            Apertar
          </GhostButton>
        )}
      </div>
      {tem('temperatura') && (
        <div className="flex items-center gap-2">
          <IconButton label="Menos 1 grau" disabled={ocupado || temp <= 16} onClick={() => setTemp((t) => Math.max(16, t - 1))}>
            <Minus size={14} />
          </IconButton>
          <span className="text-lg font-semibold tabular-nums w-16 text-center" style={{ color: 'var(--color-text)' }} aria-live="polite">
            {temp} °C
          </span>
          <IconButton label="Mais 1 grau" disabled={ocupado || temp >= 30} onClick={() => setTemp((t) => Math.min(30, t + 1))}>
            <Plus size={14} />
          </IconButton>
          <PrimaryButton
            disabled={ocupado}
            onClick={() => aoComandar({ entidade: aparelho.entidade, acao: 'temperatura', valor: temp })}
          >
            Ajustar
          </PrimaryButton>
        </div>
      )}
      {tem('cor') && (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label={`Cor de ${aparelho.nome}`}>
          {cores.map((c) => (
            <button
              key={c}
              type="button"
              className="eden-cor"
              data-cor={c}
              aria-pressed={cor === c}
              title={c}
              aria-label={c}
              disabled={ocupado}
              onClick={() => {
                setCor(c);
                aoComandar({ entidade: aparelho.entidade, acao: 'cor', valor: c });
              }}
            />
          ))}
        </div>
      )}
      {tem('brilho') && (
        <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          Brilho
          <input
            type="range"
            min={1}
            max={100}
            value={brilho}
            disabled={ocupado}
            onChange={(e) => setBrilho(Number(e.target.value))}
            onPointerUp={() => aoComandar({ entidade: aparelho.entidade, acao: 'brilho', valor: brilho })}
            onKeyUp={(e) => {
              if (e.key.startsWith('Arrow')) aoComandar({ entidade: aparelho.entidade, acao: 'brilho', valor: brilho });
            }}
            className="flex-1 accent-[var(--color-accent)]"
          />
          <span className="tabular-nums w-9 text-right">{brilho}%</span>
        </label>
      )}
    </div>
  );
}

function EditorRotina({
  casa,
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  casa: SituacaoCasa;
  inicial: RotinaCasa | null;
  aoSalvar: (r: RotinaCasa) => void;
  aoCancelar: () => void;
}) {
  const primeiro = casa.aparelhos[0];
  const novoPasso = (): PassoCasa => ({ entidade: primeiro.entidade, acao: primeiro.acoes[0] });
  const [nome, setNome] = useState(inicial?.nome ?? 'Chegando em casa');
  const [passos, setPassos] = useState<PassoCasa[]>(inicial?.passos ?? [novoPasso()]);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const mudar = (i: number, p: Partial<PassoCasa>) =>
    setPassos((lista) => lista.map((x, j) => (j === i ? { ...x, ...p } : x)));

  const pronto =
    nome.trim().length > 0 && passos.length > 0 && passos.every((p) => passoValido(p, casa.aparelhos, casa.cores));

  const salvar = async () => {
    setSalvando(true);
    setErro(null);
    try {
      const r = await salvarRotina({ nome: nome.trim(), passos }, inicial?.id);
      aoSalvar(r.rotina);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não deu para salvar.');
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        Nome da rotina
        <input value={nome} maxLength={60} onChange={(e) => setNome(e.target.value)} style={inputStyle} className="rounded-lg px-3 py-2 text-sm" />
      </label>
      {passos.map((p, i) => {
        const aparelho = casa.aparelhos.find((a) => a.entidade === p.entidade) ?? primeiro;
        return (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <span className="text-xs tabular-nums w-4" style={{ color: 'var(--color-text-tertiary)' }}>
              {i + 1}.
            </span>
            <select
              aria-label={`Aparelho do passo ${i + 1}`}
              value={p.entidade}
              onChange={(e) => {
                const a = casa.aparelhos.find((x) => x.entidade === e.target.value) ?? primeiro;
                mudar(i, { entidade: a.entidade, acao: a.acoes[0], valor: valorPadrao(a.acoes[0], casa.cores) });
              }}
              style={inputStyle}
              className="rounded-lg px-2 py-1.5 text-sm"
            >
              {casa.aparelhos.map((a) => (
                <option key={a.entidade} value={a.entidade}>
                  {a.nome}
                </option>
              ))}
            </select>
            <select
              aria-label={`Ação do passo ${i + 1}`}
              value={p.acao}
              onChange={(e) => mudar(i, { acao: e.target.value, valor: valorPadrao(e.target.value, casa.cores) })}
              style={inputStyle}
              className="rounded-lg px-2 py-1.5 text-sm"
            >
              {aparelho.acoes.map((a) => (
                <option key={a} value={a}>
                  {NOME_ACAO[a] ?? a}
                </option>
              ))}
            </select>
            {p.acao === 'cor' && (
              <select
                aria-label={`Cor do passo ${i + 1}`}
                value={String(p.valor ?? '')}
                onChange={(e) => mudar(i, { valor: e.target.value })}
                style={inputStyle}
                className="rounded-lg px-2 py-1.5 text-sm"
              >
                {casa.cores.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            )}
            {(p.acao === 'temperatura' || p.acao === 'brilho') && (
              <input
                type="number"
                aria-label={p.acao === 'temperatura' ? `Graus do passo ${i + 1}` : `Brilho do passo ${i + 1}`}
                min={p.acao === 'temperatura' ? 16 : 1}
                max={p.acao === 'temperatura' ? 30 : 100}
                value={Number(p.valor ?? 0)}
                onChange={(e) => mudar(i, { valor: Math.round(Number(e.target.value)) })}
                style={inputStyle}
                className="rounded-lg px-2 py-1.5 text-sm w-20"
              />
            )}
            <IconButton label={`Tirar o passo ${i + 1}`} onClick={() => setPassos((l) => l.filter((_, j) => j !== i))}>
              <Trash2 size={14} />
            </IconButton>
          </div>
        );
      })}
      <div className="flex flex-wrap gap-2">
        <GhostButton disabled={passos.length >= 10} onClick={() => setPassos((l) => [...l, novoPasso()])}>
          <Plus size={14} /> Passo
        </GhostButton>
        <div className="flex-1" />
        <GhostButton onClick={aoCancelar}>Cancelar</GhostButton>
        <PrimaryButton disabled={!pronto || salvando} onClick={salvar}>
          {salvando ? <Loader2 size={14} className="animate-spin" /> : null} Salvar rotina
        </PrimaryButton>
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}

export function EdenCasaPage() {
  const [casa, setCasa] = useState<SituacaoCasa | null>(null);
  const [estados, setEstados] = useState<Record<string, EstadoAparelho>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [editando, setEditando] = useState<RotinaCasa | 'nova' | null>(null);

  const carregarEstados = useCallback(async () => {
    try {
      const r = await lerEstados();
      setEstados(Object.fromEntries(r.estados.map((e) => [e.entidade, e])));
    } catch {
      // Sem estado: os botões continuam funcionando.
    }
  }, []);

  const carregar = useCallback(async () => {
    try {
      const c = await lerCasa();
      setCasa(c);
      setErro(null);
      if (c.ligada) void carregarEstados();
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Não deu para abrir a casa.');
    }
  }, [carregarEstados]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const fazer = async (acao: () => Promise<FeitoCasa>) => {
    setOcupado(true);
    try {
      avisarFeito(await acao());
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Não deu.');
    } finally {
      setOcupado(false);
      void carregarEstados();
    }
  };

  const apagar = async (r: RotinaCasa) => {
    if (!window.confirm(`Apagar a rotina "${r.nome}"?`)) return;
    try {
      await apagarRotina(r.id);
      toast.success('Rotina apagada.');
      void carregar();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Não deu para apagar.');
    }
  };

  return (
    <EdenPage
      title="Casa"
      actions={
        casa?.ligada ? (
          <div className="flex items-center gap-2">
            {casa.demo && <Badge tone="warning">demonstração</Badge>}
            <IconButton label="Atualizar" onClick={() => void carregar()}>
              <RefreshCw size={16} />
            </IconButton>
          </div>
        ) : undefined
      }
    >
      <ErrorLine message={erro} />
      {casa && !casa.ligada && (
        <EdenSection title="A casa ainda não está ligada">
          <div className="flex gap-3 items-start">
            <span className="eden-aparelho-icone" aria-hidden>
              <House size={18} />
            </span>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
              O Éden mexe nas luzes, tomadas e ar-condicionado pelo Home Assistant (grátis). Depois de comprar os
              aparelhos e instalar o Home Assistant, coloque o endereço, o token e a lista de aparelhos no{' '}
              <code>.env</code> do servidor (passo a passo no LEIA-ME). Para testar sem nada em casa, ligue a
              demonstração com <code>EDEN_CASA_DEMO=1</code>.
            </p>
          </div>
        </EdenSection>
      )}
      {casa?.ligada && (
        <>
          <EdenSection title="Aparelhos">
            {casa.aparelhos.length === 0 ? (
              <Empty>Nenhum aparelho na lista do servidor.</Empty>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {casa.aparelhos.map((a) => (
                  <CartaoAparelho
                    key={a.entidade}
                    aparelho={a}
                    estado={estados[a.entidade]}
                    cores={casa.cores}
                    ocupado={ocupado}
                    aoComandar={(p) => void fazer(() => comandar(p))}
                  />
                ))}
              </div>
            )}
          </EdenSection>
          <EdenSection
            title="Rotinas"
            aside={
              editando === null && casa.aparelhos.length > 0 ? (
                <GhostButton onClick={() => setEditando('nova')}>
                  <Plus size={14} /> Nova rotina
                </GhostButton>
              ) : undefined
            }
          >
            {editando !== null ? (
              <EditorRotina
                casa={casa}
                inicial={editando === 'nova' ? null : editando}
                aoCancelar={() => setEditando(null)}
                aoSalvar={(r) => {
                  toast.success(`Rotina "${r.nome}" salva.`);
                  setEditando(null);
                  void carregar();
                }}
              />
            ) : casa.rotinas.length === 0 ? (
              <Empty>
                Nenhuma rotina ainda. Ex.: “Chegando em casa” — ar em 20 °C, computador ligado e luz azul.
              </Empty>
            ) : (
              <ul className="flex flex-col gap-2">
                {casa.rotinas.map((r) => (
                  <li key={r.id} className="eden-vidro rounded-xl p-3 flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium flex-1 truncate" style={{ color: 'var(--color-text)' }}>
                        {r.nome}
                      </span>
                      <IconButton label={`Editar ${r.nome}`} onClick={() => setEditando(r)}>
                        <Pencil size={14} />
                      </IconButton>
                      <IconButton label={`Apagar ${r.nome}`} onClick={() => void apagar(r)}>
                        <Trash2 size={14} />
                      </IconButton>
                      <PrimaryButton disabled={ocupado} onClick={() => void fazer(() => rodarRotina(r.id))}>
                        <Play size={14} /> Rodar agora
                      </PrimaryButton>
                    </div>
                    <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                      {r.passos.map((p) => textoPasso(p, casa.aparelhos)).join(' · ')}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </EdenSection>
          <p className="text-xs leading-relaxed px-1" style={{ color: 'var(--color-text-tertiary)' }}>
            Na conversa: “estou chegando em 5 minutos” → o Éden sugere a rotina num cartão, e ela roda quando você
            confirma. Ele não agenda para depois.
          </p>
        </>
      )}
    </EdenPage>
  );
}
