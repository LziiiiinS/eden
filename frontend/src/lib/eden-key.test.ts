// Éden: testes da limpeza da chave de acesso.
import { describe, expect, it } from 'vitest';
import { buildPhoneLink, isPhoneReachableUrl, normalizeAccessKey, readKeyFromHash } from './eden-key';
import { qrcodegen } from './vendor/qrcodegen';

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

describe('phone link (QR code)', () => {
  it('puts the key after "#" and reads it back', () => {
    const link = buildPhoneLink('https://eden-notebook.tail1234.ts.net/', KEY);
    expect(link).toBe(`https://eden-notebook.tail1234.ts.net/#chave=${KEY}`);
    expect(readKeyFromHash(new URL(link).hash)).toBe(KEY);
  });

  it('ignores addresses without a key', () => {
    expect(readKeyFromHash('')).toBeNull();
    expect(readKeyFromHash('#outra=coisa')).toBeNull();
  });

  it('accepts only the Tailscale https address for the phone', () => {
    expect(isPhoneReachableUrl('https://eden-notebook.tail1234.ts.net')).toBe(true);
    expect(isPhoneReachableUrl('https://eden-notebook.tail1234.ts.net/')).toBe(true);
    expect(isPhoneReachableUrl('http://eden-notebook.tail1234.ts.net')).toBe(false);
    expect(isPhoneReachableUrl('https://localhost:8000')).toBe(false);
    expect(isPhoneReachableUrl('http://localhost:8000')).toBe(false);
    expect(isPhoneReachableUrl('não é endereço')).toBe(false);
  });

  it('refuses disguised addresses that would leak the key', () => {
    expect(isPhoneReachableUrl('https://eden.tail1234.ts.net@evil.example')).toBe(false);
    expect(isPhoneReachableUrl('https://user:pw@eden.tail1234.ts.net')).toBe(false);
    expect(isPhoneReachableUrl('https://eden.tail1234.ts.net.evil.example')).toBe(false);
    expect(isPhoneReachableUrl('https://evil.example/?x=.ts.net')).toBe(false);
    expect(isPhoneReachableUrl('https://eden.tail1234.ts.net:4443')).toBe(false);
    expect(isPhoneReachableUrl('https://eden.tail1234.ts.net:8448')).toBe(false);
    // Éden de outra pessoa no mesmo servidor (nova-pessoa.sh).
    expect(isPhoneReachableUrl('https://srv.tail1234.ts.net:8443')).toBe(true);
    expect(buildPhoneLink('https://srv.tail1234.ts.net:8443/', KEY)).toBe(`https://srv.tail1234.ts.net:8443/#chave=${KEY}`);
    expect(isPhoneReachableUrl('https://eden.tail1234.ts.net/caminho')).toBe(false);
  });

  it('builds the link from the origin only', () => {
    expect(buildPhoneLink('https://eden.tail1234.ts.net/', KEY)).toBe(
      `https://eden.tail1234.ts.net/#chave=${KEY}`,
    );
  });
});

describe('QR code', () => {
  it('encodes the phone link into a square grid', () => {
    const link = buildPhoneLink('https://eden-notebook.tail1234.ts.net', KEY);
    const qr = qrcodegen.QrCode.encodeText(link, qrcodegen.QrCode.Ecc.MEDIUM);
    expect(qr.size).toBeGreaterThan(20);
    expect(qr.size % 4).toBe(1);
  });
});

describe('chave de aparelho', () => {
  it('keeps a device key (oj_ap_)', () => {
    const ap = 'oj_ap_Zx-9_' + 'a'.repeat(40);
    expect(normalizeAccessKey(`  ${ap} `)).toBe(ap);
    expect(readKeyFromHash(`#chave=${ap}`)).toBe(ap);
  });
});
