// Éden: código curto (ABCD-EFGH) para ligar um aparelho sem digitar a chave.
//
// Serve principalmente para o iPhone: o Éden aberto pelo ícone da tela de
// início não enxerga a chave que o QR code salvou no Safari. O notebook mostra
// um código que vale 5 minutos e serve uma vez só; o aparelho troca o código
// pela chave (POST /v1/eden/pareamento/usar).
import { apiFetch } from './api';

// Sem I, O, 0 e 1 (confundem). Igual ao servidor (openjarvis/eden/pareamento.py).
export const PAIRING_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const PAIRING_LENGTH = 8;

/** Deixa o que a pessoa digita no formato ABCD-EFGH, enquanto ela digita. */
export function formatPairingInput(raw: string): string {
  const limpo = raw
    .replace(/[^A-Za-z0-9]/g, '')
    .toUpperCase()
    .split('')
    .filter((c) => PAIRING_ALPHABET.includes(c))
    .join('')
    .slice(0, PAIRING_LENGTH);
  return limpo.length > 4 ? `${limpo.slice(0, 4)}-${limpo.slice(4)}` : limpo;
}

export function isCompletePairingCode(value: string): boolean {
  return formatPairingInput(value).length === PAIRING_LENGTH + 1;
}

export type PairingResult =
  | { ok: true; key: string }
  | { ok: false; reason: 'invalid' | 'too-many' | 'full' | 'offline' };

/** Troca o código pela chave de acesso do servidor. */
export async function redeemPairingCode(code: string): Promise<PairingResult> {
  let res: Response;
  try {
    res = await apiFetch('/v1/eden/pareamento/usar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ codigo: formatPairingInput(code) }),
    });
  } catch {
    return { ok: false, reason: 'offline' };
  }
  if (res.status === 429) return { ok: false, reason: 'too-many' };
  if (res.status === 400) return { ok: false, reason: 'invalid' };
  if (res.status === 409) return { ok: false, reason: 'full' };
  if (!res.ok) return { ok: false, reason: 'offline' };
  try {
    const data = await res.json();
    const key = typeof data?.chave === 'string' ? data.chave.trim() : '';
    return key ? { ok: true, key } : { ok: false, reason: 'offline' };
  } catch {
    return { ok: false, reason: 'offline' };
  }
}

export interface PairingCode {
  codigo: string;
  validadeS: number;
}

/** No aparelho que já tem a chave: pede um código novo ao servidor. */
export async function createPairingCode(): Promise<PairingCode | null> {
  try {
    const res = await apiFetch('/v1/eden/pareamento', { method: 'POST' });
    if (!res.ok) return null;
    const data = await res.json();
    if (typeof data?.codigo !== 'string' || !isCompletePairingCode(data.codigo)) return null;
    const validadeS = typeof data.validade_s === 'number' ? data.validade_s : 300;
    return { codigo: data.codigo, validadeS };
  } catch {
    return null;
  }
}

/** Apaga o código antes da hora (por exemplo, ao esconder da tela). */
export async function cancelPairingCode(): Promise<void> {
  try {
    await apiFetch('/v1/eden/pareamento', { method: 'DELETE' });
  } catch {
    // Melhor esforço: o código vence sozinho em 5 minutos.
  }
}

/** O Éden foi aberto pelo ícone da tela de início (app instalado)? */
export function isHomeScreenApp(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    if (window.matchMedia?.('(display-mode: standalone)').matches) return true;
  } catch {
    // Navegador antigo.
  }
  return (navigator as Navigator & { standalone?: boolean }).standalone === true;
}
