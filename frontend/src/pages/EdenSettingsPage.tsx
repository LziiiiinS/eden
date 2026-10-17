// Éden: configurações do piloto, em português e só com o que o Éden usa.
// As configurações completas do OpenJarvis continuam em /settings/avancado.
import { useEffect, useRef, useState } from 'react';
import { Sun, Moon, Monitor, Smartphone, KeyRound } from 'lucide-react';
import { EdenPhoneQr } from '../components/EdenPhoneQr';
import { EdenSpacesSettings } from '../components/Eden/EdenSpacesSettings';
import { EdenPushSettings } from '../components/Eden/EdenPushSettings';
import { EdenGoogleSettings } from '../components/Eden/EdenGoogleSettings';
import { EdenNotionSettings } from '../components/Eden/EdenNotionSettings';
import { EdenVozSettings } from '../components/Eden/EdenVozSettings';
import { EdenAparelhosSettings } from '../components/Eden/EdenAparelhosSettings';
import { criarAparelho } from '../lib/eden-aparelhos';
import { ErroEden } from '../lib/eden-org';
import { useAppStore, type ThemeMode } from '../lib/store';
import { apiFetch, checkHealth, fetchSpeechHealth } from '../lib/api';
import { EdenSpending } from '../components/Sidebar/EdenSpending';
import { buildPhoneLink, isPhoneReachableUrl, normalizeAccessKey } from '../lib/eden-key';
import { cancelPairingCode, createPairingCode, type PairingCode } from '../lib/eden-pareamento';

const PHONE_URL_KEY = 'eden-phone-url';
// O QR code leva a chave de acesso: some sozinho depois de 5 minutos.
const QR_VISIBLE_MS = 5 * 60_000;

function initialPhoneUrl(): string {
  if (typeof window !== 'undefined' && isPhoneReachableUrl(window.location.origin)) {
    return window.location.origin;
  }
  try {
    return localStorage.getItem(PHONE_URL_KEY) ?? '';
  } catch {
    return '';
  }
}

// Éden: código curto (ABCD-EFGH) para o aparelho que não recebe a chave pelo
// QR code — o iPhone aberto pelo ícone da tela de início guarda tudo separado
// do Safari. Vale 5 minutos e serve uma vez só.
function PairingCodeBlock() {
  const [code, setCode] = useState<PairingCode | null>(null);
  const [expiresAt, setExpiresAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ativoRef = useRef(false);
  ativoRef.current = code !== null;

  // Saiu da tela com o código à vista: o código deixa de valer.
  useEffect(
    () => () => {
      if (ativoRef.current) void cancelPairingCode();
    },
    [],
  );

  useEffect(() => {
    if (!code) return;
    const t = setInterval(() => {
      const agora = Date.now();
      setNow(agora);
      if (agora >= expiresAt) setCode(null);
    }, 1000);
    return () => clearInterval(t);
  }, [code, expiresAt]);

  const show = async () => {
    setBusy(true);
    setError('');
    const novo = await createPairingCode();
    setBusy(false);
    if (!novo) {
      setError('Não consegui criar o código agora. Tente de novo.');
      return;
    }
    setCode(novo);
    setExpiresAt(Date.now() + novo.validadeS * 1000);
    setNow(Date.now());
  };

  const hide = () => {
    setCode(null);
    void cancelPairingCode();
  };

  const restante = Math.max(0, Math.ceil((expiresAt - now) / 1000));
  const minutos = Math.floor(restante / 60);
  const segundos = String(restante % 60).padStart(2, '0');

  return (
    <div className="pt-4 mt-3 flex flex-col items-start gap-3" style={{ borderTop: '1px solid var(--color-border)' }}>
      <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
        <strong>iPhone pelo ícone da tela de início:</strong> o ícone não enxerga a chave que o QR
        code salvou no Safari e pede a chave de novo. Nesse caso, mostre um código aqui e, no iPhone,
        toque em "Tenho um código do notebook" e digite.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={code ? hide : show}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs cursor-pointer disabled:opacity-40 disabled:cursor-default"
        style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text)', border: '1px solid var(--color-border)' }}
      >
        <KeyRound size={14} />
        {code ? 'Esconder código' : busy ? 'Criando…' : 'Mostrar código'}
      </button>
      {error && (
        <p className="text-xs" role="alert" style={{ color: 'var(--color-error)' }}>
          {error}
        </p>
      )}
      {code && (
        <div className="flex flex-col items-center gap-1 self-center">
          <p
            className="font-mono text-3xl font-semibold tracking-widest select-all"
            style={{ color: 'var(--color-text)' }}
            aria-label="Código para digitar no aparelho"
          >
            {code.codigo}
          </p>
          <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            Vale por mais {minutos}:{segundos} e serve uma vez só.
          </p>
          <p className="text-xs text-center max-w-xs" style={{ color: 'var(--color-warning)' }}>
            Este código dá acesso ao seu Éden. Digite só nos seus aparelhos, não mande para ninguém.
          </p>
        </div>
      )}
    </div>
  );
}

// Éden: QR code para conectar um celular sem digitar a chave de acesso.
function ConnectPhone({ apiKey }: { apiKey: string }) {
  const [phoneUrl, setPhoneUrl] = useState(initialPhoneUrl);
  const [showQr, setShowQr] = useState(false);
  // Parte 5: o QR leva uma chave só para o celular novo (não a principal).
  const [qrKey, setQrKey] = useState<string | null>(null);
  const [qrErro, setQrErro] = useState<string | null>(null);
  const [automatico, setAutomatico] = useState(false);
  const reachable = isPhoneReachableUrl(phoneUrl);
  const phoneUrlRef = useRef(phoneUrl);
  phoneUrlRef.current = phoneUrl;

  // Éden: o iniciar-eden descobre o endereço do Tailscale deste computador e
  // o servidor informa aqui. Se o campo estiver vazio ou errado, usa esse.
  useEffect(() => {
    let cancelado = false;
    apiFetch('/v1/eden/info')
      .then((res) => (res.ok ? res.json() : null))
      .then((info) => {
        const endereco = typeof info?.endereco_celular === 'string' ? info.endereco_celular : '';
        if (cancelado || !isPhoneReachableUrl(endereco)) return;
        if (isPhoneReachableUrl(phoneUrlRef.current)) return;
        setPhoneUrl(endereco);
        setAutomatico(true);
        try {
          localStorage.setItem(PHONE_URL_KEY, endereco);
        } catch {
          // Melhor esforço.
        }
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, []);

  useEffect(() => {
    if (!showQr) return;
    const t = setTimeout(() => setShowQr(false), QR_VISIBLE_MS);
    return () => clearTimeout(t);
  }, [showQr]);

  const changeUrl = (value: string) => {
    setPhoneUrl(value);
    setShowQr(false);
    setAutomatico(false);
    try {
      localStorage.setItem(PHONE_URL_KEY, value.trim());
    } catch {
      // Melhor esforço.
    }
  };

  return (
    <>
      <p className="text-xs leading-relaxed mb-1" style={{ color: 'var(--color-text-secondary)' }}>
        Aponte a câmera do celular para o QR code: ele abre o Éden já com a chave de acesso. O
        celular precisa estar na sua rede privada (Tailscale ligado).
      </p>
      <Row
        label="Endereço do Éden no celular"
        description="O endereço com cadeado do Tailscale, por exemplo https://eden-notebook.tailxxxx.ts.net (aparece no comando tailscale serve status)."
      >
        <input
          type="url"
          value={phoneUrl}
          onChange={(e) => changeUrl(e.target.value)}
          placeholder="https://…ts.net"
          aria-label="Endereço do Éden no celular"
          autoCapitalize="off"
          spellCheck={false}
          className="text-sm px-3 py-1.5 rounded-lg outline-none w-64"
          style={inputStyle}
        />
      </Row>
      {automatico && reachable && (
        <p className="text-xs mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
          Endereço encontrado sozinho (Tailscale deste computador).
        </p>
      )}
      {!reachable && phoneUrl.trim() !== '' && (
        <p className="text-xs mt-2" role="alert" style={{ color: 'var(--color-warning)' }}>
          Use o endereço com cadeado do Tailscale, como https://eden-notebook.tailxxxx.ts.net
          (sem nada depois do .ts.net). Por segurança, a chave só vai para esse tipo de endereço.
        </p>
      )}
      <div className="pt-3 flex flex-col items-start gap-3">
        <button
          type="button"
          disabled={!reachable}
          onClick={async () => {
            if (showQr) {
              setShowQr(false);
              return;
            }
            setQrErro(null);
            try {
              setQrKey((await criarAparelho('Celular (QR code)')).chave);
            } catch (e) {
              if (e instanceof ErroEden && e.status === 404) {
                setQrKey(apiKey); // servidor antigo, sem chave por aparelho
              } else {
                setQrErro((e as Error).message);
                return;
              }
            }
            setShowQr(true);
          }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs cursor-pointer disabled:opacity-40 disabled:cursor-default"
          style={{ background: 'var(--color-accent)', color: 'var(--color-on-accent, white)' }}
        >
          <Smartphone size={14} />
          {showQr ? 'Esconder QR code' : 'Mostrar QR code'}
        </button>
        {qrErro && (
          <p className="text-xs" role="alert" style={{ color: 'var(--color-error)' }}>
            {qrErro}
          </p>
        )}
        {showQr && reachable && qrKey && (
          <div className="flex flex-col items-center gap-2 self-center">
            <EdenPhoneQr text={buildPhoneLink(phoneUrl, qrKey)} />
            <p className="text-xs text-center max-w-xs" style={{ color: 'var(--color-warning)' }}>
              Este QR code leva uma chave de acesso só para o celular novo (aparece em Aparelhos
              ligados, onde dá para desligar). Mostre só para os seus aparelhos, não fotografe nem
              mande para ninguém. Ele some sozinho em 5 minutos.
            </p>
          </div>
        )}
      </div>
      <PairingCodeBlock />
    </>
  );
}

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
    const key = normalizeAccessKey(newKey);
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

        {settings.apiKey && (
          <Section title="Conectar um celular">
            <ConnectPhone apiKey={settings.apiKey} />
          </Section>
        )}

        {settings.apiKey && (
          <Section title="Aparelhos ligados">
            <EdenAparelhosSettings />
          </Section>
        )}

        {settings.apiKey && (
          <Section title="Google Agenda">
            <EdenGoogleSettings />
          </Section>
        )}

        {settings.apiKey && (
          <Section title="Notion">
            <EdenNotionSettings />
          </Section>
        )}

        {settings.apiKey && (
          <Section title="Espaços">
            <EdenSpacesSettings />
          </Section>
        )}

        {settings.apiKey && (
          <Section title="Avisos de lembrete neste aparelho">
            <EdenPushSettings />
          </Section>
        )}

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
          <EdenVozSettings />
        </Section>

        <Section title="Sobre">
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
            O Éden é baseado no OpenJarvis (Universidade Stanford, licença Apache 2.0). As conversas
            ficam no seu servidor e são sincronizadas entre os seus aparelhos.
          </p>
          <p className="text-xs mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
            Por segurança, o servidor do Éden liga só o que o Éden usa: conversa, sincronização,
            microfone e gastos. As outras funções do OpenJarvis ficam desligadas.
          </p>
        </Section>
      </div>
    </div>
  );
}
