// Éden: situação da sincronização das conversas, no menu lateral.
import { useSyncStore } from '../../lib/eden-sync';

function hhmm(ts: number): string {
  return new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function EdenSyncStatus() {
  const status = useSyncStore((s) => s.status);
  const lastSyncedAt = useSyncStore((s) => s.lastSyncedAt);
  const errorMessage = useSyncStore((s) => s.errorMessage);

  let color = 'var(--color-text-tertiary)';
  let text = 'Conectando ao servidor…';
  if (status === 'synced' && lastSyncedAt) {
    color = 'var(--color-success)';
    text = `Sincronizado às ${hhmm(lastSyncedAt)}`;
  } else if (status === 'syncing') {
    text = 'Sincronizando…';
  } else if (status === 'offline') {
    color = 'var(--color-warning)';
    text = 'Sem conexão. O que você escrever fica neste aparelho até voltar.';
  } else if (status === 'error') {
    color = 'var(--color-error)';
    text = `Não sincronizado. ${errorMessage ?? ''}`.trim();
  }

  return (
    <div
      className="px-4 py-2 flex items-start gap-2 text-[11px] leading-snug"
      style={{ color: 'var(--color-text-secondary)' }}
      role="status"
      aria-live="polite"
    >
      <span
        aria-hidden="true"
        className="w-2 h-2 rounded-full shrink-0 mt-[3px]"
        style={{ background: color }}
      />
      <span>{text}</span>
    </div>
  );
}
