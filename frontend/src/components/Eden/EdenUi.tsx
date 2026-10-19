// Éden: peças de tela compartilhadas pelas páginas da organização pessoal
// (Hoje, Tarefas, Notas, Memória). Mesmo visual das Configurações do Éden:
// o núcleo pequeno no título, caixas de vidro sobre o fundo 3D e a página
// entrando vinda do fundo.
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { EdenNucleoMini } from './EdenNucleo';

export const inputStyle = {
  background: 'var(--color-bg-secondary)',
  color: 'var(--color-text)',
  border: '1px solid var(--color-border)',
};

export function EdenPage({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="eden-surgir max-w-2xl mx-auto px-4 py-6 flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2 pl-10 md:pl-0">
          <div className="flex items-center gap-2 min-w-0">
            <EdenNucleoMini />
            <h1 className="eden-titulo" style={{ color: 'var(--color-text)' }}>
              {title}
            </h1>
          </div>
          {actions}
        </div>
        {children}
      </div>
    </div>
  );
}

export function EdenSection({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="eden-vidro rounded-2xl p-4 md:p-5">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text)' }}>
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function PrimaryButton({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium cursor-pointer disabled:opacity-50 disabled:cursor-default ${className}`}
      style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)', minHeight: 40 }}
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-sm cursor-pointer disabled:opacity-50 disabled:cursor-default ${className}`}
      style={{
        background: 'var(--color-bg-secondary)',
        color: 'var(--color-text-secondary)',
        border: '1px solid var(--color-border)',
        minHeight: 40,
      }}
    >
      {children}
    </button>
  );
}

export function IconButton({ children, label, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className="inline-flex items-center justify-center rounded-lg cursor-pointer disabled:opacity-50"
      style={{ color: 'var(--color-text-tertiary)', minWidth: 36, minHeight: 36 }}
    >
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="text-sm py-2" style={{ color: 'var(--color-text-tertiary)' }}>
      {children}
    </p>
  );
}

export function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="text-xs mt-2" role="alert" style={{ color: 'var(--color-error)' }}>
      {message}
    </p>
  );
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'warning' | 'success' }) {
  const colors = {
    neutral: ['var(--color-bg-tertiary)', 'var(--color-text-tertiary)'],
    accent: ['var(--color-accent-subtle)', 'var(--color-accent)'],
    warning: ['color-mix(in srgb, var(--color-warning) 15%, transparent)', 'var(--color-warning)'],
    success: ['color-mix(in srgb, var(--color-success) 15%, transparent)', 'var(--color-success)'],
  }[tone];
  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] whitespace-nowrap"
      style={{ background: colors[0], color: colors[1] }}
    >
      {children}
    </span>
  );
}

/** Aviso do piloto: só dados de teste por enquanto. */
export function PilotNotice() {
  return (
    <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
      Piloto: use dados de teste. Não guarde senhas, documentos nem dados reais de clientes até
      conferirmos as regras do trabalho.
    </p>
  );
}
