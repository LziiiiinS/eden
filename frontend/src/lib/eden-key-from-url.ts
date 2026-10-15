// Éden: quando o celular abre o link do QR code (https://…/#chave=oj_sk_…),
// guarda a chave de acesso neste aparelho e tira a chave do endereço na hora.
//
// Este arquivo é importado PRIMEIRO em main.tsx, antes do resto do app, para
// que a chave já esteja salva quando o app começar a falar com o servidor.
import { readKeyFromHash } from './eden-key';

const SETTINGS_KEY = 'openjarvis-settings';

function consumeKeyFromUrl(): void {
  if (typeof window === 'undefined') return;
  const key = readKeyFromHash(window.location.hash);
  if (!key) return;
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    const settings = raw ? JSON.parse(raw) : {};
    const atual = typeof settings.apiKey === 'string' ? settings.apiKey : '';
    // Um link (por exemplo, escrito pela IA numa resposta) não troca a chave
    // que já está salva sem a pessoa concordar.
    const trocar =
      !atual ||
      atual === key ||
      window.confirm(
        'Este link quer trocar a chave de acesso salva neste aparelho. Só aceite se o link veio do QR code do seu Éden. Trocar?',
      );
    if (trocar) {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...settings, apiKey: key }));
    }
  } catch {
    // Sem armazenamento: a tela de chave aparece e a pessoa digita.
  }
  // Tira a chave do endereço (e do histórico desta aba).
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}

consumeKeyFromUrl();
