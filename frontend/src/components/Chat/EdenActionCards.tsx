// Éden (Parte 2): cartões das ações que o Éden sugeriu na resposta.
// Nada acontece sem a pessoa tocar em "Confirmar". O app manda só o id e a
// assinatura do cartão; o servidor executa o que ele mesmo guardou.
import { useEffect, useState } from 'react';
import { Check, X, ListTodo, Brain, StickyNote, Clock, AlertTriangle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '../../lib/store';
import { edenJson, ErroEden, type Acao } from '../../lib/eden-org';
import { visibleState, type EdenActionRef } from '../../lib/eden-acoes';

/** Avisa as telas abertas (tarefas, notas, memória) que algo mudou. */
export function avisarMudanca(): void {
  window.dispatchEvent(new Event('eden-org-mudou'));
}

function Icone({ tipo }: { tipo: string }) {
  if (tipo.startsWith('tarefa')) return <ListTodo size={16} />;
  if (tipo.startsWith('memoria')) return <Brain size={16} />;
  return <StickyNote size={16} />;
}

const ROTULO: Record<string, string> = {
  feita: 'Feito',
  recusada: 'Recusado',
  expirada: 'Expirou — peça de novo ao Éden',
  falhou: 'Não deu para fazer',
  executando: 'Enviando…',
};

function Cartao({ messageId, acao }: { messageId: string; acao: EdenActionRef }) {
  const updateEdenAction = useAppStore((s) => s.updateEdenAction);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [agora, setAgora] = useState(() => Date.now());
  // O que o SERVIDOR guardou para esta ação. O botão Confirmar só aparece
  // depois de conferir: o resumo mostrado e a assinatura enviada são os do
  // servidor, não os que vieram na mensagem sincronizada.
  const [conferida, setConferida] = useState<Acao | null>(null);
  const [semConexao, setSemConexao] = useState(false);
  const estado = visibleState(acao, agora);

  useEffect(() => {
    if (acao.estado !== 'pendente') return;
    let cancelado = false;
    edenJson<{ acao: Acao }>(`/acoes/${encodeURIComponent(acao.id)}`)
      .then(({ acao: atual }) => {
        if (cancelado) return;
        setConferida(atual);
        setSemConexao(false);
        const mudou =
          atual.estado !== acao.estado ||
          atual.resumo !== acao.resumo ||
          atual.assinatura !== acao.assinatura;
        if (mudou) {
          updateEdenAction(messageId, acao.id, {
            estado: atual.estado,
            resumo: atual.resumo,
            assinatura: atual.assinatura,
            expira_em: atual.expira_em,
          });
        }
      })
      .catch(() => {
        if (!cancelado) setSemConexao(true);
      });
    return () => {
      cancelado = true;
    };
  }, [acao.id, acao.estado, acao.resumo, acao.assinatura, messageId, updateEdenAction]);

  // Atualiza o "expirou" sozinho.
  useEffect(() => {
    if (estado !== 'pendente') return;
    const falta = acao.expira_em - Date.now();
    if (falta <= 0) return;
    const t = setTimeout(() => setAgora(Date.now()), Math.min(falta + 500, 2 ** 31 - 1));
    return () => clearTimeout(t);
  }, [estado, acao.expira_em]);

  const decidir = async (confirmar: boolean) => {
    setOcupado(true);
    setErro(null);
    try {
      const caminho = `/acoes/${encodeURIComponent(acao.id)}/${confirmar ? 'confirmar' : 'recusar'}`;
      const { acao: nova } = await edenJson<{ acao: Acao }>(caminho, {
        method: 'POST',
        body: confirmar ? { assinatura: conferida?.assinatura ?? '' } : {},
      });
      updateEdenAction(messageId, acao.id, { estado: nova.estado });
      if (confirmar) {
        toast.success('Feito!');
        avisarMudanca();
      }
    } catch (e) {
      const err = e as ErroEden;
      if (err.code === 'eden_acao_expirada') {
        updateEdenAction(messageId, acao.id, { estado: 'expirada' });
      } else if (err.code === 'eden_acao_falhou') {
        updateEdenAction(messageId, acao.id, { estado: 'falhou' });
        setErro(err.message);
      } else if (err.code === 'eden_acao_ja_decidida') {
        try {
          const { acao: atual } = await edenJson<{ acao: Acao }>(`/acoes/${encodeURIComponent(acao.id)}`);
          updateEdenAction(messageId, acao.id, { estado: atual.estado });
        } catch {
          setErro(err.message);
        }
      } else {
        setErro(err.message || 'Não deu certo. Tente de novo.');
      }
    } finally {
      setOcupado(false);
    }
  };

  const pendente = estado === 'pendente';
  const cor =
    estado === 'feita'
      ? 'var(--color-success)'
      : estado === 'falhou'
        ? 'var(--color-error)'
        : pendente
          ? 'var(--color-accent)'
          : 'var(--color-text-tertiary)';

  return (
    <div
      className="rounded-xl px-3 py-3 text-sm"
      style={{
        background: 'var(--color-surface)',
        border: `1px solid ${pendente ? 'var(--color-accent)' : 'var(--color-border)'}`,
      }}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0" style={{ color: cor }}>
          <Icone tipo={acao.tipo} />
        </span>
        <div className="min-w-0 flex-1">
          <p
            className="leading-snug break-words overflow-y-auto"
            style={{ color: 'var(--color-text)', whiteSpace: 'pre-wrap', maxHeight: '40vh' }}
          >
            {conferida?.resumo ?? acao.resumo}
          </p>
          {pendente && !conferida ? (
            <p className="mt-1 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              {semConexao ? 'Sem conexão com o servidor; tente de novo daqui a pouco.' : 'Conferindo…'}
            </p>
          ) : pendente ? (
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={ocupado}
                onClick={() => decidir(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer disabled:opacity-60"
                style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)', minHeight: 40 }}
              >
                {ocupado ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                Confirmar
              </button>
              <button
                type="button"
                disabled={ocupado}
                onClick={() => decidir(false)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm cursor-pointer disabled:opacity-60"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                  minHeight: 40,
                }}
              >
                <X size={14} />
                Recusar
              </button>
            </div>
          ) : (
            <p className="mt-1 flex items-center gap-1.5 text-xs" style={{ color: cor }}>
              {estado === 'feita' ? <Check size={12} /> : estado === 'expirada' ? <Clock size={12} /> : estado === 'falhou' ? <AlertTriangle size={12} /> : <X size={12} />}
              {ROTULO[estado] ?? estado}
            </p>
          )}
          {erro && (
            <p className="mt-1 text-xs" role="alert" style={{ color: 'var(--color-error)' }}>
              {erro}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export function EdenActionCards({ messageId, actions }: { messageId: string; actions?: EdenActionRef[] }) {
  if (!actions || actions.length === 0) return null;
  return (
    <div className="mt-2 mb-1 flex flex-col gap-2" aria-label="Sugestões do Éden para confirmar">
      {actions.map((a) => (
        <Cartao key={a.id} messageId={messageId} acao={a} />
      ))}
    </div>
  );
}
