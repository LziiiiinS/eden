// Éden: pede a chave de acesso do servidor na primeira vez que o aparelho abre
// o Éden (ou quando a chave muda no servidor). A chave fica salva só neste
// aparelho, no navegador.
import { useEffect, useState } from 'react';
import { KeyRound } from 'lucide-react';
import { apiFetch, isTauri } from '../lib/api';
import { useAppStore } from '../lib/store';

type GateState = 'checking' | 'ok' | 'needs-key' | 'offline';

async function probe(): Promise<GateState> {
  try {
    const res = await apiFetch('/v1/eden/gastos');
    if (res.status === 401) return 'needs-key';
    return 'ok';
  } catch {
    // Sem internet ou servidor fora do ar: o aviso de servidor cuida disso.
    return 'offline';
  }
}

export function EdenAccessGate() {
  const apiKey = useAppStore((s) => s.settings.apiKey);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const [state, setState] = useState<GateState>('checking');
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isTauri()) return;
    let cancelled = false;
    probe().then((s) => {
      if (!cancelled) setState(s);
    });
    return () => {
      cancelled = true;
    };
  }, [apiKey]);

  if (state !== 'needs-key') return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = draft.trim();
    if (!key) return;
    setBusy(true);
    setError('');
    const previous = apiKey;
    updateSettings({ apiKey: key });
    const result = await probe();
    setBusy(false);
    if (result === 'ok') {
      setDraft('');
      // Recarrega para buscar modelos e conversas já com a chave.
      window.location.reload();
    } else if (result === 'needs-key') {
      updateSettings({ apiKey: previous });
      setError('Chave incorreta. Confira e tente de novo.');
    } else {
      setError('Não consegui falar com o servidor agora. Tente de novo em instantes.');
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'color-mix(in srgb, var(--color-bg) 92%, transparent)' }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="eden-gate-title"
    >
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl p-6 flex flex-col gap-4"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', boxShadow: 'var(--shadow-lg)' }}
      >
        <div className="flex items-center gap-2">
          <KeyRound size={18} style={{ color: 'var(--color-accent)' }} />
          <h2 id="eden-gate-title" className="text-base font-semibold" style={{ color: 'var(--color-text)' }}>
            Chave de acesso do Éden
          </h2>
        </div>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
          Para usar o Éden neste aparelho, digite a chave de acesso criada no servidor. Ela fica
          salva só neste aparelho. Não envie essa chave por mensagem para ninguém.
        </p>
        <input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          autoComplete="current-password"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          placeholder="oj_sk_…"
          aria-label="Chave de acesso"
          className="w-full text-sm px-3 py-2.5 rounded-lg outline-none"
          style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
        />
        {error && (
          <p className="text-xs" role="alert" style={{ color: 'var(--color-error)' }}>
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="w-full py-2.5 rounded-lg text-sm font-medium cursor-pointer disabled:opacity-50 disabled:cursor-default"
          style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' }}
        >
          {busy ? 'Conferindo…' : 'Entrar'}
        </button>
      </form>
    </div>
  );
}
