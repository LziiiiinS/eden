// Éden: limpa o que a pessoa colou no campo da chave de acesso e monta/lê o
// link do QR code que leva a chave para o celular.
//
// Aceita a chave sozinha, a linha inteira do .env ("OPENJARVIS_API_KEY=oj_sk_…"),
// com espaços ou aspas, e também o caso em que o navegador já tinha preenchido
// uma senha salva no campo e a chave foi colada junto: fica só a última chave
// no formato oj_sk_….
const KEY_PATTERN = /oj_sk_[A-Za-z0-9_-]+/g;

/** Nome do parâmetro no fim do link do QR code: https://…/#chave=oj_sk_… */
export const KEY_HASH_PARAM = 'chave';

export function normalizeAccessKey(raw: string): string {
  const matches = raw.match(KEY_PATTERN);
  if (matches && matches.length > 0) return matches[matches.length - 1];
  return raw
    .trim()
    .replace(/^OPENJARVIS_API_KEY\s*=\s*/, '')
    .replace(/^["']|["']$/g, '')
    .trim();
}

/**
 * Link que o QR code mostra. A chave vai depois do "#": essa parte do
 * endereço fica só no aparelho, o navegador não envia ao servidor.
 */
export function buildPhoneLink(baseUrl: string, key: string): string {
  const base = baseUrl.trim().replace(/[/#?]+$/, '');
  return `${base}/#${KEY_HASH_PARAM}=${encodeURIComponent(key)}`;
}

/** Lê a chave do fim do endereço ("#chave=…"); devolve null se não houver. */
export function readKeyFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const raw = params.get(KEY_HASH_PARAM);
  if (!raw) return null;
  const key = normalizeAccessKey(raw);
  return key || null;
}

/** O endereço serve para o celular abrir? (precisa de https, fora do localhost) */
export function isPhoneReachableUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && u.hostname !== 'localhost' && u.hostname !== '127.0.0.1';
  } catch {
    return false;
  }
}
