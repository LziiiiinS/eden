// Éden: testes da limpeza da chave de acesso.
import { describe, expect, it } from 'vitest';
import { normalizeAccessKey } from './eden-key';

const KEY = 'oj_sk_Ab-9_xYz0123456789abcdefghijklmnopqrstuv';

describe('normalizeAccessKey', () => {
  it('keeps a plain key', () => {
    expect(normalizeAccessKey(KEY)).toBe(KEY);
  });

  it('accepts the whole .env line, spaces and quotes', () => {
    expect(normalizeAccessKey(`OPENJARVIS_API_KEY=${KEY}`)).toBe(KEY);
    expect(normalizeAccessKey(`  "${KEY}"  \r\n`)).toBe(KEY);
  });

  it('drops a password the browser filled before the paste', () => {
    expect(normalizeAccessKey(`senhaSalva123${KEY}`)).toBe(KEY);
  });

  it('leaves keys in other formats untouched (only trimmed)', () => {
    expect(normalizeAccessKey('  outra-chave  ')).toBe('outra-chave');
  });
});
