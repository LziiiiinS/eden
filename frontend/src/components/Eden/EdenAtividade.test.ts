import { describe, expect, it } from 'vitest';
import { nomeDaAtividade } from './EdenAtividade';

describe('atividade recente', () => {
  it('mostra o nome em português', () => {
    expect(nomeDaAtividade('conta.pagar')).toBe('marcou conta como paga');
    expect(nomeDaAtividade('criou evento')).toBe('criou evento');
    expect(nomeDaAtividade('algo.novo')).toBe('algo novo');
  });
});
