// Éden: configurações do piloto, em português e só com o que o Éden usa.
// As configurações completas do OpenJarvis continuam em /settings/avancado.
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useAppStore, type ThemeMode } from '../lib/store';
import { apiFetch, checkHealth, fetchSpeechHealth } from '../lib/api';
import { EdenSpending } from '../components/Sidebar/EdenSpending';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      className="rounded-xl p-5"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)' }}
    >
      <h2 className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text)' }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, description, children }: { label: string; description?: string; children?: React.ReactNode }) {
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

function Toggle({ on, onChange, label }: { on: boolean; onChange: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      className="relative w-11 h-6 rounded-full transition-colors cursor-pointer"
      style={{ background: on ? 'var(--color-accent)' : 'var(--color-bg-tertiary)' }}
    >
      <span
        className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform bg-white"
        style={{ transform: on ? 'translateX(20px)' : 'translateX(0)', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' }}
      />
    </button>
  );
}

function Status({ ok, text }: { ok: boolean | null; text: string }) {
  return (
    <span className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
      <span
        className="w-2 h-2 rounded-full"
        style={{ background: ok === null ? 'var(--color-text-tertiary)' : ok ? 'var(--color-success)' : 'var(--color-error)' }}
      />
      {text}
    </span>
  );
}

const THEMES: Array<{ value: ThemeMode; label: string; icon: typeof Sun }> = [
  { value: 'light', label: 'Claro', icon: Sun },
  { value: 'dark', label: 'Escuro', icon: Moon },
  { value: 'system', label: 'Automático', icon: Monitor },
];

const inputStyle = {
  background: 'var(--color-bg-secondary)',
  color: 'var(--color-text)',
  border: '1px solid var(--color-border)',
};

export function EdenSettingsPage() {
  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);
  const [online, setOnline] = useState<boolean | null>(null);
  const [keyOk, setKeyOk] = useState<boolean | null>(null);
  const [speechOk, setSpeechOk] = useState<boolean | null>(null);
  const [models, setModels] = useState<{ dia?: string; missao?: string }>({});
  const [newKey, setNewKey] = useState('');

  useEffect(() => {
    checkHealth().then(setOnline).catch(() => setOnline(false));
    fetchSpeechHealth()
      .then((h) => setSpeechOk(h.available))
      .catch(() => setSpeechOk(false));
    apiFetch('/v1/eden/gastos')
      .then(async (res) => {
        setKeyOk(res.status !== 401);
        if (res.ok) setModels((await res.json()).models ?? {});
      })
      .catch(() => setKeyOk(null));
  }, [settings.apiKey, settings.apiUrl]);

  const saveKey = () => {
    const key = newKey.trim();
    if (!key) return;
    updateSettings({ apiKey: key });
    setNewKey('');
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 py-6 flex flex-col gap-4">
        <h1 className="text-lg font-semibold pl-10 md:pl-0" style={{ color: 'var(--color-text)' }}>
          Configurações
        </h1>

        <Section title="Aparência">
          <Row label="Tema">
            <div className="flex gap-1" role="radiogroup" aria-label="Tema">
              {THEMES.map((t) => {
                const active = settings.theme === t.value;
                return (
                  <button
                    key={t.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => updateSettings({ theme: t.value })}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs cursor-pointer"
                    style={{
                      background: active ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
                      color: active ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                      border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-border)'}`,
                    }}
                  >
                    <t.icon size={13} />
                    {t.label}
                  </button>
                );
              })}
            </div>
          </Row>
          <Row label="Tamanho da letra">
            <select
              value={settings.fontSize}
              onChange={(e) => updateSettings({ fontSize: e.target.value as 'small' | 'default' | 'large' })}
              aria-label="Tamanho da letra"
              className="text-sm px-3 py-1.5 rounded-lg outline-none cursor-pointer"
              style={inputStyle}
            >
              <option value="small">Pequena</option>
              <option value="default">Normal</option>
              <option value="large">Grande</option>
            </select>
          </Row>
        </Section>

        <Section title="Servidor">
          <Row label="Situação">
            <Status
              ok={online === null ? null : online && keyOk !== false}
              text={
                online === null
                  ? 'Conferindo…'
                  : !online
                    ? 'Fora do ar ou sem internet'
                    : keyOk === false
                      ? 'Chave de acesso inválida'
                      : 'Conectado'
              }
            />
          </Row>
          <Row
            label="Chave de acesso"
            description={settings.apiKey ? 'Salva neste aparelho. Para trocar, digite a nova.' : 'Ainda não informada.'}
          >
            <div className="flex gap-2">
              <input
                type="password"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
                placeholder="Nova chave"
                aria-label="Nova chave de acesso"
                className="text-sm px-3 py-1.5 rounded-lg outline-none w-40"
                style={inputStyle}
              />
              <button
                type="button"
                onClick={saveKey}
                disabled={!newKey.trim()}
                className="px-3 py-1.5 rounded-lg text-xs cursor-pointer disabled:opacity-40 disabled:cursor-default"
                style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' }}
              >
                Salvar
              </button>
            </div>
          </Row>
          <Row
            label="Endereço do servidor"
            description="Deixe em branco quando o Éden abre pelo próprio endereço do servidor (o normal)."
          >
            <input
              type="url"
              value={settings.apiUrl}
              onChange={(e) => updateSettings({ apiUrl: e.target.value })}
              placeholder="https://…"
              aria-label="Endereço do servidor"
              className="text-sm px-3 py-1.5 rounded-lg outline-none w-56"
              style={inputStyle}
            />
          </Row>
        </Section>

        <Section title="IAs e gastos do mês">
          <Row label="Dia a dia" description="Respostas rápidas, dúvidas, anotações">
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              ChatGPT {models.dia ? `(${models.dia})` : ''}
            </span>
          </Row>
          <Row label="Missão" description="Documentos, propostas, projetos, mensagens para clientes">
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              Claude {models.missao ? `(${models.missao})` : ''}
            </span>
          </Row>
          <div className="pt-3 -mx-4">
            <EdenSpending />
          </div>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
            Os modelos e os limites são definidos no servidor, na seção <code>[eden]</code> do
            arquivo <code>config.toml</code>. Quando o limite de uma IA acaba, o Éden para de usá-la
            até o mês virar.
          </p>
        </Section>

        <Section title="Voz">
          <Row label="Microfone (ditado)" description="Grava, transcreve e coloca o texto na caixa para você revisar antes de enviar.">
            <Toggle
              on={settings.speechEnabled}
              onChange={() => updateSettings({ speechEnabled: !settings.speechEnabled })}
              label="Microfone"
            />
          </Row>
          <Row label="Transcrição no servidor">
            <Status
              ok={speechOk}
              text={speechOk === null ? 'Conferindo…' : speechOk ? 'Funcionando' : 'Não configurada no servidor'}
            />
          </Row>
        </Section>

        <Section title="Sobre">
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
            O Éden é baseado no OpenJarvis (Universidade Stanford, licença Apache 2.0). As conversas
            ficam no seu servidor e são sincronizadas entre os seus aparelhos.
          </p>
          <p className="text-xs mt-2">
            <Link to="/settings/avancado" style={{ color: 'var(--color-accent)' }}>
              Configurações avançadas do OpenJarvis (em inglês)
            </Link>
          </p>
        </Section>
      </div>
    </div>
  );
}
