// Éden: escolha de quem responde — Automático, Dia a dia (ChatGPT) ou Missão (Claude).
import { useAppStore } from '../../lib/store';
import { EDEN_MODES } from '../../lib/eden-ai';

interface Props {
  disabled?: boolean;
}

export function EdenModeSwitch({ disabled = false }: Props) {
  const selectedModel = useAppStore((s) => s.selectedModel);
  const setSelectedModel = useAppStore((s) => s.setSelectedModel);
  const current = EDEN_MODES.find((m) => m.id === selectedModel);

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <div
        role="radiogroup"
        aria-label="Quem responde"
        className="inline-flex rounded-full p-0.5 text-xs"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
      >
        {EDEN_MODES.map((mode) => {
          const active = selectedModel === mode.id;
          return (
            <button
              key={mode.id}
              type="button"
              role="radio"
              aria-checked={active}
              title={mode.hint}
              disabled={disabled}
              onClick={() => setSelectedModel(mode.id)}
              className="px-3 py-1.5 rounded-full transition-colors cursor-pointer disabled:cursor-default disabled:opacity-60"
              style={{
                background: active ? 'var(--color-accent-subtle)' : 'transparent',
                color: active ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                fontWeight: active ? 600 : 400,
              }}
            >
              {mode.short}
            </button>
          );
        })}
      </div>
      {/* No celular não existe "passar o mouse": a explicação fica à vista. */}
      {current && (
        <span className="text-[11px] leading-snug" style={{ color: 'var(--color-text-tertiary)' }}>
          {current.hint}
        </span>
      )}
    </div>
  );
}
