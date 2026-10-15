// Éden: testes do código curto para ligar um aparelho.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  PAIRING_ALPHABET,
  formatPairingInput,
  isCompletePairingCode,
  redeemPairingCode,
} from './eden-pareamento';

describe('formatPairingInput', () => {
  it('formats as the person types', () => {
    expect(formatPairingInput('k')).toBe('K');
    expect(formatPairingInput('k7qm')).toBe('K7QM');
    expect(formatPairingInput('k7qm2')).toBe('K7QM-2');
    expect(formatPairingInput('k7qm 2xra')).toBe('K7QM-2XRA');
    expect(formatPairingInput('K7QM-2XRA-EXTRA')).toBe('K7QM-2XRA');
  });

  it('drops symbols the code never has', () => {
    expect(formatPairingInput('O0I1')).toBe('');
    expect(formatPairingInput('ß')).toBe('');
    expect(formatPairingInput('K7QM\u200b2XRA')).toBe('K7QM-2XRA');
  });

  it('knows a complete code', () => {
    expect(isCompletePairingCode('K7QM-2XRA')).toBe(true);
    expect(isCompletePairingCode('K7QM-2XR')).toBe(false);
  });

  it('uses the same alphabet as the server', () => {
    expect(PAIRING_ALPHABET).toHaveLength(32);
    for (const c of 'IO01') expect(PAIRING_ALPHABET).not.toContain(c);
  });
});

describe('redeemPairingCode', () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    globalThis.fetch = fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends JSON and returns the key', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ chave: 'oj_sk_abc' }), { status: 200 }),
    );
    await expect(redeemPairingCode('k7qm 2xra')).resolves.toEqual({ ok: true, key: 'oj_sk_abc' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('/v1/eden/pareamento/usar');
    expect(init?.method).toBe('POST');
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(JSON.parse(String(init?.body))).toEqual({ codigo: 'K7QM-2XRA' });
  });

  it('tells wrong code, too many tries and no connection apart', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 400 }));
    await expect(redeemPairingCode('K7QM-2XRA')).resolves.toEqual({ ok: false, reason: 'invalid' });
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 429 }));
    await expect(redeemPairingCode('K7QM-2XRA')).resolves.toEqual({ ok: false, reason: 'too-many' });
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await expect(redeemPairingCode('K7QM-2XRA')).resolves.toEqual({ ok: false, reason: 'offline' });
    fetchMock.mockResolvedValueOnce(new Response('{"chave": ""}', { status: 200 }));
    await expect(redeemPairingCode('K7QM-2XRA')).resolves.toEqual({ ok: false, reason: 'offline' });
  });
});
