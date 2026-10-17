// Éden (Parte 3): ligar a Google Agenda (Configurações). O Éden só ganha a
// permissão de eventos da agenda; a autorização fica cifrada no servidor.
import { useCallback, useEffect, useState } from 'react';
import { CalendarDays, Copy, RefreshCw, Unlink } from 'lucide-react';
import { GhostButton, PrimaryButton } from './EdenUi';
import { edenJson } from '../../lib/eden-org';
import {
  desconectarAgenda,
  mensagemDaVolta,
  statusAgenda,
  urlParaConectar,
  type StatusAgenda,
} from '../../lib/eden-agenda';

function lerVolta(): string | null {
  try {
    const params = new URLSearchParams(window.location.search);
    const situacao = params.get('google');
    if (situacao) {
      params.delete('google');
      const resto = params.toString();
      window.history.replaceState(null, '', window.location.pathname + (resto ? `?${resto}` : ''));
    }
    return situacao;
  } catch {
    return null;
  }
}

export function EdenGoogleSettings() {
  const [status, setStatus] = useState<StatusAgenda | null>(null);
  const [erro, setErro] = useState('');
  const [busy, setBusy] = useState(false);
  const [volta, setVolta] = useState(() => mensagemDaVolta(lerVolta()));
  const [copiado, setCopiado] = useState(false);

  const carregar = useCallback(() => {
    statusAgenda()
      .then((s) => {
        setStatus(s);
        setErro('');
      })
      .catch((e) => setErro((e as Error).message));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const conectar = async () => {
    setBusy(true);
    setErro('');
    try {
      window.location.assign(await urlParaConectar());
    } catch (e) {
      setErro((e as Error).message);
      setBusy(false);
    }
  };

  const desconectar = async () => {
    if (!window.confirm('Desligar a Google Agenda do Éden? A sua agenda no Google não muda.')) return;
    setBusy(true);
    try {
      const r = await desconectarAgenda();
      setVolta(
        r.revogado === false
          ? {
              ok: false,
              texto:
                'Desligada aqui. O Google não confirmou: se quiser, remova o acesso do "Éden" na sua conta do Google (Segurança → Apps e serviços de terceiros).',
            }
          : { ok: true, texto: 'Desligada. O Google também retirou o acesso do Éden.' },
      );
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const atualizar = async () => {
    setBusy(true);
    try {
      await edenJson('/google/atualizar', { method: 'POST' });
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copiar = async (texto: string) => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Sem acesso à área de transferência: a pessoa seleciona o texto.
    }
  };

  const texto = 'text-xs leading-relaxed';
  const cor = { color: 'var(--color-text-secondary)' };

  return (
    <div className="flex flex-col items-start gap-3">
      {volta && (
        <p className="text-xs" role="status" style={{ color: volta.ok ? 'var(--color-success)' : 'var(--color-warning)' }}>
          {volta.texto}
        </p>
      )}
      {erro && (
        <p className="text-xs" role="alert" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
      {status === null ? (
        <p className={texto} style={cor}>
          Carregando…
        </p>
      ) : !status.configurado ? (
        <>
          <p className={texto} style={cor}>
            Ainda não configurada. É preciso criar um projeto grátis no Google e colocar o ID e o
            segredo no arquivo .env do Éden (passo a passo no LEIA-ME).
          </p>
          {status.endereco_retorno ? (
            <div className="flex flex-col gap-1">
              <span className={texto} style={cor}>
                Endereço de retorno para colocar no Google:
              </span>
              <div className="flex items-center gap-2 flex-wrap">
                <code className="text-xs px-2 py-1 rounded select-all break-all" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)' }}>
                  {status.endereco_retorno}
                </code>
                <GhostButton onClick={() => copiar(status.endereco_retorno ?? '')}>
                  <Copy size={12} /> {copiado ? 'Copiado' : 'Copiar'}
                </GhostButton>
              </div>
            </div>
          ) : (
            <p className={texto} style={{ color: 'var(--color-warning)' }}>
              Antes, rode o iniciar-eden com o Tailscale ligado (o Google precisa do endereço com cadeado).
            </p>
          )}
        </>
      ) : !status.conectado ? (
        <>
          <p className={texto} style={cor}>
            O Éden vai poder ler os seus eventos e sugerir eventos novos ou mudanças, sempre com o cartão de
            confirmação. Só a permissão da agenda é pedida. Faça de preferência no notebook.
          </p>
          <PrimaryButton onClick={conectar} disabled={busy}>
            <CalendarDays size={14} /> {busy ? 'Abrindo o Google…' : 'Conectar a Google Agenda'}
          </PrimaryButton>
        </>
      ) : (
        <>
          <p className={texto} style={{ color: 'var(--color-success)' }}>
            Conectada.
            {status.atualizado_em
              ? ` Agenda atualizada às ${new Date(status.atualizado_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}.`
              : ''}
          </p>
          <div className="flex flex-wrap gap-2">
            <GhostButton onClick={atualizar} disabled={busy}>
              <RefreshCw size={12} /> Atualizar agora
            </GhostButton>
            <GhostButton onClick={desconectar} disabled={busy}>
              <Unlink size={12} /> Desconectar
            </GhostButton>
          </div>
        </>
      )}
    </div>
  );
}
