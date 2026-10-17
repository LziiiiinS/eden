// Éden: mostra embaixo de cada resposta qual IA respondeu e por quê.
import type { MessageTelemetry } from '../../types';
import { REASON_LABEL, providerName } from '../../lib/eden-ai';

export function EdenAiLabel({ telemetry }: { telemetry?: MessageTelemetry }) {
  if (!telemetry?.eden_provider) return null;
  const name = providerName(telemetry.eden_provider);
  const pesquisa = telemetry.eden_reason === 'pesquisa';
  const mission = telemetry.eden_mode === 'missao' && !pesquisa;
  const reason = telemetry.eden_reason ? REASON_LABEL[telemetry.eden_reason] : undefined;
  const detail = [telemetry.model_id, reason].filter(Boolean).join(' · ');

  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full"
      style={{
        background: mission ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
        color: mission ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
      }}
      title={detail}
      aria-label={`Respondido pelo ${name}${mission ? ', modo missão' : ''}${reason ? `: ${reason}` : ''}`}
    >
      {name}
      {mission ? ' · missão' : ''}
      {pesquisa ? ' · pesquisa na internet' : ''}
    </span>
  );
}
