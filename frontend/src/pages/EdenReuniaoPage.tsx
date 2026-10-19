// Éden: modo reunião. A pessoa liga quando quiser; o Éden grava em pedaços,
// transcreve e, no fim, faz o resumo (tópicos, decisões, quem faz o quê,
// datas). As tarefas viram cartões para confirmar. Nunca escuta sozinho.
import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Mic, Square, Trash2, RotateCcw, ChevronRight, Loader2, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { EdenPage, EdenSection, ErrorLine, GhostButton, PilotNotice, PrimaryButton, Empty, Badge, inputStyle } from '../components/Eden/EdenUi';
import { EdenSpaceSelect } from '../components/Chat/EdenSpaceSelect';
import { EdenActionCards } from '../components/Chat/EdenActionCards';
import { SafeImage, SafeLink } from '../components/Chat/EdenSafeMarkdown';
import { EdenNucleo } from '../components/Eden/EdenNucleo';
import { useNucleoStore } from '../lib/eden-nucleo';
import { nomeEspaco, useEdenOrg } from '../lib/eden-org';
import type { EdenActionRef } from '../lib/eden-acoes';
import {
  abrirReuniao,
  apagarReuniao,
  cartoesDeNovo,
  comecarReuniao,
  duracaoTexto,
  GravadorDeReuniao,
  listarReunioes,
  terminarReuniao,
  type Reuniao,
  type ReuniaoCompleta,
  type SituacaoGravador,
} from '../lib/eden-reuniao';

const ESTADO_TEXTO: Record<string, string> = {
  gravando: 'gravando',
  resumindo: 'fazendo o resumo',
  pronta: 'pronta',
  erro: 'sem resumo',
};

function quando(ms: number): string {
  return new Date(ms).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function paraCartao(a: ReuniaoCompleta['cartoes'][number]): EdenActionRef {
  return { id: a.id, tipo: a.tipo, resumo: a.resumo, assinatura: a.assinatura, estado: a.estado, expira_em: a.expira_em };
}

export function EdenReuniaoPage() {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const espacos = useEdenOrg((s) => s.espacos);
  const setOuvindo = useNucleoStore((s) => s.setOuvindo);
  const [lista, setLista] = useState<Reuniao[]>([]);
  const [aberta, setAberta] = useState<ReuniaoCompleta | null>(null);
  const [titulo, setTitulo] = useState('');
  const [avisei, setAvisei] = useState(false);
  const [gravando, setGravando] = useState<{ id: number; inicio: number } | null>(null);
  const [situacao, setSituacao] = useState<SituacaoGravador | null>(null);
  const [agora, setAgora] = useState(() => Date.now());
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const gravadorRef = useRef<GravadorDeReuniao | null>(null);

  const carregarLista = useCallback(() => {
    listarReunioes()
      .then((r) => setLista(r.reunioes))
      .catch(() => {});
  }, []);

  useEffect(() => {
    carregarLista();
  }, [carregarLista]);

  // Relógio da gravação e aviso ao fechar a página no meio.
  useEffect(() => {
    if (!gravando) return;
    const t = window.setInterval(() => setAgora(Date.now()), 1000);
    const aoSair = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', aoSair);
    return () => {
      clearInterval(t);
      window.removeEventListener('beforeunload', aoSair);
    };
  }, [gravando]);

  // Saiu da página: para de gravar (o que já foi gravado continua subindo).
  useEffect(
    () => () => {
      gravadorRef.current?.parar();
      setOuvindo(false);
    },
    [setOuvindo],
  );

  const abrir = useCallback(async (id: number) => {
    setErro(null);
    try {
      const { reuniao } = await abrirReuniao(id);
      setAberta(reuniao);
    } catch (e) {
      setErro((e as Error).message);
    }
  }, []);

  // Enquanto o resumo é feito, confere de 3 em 3 segundos.
  useEffect(() => {
    if (!aberta || aberta.estado !== 'resumindo') return;
    const t = window.setTimeout(() => {
      void abrir(aberta.id);
      carregarLista();
    }, 3000);
    return () => clearTimeout(t);
  }, [aberta, abrir, carregarLista]);

  const comecar = async () => {
    setOcupado(true);
    setErro(null);
    let criada: number | null = null;
    try {
      const { reuniao } = await comecarReuniao(titulo.trim() || 'Reunião', espacoAtivo);
      criada = reuniao.id;
      const g = new GravadorDeReuniao(reuniao.id, setSituacao);
      try {
        await g.comecar();
      } catch (e) {
        g.parar(); // microfone e tela não ficam presos
        throw e;
      }
      gravadorRef.current = g;
      setGravando({ id: reuniao.id, inicio: Date.now() });
      setAgora(Date.now());
      setAberta(null);
      setOuvindo(true);
    } catch (e) {
      if (criada !== null) await apagarReuniao(criada).catch(() => {});
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
      carregarLista();
    }
  };

  const terminar = async () => {
    const g = gravadorRef.current;
    if (!g || !gravando) return;
    setOcupado(true);
    setErro(null);
    try {
      await g.terminar();
    } catch (e) {
      setErro(`${(e as Error).message} O áudio continua guardado aqui; toque em "Mandar de novo".`);
      setOcupado(false);
      return;
    }
    setOuvindo(false);
    const id = gravando.id;
    gravadorRef.current = null;
    setGravando(null);
    setSituacao(null);
    setTitulo('');
    setAvisei(false);
    try {
      await terminarReuniao(id);
    } catch (e) {
      setErro((e as Error).message);
    }
    await abrir(id);
    carregarLista();
    setOcupado(false);
  };

  const cancelar = async () => {
    if (!gravando) return;
    if (!window.confirm('Parar e apagar esta gravação? O que foi transcrito também é apagado.')) return;
    gravadorRef.current?.cancelar();
    gravadorRef.current = null;
    setOuvindo(false);
    const id = gravando.id;
    setGravando(null);
    setSituacao(null);
    await apagarReuniao(id).catch(() => {});
    carregarLista();
  };

  const resumirDeNovo = async (id: number) => {
    setErro(null);
    try {
      await terminarReuniao(id);
      await abrir(id);
      carregarLista();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const apagar = async (id: number) => {
    if (!window.confirm('Apagar esta reunião? O resumo, a transcrição e os cartões ainda não confirmados somem (backups antigos ainda guardam uma cópia).')) return;
    try {
      await apagarReuniao(id);
      setAberta(null);
      carregarLista();
      toast.success('Reunião apagada.');
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const recriarCartoes = async (id: number) => {
    setErro(null);
    try {
      await cartoesDeNovo(id);
      await abrir(id);
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const aoMudarCartao = useCallback((acaoId: string, mudanca: Partial<EdenActionRef>) => {
    setAberta((a) =>
      a ? { ...a, cartoes: a.cartoes.map((c) => (c.id === acaoId ? { ...c, ...mudanca } : c)) } : a,
    );
  }, []);

  return (
    <EdenPage title="Modo reunião">
      {gravando ? (
        <EdenSection title="Gravando">
          <div className="flex flex-col items-center gap-3 py-2 text-center">
            <EdenNucleo tamanho={132} estado="ouvindo" />
            <p className="eden-titulo tabular-nums" style={{ color: 'var(--color-text)' }} aria-live="off">
              {duracaoTexto((agora - gravando.inicio) / 1000)}
            </p>
            <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {situacao?.enviados ?? 0} pedaço(s) enviados
              {situacao && situacao.naFila > 0 ? ` · ${situacao.naFila} esperando` : ''}
              {situacao?.tentando ? ' · sem conexão, tentando de novo' : ''}
            </p>
            <p className="text-xs max-w-sm" style={{ color: 'var(--color-text-tertiary)' }}>
              Deixe a tela ligada e o Éden aberto nesta página. No iPhone, a gravação para se a tela travar ou se você
              trocar de app.
            </p>
            <div className="flex flex-wrap justify-center gap-2 pt-1">
              <PrimaryButton onClick={terminar} disabled={ocupado}>
                {ocupado ? <Loader2 size={16} className="animate-spin" /> : <Square size={14} />}
                Terminar e resumir
              </PrimaryButton>
              {situacao?.erro && (
                <GhostButton onClick={() => gravadorRef.current?.tentarDeNovo()}>
                  <RotateCcw size={14} />
                  Mandar de novo
                </GhostButton>
              )}
              <GhostButton onClick={cancelar} disabled={ocupado}>
                <Trash2 size={14} />
                Cancelar
              </GhostButton>
            </div>
            <ErrorLine message={situacao?.erro ?? erro} />
          </div>
        </EdenSection>
      ) : aberta ? (
        <EdenSection
          title={aberta.titulo}
          aside={
            <GhostButton onClick={() => setAberta(null)} aria-label="Fechar a reunião">
              Fechar
            </GhostButton>
          }
        >
          <p className="text-xs mb-3" style={{ color: 'var(--color-text-tertiary)' }}>
            {quando(aberta.criado_em)} · {duracaoTexto(aberta.segundos)} · {nomeEspaco(espacos, aberta.espaco)}
          </p>
          {aberta.estado === 'resumindo' && (
            <p className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              <Loader2 size={14} className="animate-spin" /> Fazendo o resumo… (leva até um minuto)
            </p>
          )}
          {aberta.estado === 'gravando' && (
            <div className="flex flex-col gap-2">
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Esta gravação foi interrompida (a página fechou no meio). Dá para resumir o que chegou até ali.
              </p>
              <div className="flex flex-wrap gap-2">
                <PrimaryButton onClick={() => resumirDeNovo(aberta.id)}>Resumir o que foi gravado</PrimaryButton>
              </div>
            </div>
          )}
          {aberta.estado === 'erro' && (
            <div className="flex flex-col gap-2">
              <p className="flex items-start gap-2 text-sm" style={{ color: 'var(--color-warning)' }}>
                <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {aberta.erro || 'Não deu para resumir.'}
              </p>
              <div>
                <PrimaryButton onClick={() => resumirDeNovo(aberta.id)}>
                  <RotateCcw size={14} />
                  Tentar o resumo de novo
                </PrimaryButton>
              </div>
            </div>
          )}
          {aberta.estado === 'pronta' && aberta.resumo && (
            <div className="prose max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: SafeLink, img: SafeImage }}>
                {aberta.resumo}
              </ReactMarkdown>
            </div>
          )}
          {aberta.cartoes.length > 0 && (
            <div className="mt-3">
              <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                Tarefas sugeridas (nada é criado sem você confirmar; cada cartão vale 15 minutos):
              </p>
              <EdenActionCards
                messageId={`reuniao-${aberta.id}`}
                actions={aberta.cartoes.map(paraCartao)}
                aoMudar={aoMudarCartao}
              />
            </div>
          )}
          {aberta.estado === 'pronta' &&
            aberta.tarefas.length > 0 &&
            !aberta.cartoes.some((c) => c.estado === 'pendente' && c.expira_em > Date.now()) && (
              <div className="mt-2">
                <GhostButton onClick={() => recriarCartoes(aberta.id)}>
                  <RotateCcw size={14} />
                  Mostrar os cartões das tarefas de novo
                </GhostButton>
              </div>
            )}
          {aberta.transcricao && (
            <details className="mt-4 text-sm">
              <summary className="cursor-pointer" style={{ color: 'var(--color-text-secondary)' }}>
                Ver a transcrição
              </summary>
              <p
                className="mt-2 text-xs leading-relaxed whitespace-pre-wrap break-words"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {aberta.transcricao}
              </p>
            </details>
          )}
          <div className="mt-4">
            <GhostButton onClick={() => apagar(aberta.id)}>
              <Trash2 size={14} />
              Apagar reunião
            </GhostButton>
          </div>
          <ErrorLine message={erro} />
        </EdenSection>
      ) : (
        <EdenSection title="Nova reunião">
          <div className="flex flex-col gap-3">
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              O Éden só escuta enquanto você deixar gravando. No fim, ele faz o resumo: tópicos, decisões, quem ficou
              de fazer o quê e as datas. As tarefas viram cartões para você confirmar.
            </p>
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Nome da reunião (opcional)"
              aria-label="Nome da reunião"
              maxLength={120}
              className="text-sm px-3 py-2 rounded-lg outline-none"
              style={inputStyle}
            />
            <EdenSpaceSelect label="Tarefas vão para" />
            <label className="flex items-start gap-2 text-sm cursor-pointer" style={{ color: 'var(--color-text)' }}>
              <input
                type="checkbox"
                checked={avisei}
                onChange={(e) => setAvisei(e.target.checked)}
                className="mt-1"
              />
              <span>Avisei as pessoas da reunião que o Éden está gravando.</span>
            </label>
            <PilotNotice />
            <div>
              <PrimaryButton onClick={comecar} disabled={!avisei || ocupado}>
                {ocupado ? <Loader2 size={16} className="animate-spin" /> : <Mic size={16} />}
                Começar a gravar
              </PrimaryButton>
            </div>
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              Custo aproximado: US$ 0,30 a 0,40 por hora de reunião (transcrição + resumo), dentro do limite do mês. O
              áudio não fica guardado; só o texto.
            </p>
            <ErrorLine message={erro} />
          </div>
        </EdenSection>
      )}

      <EdenSection title="Reuniões anteriores">
        {lista.length === 0 ? (
          <Empty>Nenhuma reunião ainda.</Empty>
        ) : (
          <ul className="flex flex-col">
            {lista.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => abrir(r.id)}
                  disabled={Boolean(gravando)}
                  className="w-full flex items-center gap-2 py-2.5 text-left cursor-pointer disabled:cursor-default disabled:opacity-60"
                  style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm truncate" style={{ color: 'var(--color-text)' }}>
                      {r.titulo}
                    </div>
                    <div className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                      {quando(r.criado_em)} · {duracaoTexto(r.segundos)}
                    </div>
                  </div>
                  <Badge tone={r.estado === 'pronta' ? 'success' : r.estado === 'erro' ? 'warning' : 'accent'}>
                    {ESTADO_TEXTO[r.estado] ?? r.estado}
                  </Badge>
                  <ChevronRight size={14} style={{ color: 'var(--color-text-tertiary)' }} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </EdenSection>
    </EdenPage>
  );
}
