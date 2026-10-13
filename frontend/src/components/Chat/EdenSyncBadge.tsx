// Éden: estado de envio de uma mensagem do usuário ao servidor.
// - "Salvando…" enquanto o servidor ainda não confirmou (normal, dura segundos).
// - "Não sincronizada" quando está sem conexão ou o servidor recusou: a
//   mensagem está só neste aparelho.
import { Clock, Loader2 } from 'lucide-react';
import { useAppStore } from '../../lib/store';
import { useSyncStore } from '../../lib/eden-sync';
import { isMessagePending } from '../../lib/eden-sync-merge';

export function EdenSyncBadge({ messageId }: { messageId: string }) {
  const activeId = useAppStore((s) => s.activeId);
  const confirmed = useSyncStore((s) => (activeId ? s.confirmedIds[activeId] : undefined));
  const status = useSyncStore((s) => s.status);

  if (!activeId || !isMessagePending(messageId, confirmed)) return null;

  const stuck = status === 'offline' || status === 'error';
  return (
    <div
      className="flex justify-end mt-1 text-[11px] items-center gap-1"
      style={{ color: stuck ? 'var(--color-warning)' : 'var(--color-text-tertiary)' }}
      role={stuck ? 'status' : undefined}
    >
      {stuck ? <Clock size={12} aria-hidden="true" /> : <Loader2 size={12} className="animate-spin" aria-hidden="true" />}
      <span>{stuck ? 'Não sincronizada · salva só neste aparelho' : 'Salvando…'}</span>
    </div>
  );
}
