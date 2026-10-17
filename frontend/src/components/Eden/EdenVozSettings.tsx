// Éden (Parte 4): respostas em voz nas Configurações (voz da OpenAI pelo
// servidor do Éden, com limite de gastos). Vale para este aparelho.
import { useEffect, useState } from 'react';
import { useAppStore } from '../../lib/store';
import { VOZES, definirVoz, desbloquearAudio, useEdenVozStore, vozEscolhida } from '../../lib/eden-voz';

function Linha({ label, description, children }: { label: string; description?: string; children?: React.ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 py-3"
      style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm" style={{ color: 'var(--color-text)' }}>{label}</div>
        {description && (
          <div className="text-xs mt-0.5 break-words" style={{ color: 'var(--color-text-tertiary)' }}>
            {description}
          </div>
        )}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  );
}

function Chave({ on, onChange, label, disabled = false }: { on: boolean; onChange: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      disabled={disabled}
      className="relative w-11 h-6 rounded-full transition-colors cursor-pointer disabled:cursor-default disabled:opacity-40"
      style={{ background: on ? 'var(--color-accent)' : 'var(--color-bg-tertiary)' }}
    >
      <span
        className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
        style={{ transform: on ? 'translateX(20px)' : 'translateX(0)', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }}
      />
    </button>
  );
}

export function EdenVozSettings() {
  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const disponivel = useEdenVozStore((s) => s.available);
  const ensureHealth = useEdenVozStore((s) => s.ensureHealth);
  const speak = useEdenVozStore((s) => s.speak);
  const estado = useEdenVozStore((s) => s.state);
  const erro = useEdenVozStore((s) => s.error);
  const [voz, setVoz] = useState(vozEscolhida);

  useEffect(() => {
    void ensureHealth();
  }, [ensureHealth]);

  return (
    <>
      <Linha
        label="Ouvir as respostas"
        description="Mostra o alto-falante embaixo de cada resposta. Voz da OpenAI: cerca de US$ 0,02 a cada 1.000 caracteres falados, dentro do limite do mês da OpenAI."
      >
        <Chave
          on={settings.voiceOutputEnabled}
          onChange={() =>
            updateSettings({
              voiceOutputEnabled: !settings.voiceOutputEnabled,
              ...(settings.voiceOutputEnabled ? { voiceAutoplay: false } : {}),
            })
          }
          label="Ouvir as respostas"
        />
      </Linha>
      <Linha
        label="Modo conversa (tipo Jarvis)"
        description="O Éden fala cada resposta sozinho, responde mais curto e, ao usar o microfone, já envia o que você falou. Também liga e desliga pelo botão Voz no campo de mensagem."
      >
        <Chave
          on={settings.voiceOutputEnabled && settings.voiceAutoplay}
          onChange={() =>
            updateSettings(
              settings.voiceAutoplay && settings.voiceOutputEnabled
                ? { voiceAutoplay: false }
                : { voiceAutoplay: true, voiceOutputEnabled: true },
            )
          }
          label="Modo conversa"
        />
      </Linha>
      <Linha label="Voz" description="Vale para este aparelho.">
        <div className="flex items-center gap-2">
          <select
            value={voz}
            onChange={(e) => {
              setVoz(e.target.value);
              definirVoz(e.target.value);
            }}
            aria-label="Voz"
            className="px-2 py-1.5 rounded-lg text-xs outline-none"
            style={{ background: 'var(--color-input-bg)', border: '1px solid var(--color-input-border)', color: 'var(--color-text)' }}
          >
            {VOZES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.nome}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              desbloquearAudio();
              void speak('teste-voz', 'Oi, Levi! Esta é a minha voz. Como posso ajudar?');
            }}
            disabled={disponivel !== true || estado !== 'idle'}
            className="px-2.5 py-1.5 rounded-lg text-xs cursor-pointer disabled:cursor-default disabled:opacity-50"
            style={{ border: '1px solid var(--color-border)', color: 'var(--color-text-secondary)' }}
          >
            {estado === 'idle' ? 'Ouvir' : 'Falando…'}
          </button>
        </div>
      </Linha>
      <Linha label="Voz no servidor">
        <span className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background:
                disponivel === null ? 'var(--color-text-tertiary)' : disponivel ? 'var(--color-success)' : 'var(--color-error)',
            }}
          />
          {disponivel === null ? 'Conferindo…' : disponivel ? 'Funcionando (OpenAI)' : 'Falta a chave da OpenAI no servidor'}
        </span>
      </Linha>
      {erro && (
        <p role="alert" className="text-xs pt-2" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
    </>
  );
}
