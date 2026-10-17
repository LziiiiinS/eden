// Éden: testes dos textos de rotas e trânsito.
import { describe, expect, it } from 'vitest';
import { diferenca, lerCoordenadas, minutos, pareceRota, resumoCaminho, resumoTempo } from './eden-rotas';

const trajeto = {
  id: 1,
  nome: 'Casa → Trabalho',
  origem: { nome: 'Casa', latitude: -22.97, longitude: -43.18 },
  destino: { nome: 'Trabalho', latitude: -23, longitude: -43.36 },
};

describe('rotas', () => {
  it('formats travel times', () => {
    expect(minutos(1680)).toBe('28 min');
    expect(minutos(4000)).toBe('1 h 07 min');
    expect(minutos(null)).toBe('–');
    expect(
      resumoTempo({ trajeto, segundos: 1680, atraso_s: 480, metros: 14200, chegada: '2026-10-17T17:28:00-03:00' }),
    ).toBe('28 min agora · +8 min de trânsito · 14,2 km · chega 17:28');
    expect(resumoTempo({ trajeto, erro: 'Sem resposta do TomTom agora.' })).toBe('Sem resposta do TomTom agora.');
  });

  it('reads coordinates pasted from Google Maps', () => {
    expect(lerCoordenadas('-22.97, -43.18')).toEqual({ latitude: -22.97, longitude: -43.18 });
    expect(lerCoordenadas('Av. das Américas 500')).toBeNull();
    expect(lerCoordenadas('91, 0')).toBeNull();
  });
});

describe('caminhos', () => {
  const rapido = { segundos: 1680, atraso_s: 480, metros: 14200, vias: ['Av. das Américas', 'Av. Ayrton Senna'] };
  const lento = { segundos: 1920, atraso_s: 0, metros: 15000, vias: ['Av. Lúcio Costa'] };

  it('summarises each alternative', () => {
    expect(resumoCaminho(rapido)).toBe('28 min · +8 min de trânsito · 14,2 km · via Av. das Américas, Av. Ayrton Senna');
    expect(resumoCaminho({ segundos: 600, vias: [] })).toBe('10 min');
    expect(diferenca(lento, rapido)).toBe('+4 min');
    expect(diferenca(rapido, rapido)).toBe('');
  });

  it('only sends the location for route questions', () => {
    expect(pareceRota('Me dá a melhor rota pro posto 4')).toBe(true);
    expect(pareceRota('Como está o TRÂNSITO?')).toBe(true);
    expect(pareceRota('qual o caminho mais rápido')).toBe(true);
    expect(pareceRota('resume esse documento')).toBe(false);
    expect(pareceRota('anota uma tarefa')).toBe(false);
  });
});
