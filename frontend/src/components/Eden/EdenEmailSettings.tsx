// Éden (Parte 5): ligar o e-mail (Gmail) só para ler. Pode ser outra conta,
// diferente da da agenda. A autorização fica cifrada no servidor.
import { useCallback, useEffect, useState } from 'react';
import { Mail, Unlink } from 'lucide-react';
import { GhostButton, PrimaryButton } from './EdenUi';
import { desconectarEmail, mensagemDaVoltaEmail, statusEmail, urlConectarEmail, type StatusEmail } from '../../lib/eden-email';

function lerVolta(): string | null {
  try {
    const params = new URLSearchParams(window.location.search);
    const situacao = params.get('email');
    if (situacao) {
      params.delete('email');
      const resto = params.toString();
      window.history.replaceState(null, '', window.location.pathname + (resto ? `?${resto}` : ''));
    }
    return situacao;
  } catch {
    return null;
  }
}

const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

export function EdenEmailSettings() {
  const [status, setStatus] = useState<StatusEmail | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [volta] = useState(() => mensagemDaVoltaEmail(lerVolta()));
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    statusEmail()
      .then((s) => {
        setStatus(s);
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const conectar = async () => {
    setOcupado(true);
    setErro(null);
    try {
      window.location.assign(await urlConectarEmail());
    } catch (e) {
      setErro((e as Error).message);
      setOcupado(false);
    }
  };

  const desconectar = async () => {
    if (!window.confirm('Desconectar o e-mail? O Éden para de ler a caixa de entrada.')) return;
    setErro(null);
    try {
      const r = await desconectarEmail();
      if (r.motivo === 'agenda_ligada') {
        setErro(
          'Desligado aqui. Como a Google Agenda também está ligada, o Éden não retirou a permissão no Google (se fosse a mesma conta, a agenda cairia junto). Para retirar de vez: myaccount.google.com → Segurança → Apps de terceiros.',
        );
      } else if (!r.revogado) {
        setErro('Desligado aqui. Para garantir, retire o acesso do Éden em myaccount.google.com → Segurança → Apps de terceiros.');
      }
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-2 text-sm" style={cor2}>
      {volta && (
        <p role="status" className="text-xs" style={{ color: 'var(--color-text)' }}>
          {volta}
        </p>
      )}
      {status === null ? (
        <p className="text-xs" style={cor3}>
          {erro ?? 'Carregando…'}
        </p>
      ) : !status.configurado ? (
        <p className="text-xs">
          Precisa do Google configurado no servidor (o mesmo da agenda). Veja o LEIA-ME, seção <strong>E-mail</strong>.
        </p>
      ) : status.conectado ? (
        <div className="flex flex-wrap items-center gap-2">
          <Mail size={14} style={{ color: 'var(--color-accent)' }} />
          <span>
            Conectado{status.conta ? `: ${status.conta}` : ''} (só leitura)
          </span>
          <GhostButton onClick={() => void desconectar()}>
            <Unlink size={12} /> Desconectar
          </GhostButton>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs">
            Conecte a conta do Gmail que o Éden pode <strong>ler</strong> (pode ser uma conta separada, só para isso). Ele
            não manda, não apaga e não arquiva e-mails. Na tela do Google, entre com essa conta e marque a permissão de
            ler os e-mails.
          </p>
          <div>
            <PrimaryButton onClick={() => void conectar()} disabled={ocupado}>
              <Mail size={12} /> Conectar e-mail
            </PrimaryButton>
          </div>
        </div>
      )}
      {erro && status !== null && (
        <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
    </div>
  );
}
