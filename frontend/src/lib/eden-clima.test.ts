// Éden: testes dos textos do clima.
import { describe, expect, it } from 'vitest';
import {
  corVento,
  descricaoTempo,
  lerCoordenadas,
  nos,
  numero,
  ondasDoDia,
  resumoDoDia,
  rotuloDia,
  rumo,
} from './eden-clima';

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

describe('resumo do dia', () => {
  it('summarizes weather and waves for the Today page', () => {
    const dia = {
      dia: '2026-10-17', codigo: 61, max: 24, min: 18, chuva_mm: 3, chuva_prob: 60,
      vento_kmh: 29.6, rajada_kmh: 45, vento_dir: 135,
    };
    expect(resumoDoDia(dia)).toBe('chuva fraca, 18–24 °C, chuva 60% · vento até 16 nós de SE');
    const hora = (h: string, m: number) => ({
      hora: h, temperatura: 20, chuva_prob: 0, chuva_mm: 0, codigo: 0, vento_kmh: 10, rajada_kmh: 15,
      vento_dir: 90, ondas_m: m, ondas_s: 9, ondas_dir: 135,
    });
    const previsao = {
      mar: true,
      dias: [dia],
      horas: [hora('2026-10-17T06:00', 1.2), hora('2026-10-17T15:00', 1.6), hora('2026-10-18T06:00', 3)],
    };
    expect(ondasDoDia(previsao)).toBe('ondas até 1,6 m (9 s, de SE)');
    expect(ondasDoDia({ ...previsao, mar: false })).toBeNull();
  });
});
