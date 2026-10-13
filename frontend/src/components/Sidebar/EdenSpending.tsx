// Éden: quanto já foi gasto neste mês com cada IA, e o limite de cada uma.
import { useEffect, useState } from 'react';
import { apiFetch } from '../../lib/api';
import { useAppStore } from '../../lib/store';

interface ProviderSpending {
  label: string;
  spentUsd: number;
  limitUsd: number | null;
  blocked: boolean;
}

interface SpendingSummary {
  month: string;
  providers: Record<string, ProviderSpending>;
}

const SHORT_NAME: Record<string, string> = { openai: 'ChatGPT', anthropic: 'Claude' };
const REFRESH_MS = 60_000;

function usd(value: number): string {
  return value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function monthName(month: string): string {
  const [year, m] = month.split('-').map(Number);
  if (!year || !m) return month;
  return new Date(year, m - 1, 1).toLocaleDateString('pt-BR', { month: 'long' });
}

export function EdenSpending() {
  const [summary, setSummary] = useState<SpendingSummary | null>(null);
  const isStreaming = useAppStore((s) => s.streamState.isStreaming);

  useEffect(() => {
    if (isStreaming) return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await apiFetch('/v1/eden/gastos');
        if (!res.ok) return;
        const data = (await res.json()) as SpendingSummary;
        if (!cancelled && data?.providers) setSummary(data);
      } catch {
        // Sem conexão: mantém o último valor.
      }
    };
    void load();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isStreaming]);

  if (!summary) return null;

  return (
    <div className="px-4 pb-2 text-[11px] leading-snug" style={{ color: 'var(--color-text-secondary)' }}>
      <div className="mb-1" style={{ color: 'var(--color-text-tertiary)' }}>
        Gastos de {monthName(summary.month)}
      </div>
      {Object.entries(summary.providers).map(([id, p]) => {
        const limit = p.limitUsd ?? 0;
        const share = limit > 0 ? Math.min(1, p.spentUsd / limit) : 1;
        const color = p.blocked
          ? 'var(--color-error)'
          : share >= 0.8
            ? 'var(--color-warning)'
            : 'var(--color-accent)';
        return (
          <div key={id} className="mb-1.5">
            <div className="flex justify-between gap-2">
              <span>{SHORT_NAME[id] ?? p.label}</span>
              <span style={{ color: p.blocked ? 'var(--color-error)' : undefined }}>
                {p.blocked
                  ? `limite atingido (US$ ${usd(limit)})`
                  : `US$ ${usd(p.spentUsd)} de ${usd(limit)}`}
              </span>
            </div>
            <div
              className="h-1 rounded-full mt-0.5 overflow-hidden"
              style={{ background: 'var(--color-bg-tertiary)' }}
              role="progressbar"
              aria-label={`Gasto do ${SHORT_NAME[id] ?? p.label}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(share * 100)}
            >
              <div className="h-full" style={{ width: `${share * 100}%`, background: color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
