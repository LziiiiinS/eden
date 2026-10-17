// Éden: testes dos textos do clima.
import { describe, expect, it } from 'vitest';
import { corVento, descricaoTempo, lerCoordenadas, nos, numero, rotuloDia, rumo } from './eden-clima';

describe('rumo e nós', () => {
  it('turns degrees and km/h into simple words', () => {
    expect(rumo(0)).toBe('N');
    expect(rumo(100)).toBe('L');
    expect(rumo(225)).toBe('SO');
    expect(rumo(-45)).toBe('NO');
    expect(rumo(null)).toBe('–');
    expect(nos(27.8)).toBe(15);
    expect(nos(null)).toBeNull();
    expect(numero(1.25, 1)).toBe('1,3');
    expect(numero(undefined)).toBe('–');
    expect(descricaoTempo(61)).toBe('chuva fraca');
  });
});

describe('lerCoordenadas', () => {
  it('reads what Google Maps copies', () => {
    expect(lerCoordenadas('-27.6025, -48.4320')).toEqual({ latitude: -27.6025, longitude: -48.432 });
    expect(lerCoordenadas('-27,6025 -48,4320')).toEqual({ latitude: -27.6025, longitude: -48.432 });
    expect(lerCoordenadas('praia mole')).toBeNull();
    expect(lerCoordenadas('91, 10')).toBeNull();
    expect(lerCoordenadas('1, 2, 3')).toBeNull();
  });
});

describe('rotuloDia e corVento', () => {
  it('labels days and colors wind', () => {
    expect(rotuloDia('2026-10-18')).toBe('dom 18');
    expect(corVento(5)).toBe('transparent');
    expect(corVento(25)).not.toBe('transparent');
  });
});
