// Éden (Parte 5): e-mail (Gmail) só para ler. Lista os mais recentes, abre um
// e-mail (só o texto, sem imagens nem links ativos) e manda para a conversa
// como documento ("Usar na conversa").
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Mail, MessageSquarePlus, RefreshCw, Search, X } from 'lucide-react';
import { EdenPage, EdenSection, Empty, ErrorLine, GhostButton, PrimaryButton, inputStyle } from '../components/Eden/EdenUi';
import { useEdenOrg } from '../lib/eden-org';
import {
  importarEmail,
  lerEmail,
  listarEmails,
  quando,
  remetente,
  statusEmail,
  type Email,
  type ResumoEmail,
  type StatusEmail,
} from '../lib/eden-email';

const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

function Aberto({ id, onFechar }: { id: string; onFechar: () => void }) {
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const navigate = useNavigate();
  const [email, setEmail] = useState<Email | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    lerEmail(id)
      .then((r) => {
        if (ativo) setEmail(r.mensagem);
      })
      .catch((e) => {
        if (ativo) setErro((e as Error).message);
      });
    return () => {
      ativo = false;
    };
  }, [id]);

  const usar = async () => {
    setErro(null);
    try {
      await importarEmail(espacoAtivo, id);
      setAviso('Pronto: o e-mail está em Documentos. Marque "Usar aqui" na conversa.');
      window.setTimeout(() => navigate('/'), 1200);
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <EdenSection
      title={email ? email.assunto : 'Abrindo…'}
      aside={
        <GhostButton onClick={onFechar} aria-label="Fechar e-mail">
          <X size={12} /> Fechar
        </GhostButton>
      }
    >
      <ErrorLine message={erro} />
      {email && (
        <div className="flex flex-col gap-2 text-sm">
          <div className="text-xs" style={cor3}>
            De {remetente(email)} {email.de.email && email.de.nome ? `<${email.de.email}>` : ''} ·{' '}
            {quando(email.recebido_em)}
          </div>
          <pre
            className="whitespace-pre-wrap break-words text-sm leading-relaxed max-h-[60vh] overflow-auto rounded-lg p-3"
            style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', fontFamily: 'inherit' }}
          >
            {email.texto || email.trecho}
          </pre>
          <div className="flex flex-wrap items-center gap-2">
            <PrimaryButton onClick={() => void usar()}>
              <MessageSquarePlus size={12} /> Usar na conversa
            </PrimaryButton>
            <span className="text-[11px]" style={cor3}>
              Vira documento do espaço ativo (só o texto). O Éden não responde nem apaga e-mails.
            </span>
          </div>
          {aviso && (
            <p role="status" className="text-xs" style={{ color: 'var(--color-success)' }}>
              {aviso}
            </p>
          )}
        </div>
      )}
    </EdenSection>
  );
}

export function EdenEmailPage() {
  const [status, setStatus] = useState<StatusEmail | null>(null);
  const [lista, setLista] = useState<ResumoEmail[] | null>(null);
  const [busca, setBusca] = useState('');
  const [aberto, setAberto] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async (texto = '', atualizar = false) => {
    setCarregando(true);
    try {
      const s = await statusEmail();
      setStatus(s);
      if (s.conectado) {
        const r = await listarEmails(texto, atualizar);
        setLista(r.mensagens);
        if (r.aviso) setErro(r.aviso);
        else setErro(null);
      }
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <EdenPage
      title="E-mail"
      actions={
        status?.conectado ? (
          <GhostButton onClick={() => void carregar(busca, true)} disabled={carregando}>
            <RefreshCw size={12} /> Atualizar
          </GhostButton>
        ) : undefined
      }
    >
      <ErrorLine message={erro} />
      {status === null ? (
        <Empty>Carregando…</Empty>
      ) : !status.conectado ? (
        <EdenSection title="E-mail ainda não conectado">
          <p className="text-sm" style={cor2}>
            Em <strong>Configurações → E-mail</strong>, conecte a conta do Gmail que o Éden pode ler (pode ser uma conta
            separada, só para isso). O Éden só lê: não manda, não apaga e não arquiva nada.
          </p>
        </EdenSection>
      ) : (
        <>
          {aberto && <Aberto key={aberto} id={aberto} onFechar={() => setAberto(null)} />}
          <EdenSection title={status.conta ? `Caixa de entrada · ${status.conta}` : 'Caixa de entrada'}>
            <div className="flex items-center gap-2 mb-2">
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void carregar(busca);
                }}
                placeholder="Buscar (ex.: from:ana, orçamento, is:unread)"
                aria-label="Buscar e-mails"
                className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm outline-none"
                style={inputStyle}
              />
              <GhostButton onClick={() => void carregar(busca)} disabled={carregando}>
                <Search size={12} /> Buscar
              </GhostButton>
            </div>
            {lista === null ? (
              <Empty>Carregando…</Empty>
            ) : lista.length === 0 ? (
              <Empty>Nenhum e-mail nos últimos 7 dias (ou na busca).</Empty>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {lista.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => setAberto(m.id)}
                      className="w-full text-left flex items-start gap-2 rounded-lg px-3 py-2 cursor-pointer"
                      style={{ border: '1px solid var(--color-border)' }}
                    >
                      <Mail
                        size={14}
                        className="mt-0.5 shrink-0"
                        style={{ color: m.nao_lido ? 'var(--color-accent)' : 'var(--color-text-tertiary)' }}
                      />
                      <span className="flex-1 min-w-0">
                        <span className="flex items-center justify-between gap-2">
                          <span
                            className="truncate text-sm"
                            style={{ color: 'var(--color-text)', fontWeight: m.nao_lido ? 600 : 400 }}
                          >
                            {remetente(m)}
                          </span>
                          <span className="text-[11px] shrink-0" style={cor3}>
                            {quando(m.recebido_em)}
                          </span>
                        </span>
                        <span className="block truncate text-xs" style={cor2}>
                          {m.assunto}
                        </span>
                        <span className="block truncate text-[11px]" style={cor3}>
                          {m.trecho}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] mt-2" style={cor3}>
              Na conversa, pergunte por exemplo "chegou e-mail do cliente?" — o Éden olha os mais recentes (só leitura).
            </p>
          </EdenSection>
        </>
      )}
    </EdenPage>
  );
}
