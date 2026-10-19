import { describe, expect, it } from 'vitest';
import { estadoNucleo, VISUAL } from './eden-nucleo';

describe('estadoNucleo', () => {
  it('mostra o que o Éden está fazendo', () => {
    expect(estadoNucleo({ ouvindo: false, voz: 'idle', respondendo: false })).toBe('repouso');
    expect(estadoNucleo({ ouvindo: true, voz: 'speaking', respondendo: true })).toBe('ouvindo');
    expect(estadoNucleo({ ouvindo: false, voz: 'speaking', respondendo: true })).toBe('falando');
    expect(estadoNucleo({ ouvindo: false, voz: 'loading', respondendo: false })).toBe('pensando');
    expect(estadoNucleo({ ouvindo: false, voz: 'idle', respondendo: true })).toBe('pensando');
  });

  it('cada estado tem cor, energia e texto para leitor de tela', () => {
    for (const v of Object.values(VISUAL)) {
      expect(v.cor).toHaveLength(3);
      expect(v.energia).toBeGreaterThan(0);
      expect(v.texto).toMatch(/^Éden /);
    }
  });
});
