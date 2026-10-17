// Éden: testes dos textos de rotas e trânsito.
import { describe, expect, it } from 'vitest';
import { lerCoordenadas, minutos, resumoTempo } from './eden-rotas';

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
