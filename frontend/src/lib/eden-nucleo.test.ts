import { describe, expect, it } from 'vitest';
import {
  corCss,
  estadoNucleo,
  gradeDoHorizonte,
  quadrosPorSegundo,
  resolucaoDoFundo,
  VISUAL,
} from './eden-nucleo';
import { HORIZONTE_FRAGMENTO, HORIZONTE_VERTICE, NUCLEO_FRAGMENTO } from '../components/Eden/eden-shaders';

describe('estadoNucleo', () => {
  it('mostra o que o Éden está fazendo', () => {
    expect(estadoNucleo({ ouvindo: false, voz: 'idle', respondendo: false })).toBe('repouso');
    expect(estadoNucleo({ ouvindo: true, voz: 'speaking', respondendo: true })).toBe('ouvindo');
    expect(estadoNucleo({ ouvindo: false, voz: 'speaking', respondendo: true })).toBe('falando');
    expect(estadoNucleo({ ouvindo: false, voz: 'loading', respondendo: false })).toBe('pensando');
    expect(estadoNucleo({ ouvindo: false, voz: 'idle', respondendo: true })).toBe('pensando');
  });

  it('cada estado tem cor, energia, ritmo, giro e texto para leitor de tela', () => {
    for (const v of Object.values(VISUAL)) {
      expect(v.cor).toHaveLength(3);
      expect(v.energia).toBeGreaterThan(0);
      expect(v.ritmo).toBeGreaterThan(0);
      expect(v.giro).toBeGreaterThan(0);
      expect(v.texto).toMatch(/^Éden /);
    }
  });

  it('cor em CSS', () => {
    expect(corCss('pensando')).toBe('rgb(143, 117, 255)');
  });
});

describe('fundo 3D: cuidado com a bateria', () => {
  it('celular desenha menos pontos que o notebook', () => {
    const cel = gradeDoHorizonte(390);
    const note = gradeDoHorizonte(1440);
    expect(cel.colunas * cel.linhas).toBeLessThan(note.colunas * note.linhas);
    // Os índices da malha cabem em 16 bits (WebGL 1).
    expect(note.colunas * note.linhas).toBeLessThan(65536);
  });

  it('resolução limitada (iPhone de tela densa e monitor grande)', () => {
    const iphone = resolucaoDoFundo(390, 844, 3);
    expect(iphone.escala).toBe(1.5);
    expect(iphone.w).toBe(585);
    const monitor = resolucaoDoFundo(2560, 1440, 2);
    expect(monitor.w * monitor.h).toBeLessThanOrEqual(1_400_000 + 4000);
    const comum = resolucaoDoFundo(1280, 800, 1);
    expect(comum).toEqual({ w: 1280, h: 800, escala: 1 });
  });

  it('menos quadros em repouso', () => {
    expect(quadrosPorSegundo('repouso')).toBeLessThan(quadrosPorSegundo('falando'));
    expect(quadrosPorSegundo('ouvindo')).toBeLessThanOrEqual(30);
  });

  it('os desenhos usam só os nomes que os componentes preenchem', () => {
    for (const nome of ['u_t', 'u_energia', 'u_fase', 'u_res', 'u_olhar', 'u_escala', 'u_modo', 'u_largura']) {
      expect(HORIZONTE_VERTICE).toContain(nome);
    }
    for (const nome of ['u_cor', 'u_claro', 'u_intensidade', 'u_linha']) {
      expect(HORIZONTE_FRAGMENTO).toContain(nome);
    }
    for (const nome of ['u_res', 'u_t', 'u_cor', 'u_energia', 'u_giro']) {
      expect(NUCLEO_FRAGMENTO).toContain(nome);
    }
  });
});
