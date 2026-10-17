// Éden: testes dos textos da lista de aparelhos.
import { describe, expect, it } from 'vitest';
import { quandoUsado } from './eden-aparelhos';

describe('aparelhos', () => {
  it('formats the last use', () => {
    const agora = new Date(2026, 9, 17, 20, 0);
    expect(quandoUsado(null, agora)).toBe('nunca usado');
    expect(quandoUsado(new Date(2026, 9, 17, 14, 5).getTime(), agora)).toBe('hoje 14:05');
    expect(quandoUsado(new Date(2026, 9, 16, 9, 10).getTime(), agora)).toBe('ontem 09:10');
    expect(quandoUsado(new Date(2026, 9, 12, 9, 10).getTime(), agora)).toBe('12/10');
  });
});
