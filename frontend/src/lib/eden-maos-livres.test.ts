import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DetectorDeFala,
  MaosLivres,
  PAUSA_DEPOIS_DA_RESPOSTA_MS,
  nivelRms,
  valeEnviar,
  type DependenciasMaosLivres,
  type EstadoMaosLivres,
} from './eden-maos-livres';

function quadros(d: DetectorDeFala, nivel: number, n: number) {
  const eventos: string[] = [];
  for (let i = 0; i < n; i += 1) {
    const e = d.quadro(nivel);
    if (e) eventos.push(e);
  }
  return eventos;
}

describe('detector de fala', () => {
  it('começa com voz por 150 ms e termina com 1,2 s de silêncio', () => {
    const d = new DetectorDeFala();
    expect(quadros(d, 0.005, 40)).toEqual([]); // silêncio
    expect(quadros(d, 0.2, 2)).toEqual([]); // um estalo curto não conta
    expect(quadros(d, 0.005, 5)).toEqual([]);
    expect(quadros(d, 0.2, 3)).toEqual(['comecou']);
    expect(quadros(d, 0.2, 20)).toEqual([]);
    expect(quadros(d, 0.005, 23)).toEqual([]); // pausa entre palavras
    expect(quadros(d, 0.2, 1)).toEqual([]);
    expect(quadros(d, 0.005, 24)).toEqual(['terminou']);
  });

  it('acompanha o ruído de fundo (ventilador não vira fala)', () => {
    const d = new DetectorDeFala();
    expect(quadros(d, 0.03, 200)).toEqual([]);
    expect(d.ruidoDeFundo).toBeGreaterThan(0.02);
    expect(quadros(d, 0.15, 3)).toEqual(['comecou']); // voz bem acima do fundo
  });

  it('ignora leituras estranhas', () => {
    const d = new DetectorDeFala();
    expect(quadros(d, Number.NaN, 10)).toEqual([]);
    expect(d.emFala).toBe(false);
  });

  it('nível e mensagens curtas', () => {
    expect(nivelRms([0.5, -0.5, 0.5, -0.5])).toBeCloseTo(0.5);
    expect(nivelRms([])).toBe(0);
    expect(valeEnviar('Obrigado.')).toBe(false);
    expect(valeEnviar('que horas é a reunião')).toBe(true);
  });
});

class GravadorFalso {
  state: 'inactive' | 'recording' = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['voz'], { type: 'audio/webm' }) });
    this.onstop?.();
  }
}

function montar(podeOuvir: () => boolean) {
  let agora = 0;
  let aoQuadro: ((n: number) => void) | null = null;
  const trilhas: Array<{ parada: boolean }> = [];
  const estados: EstadoMaosLivres[] = [];
  const falas: number[] = [];
  const dep: DependenciasMaosLivres = {
    pedirMicrofone: async () => {
      const t = { parada: false };
      trilhas.push(t);
      return { getTracks: () => [{ stop: () => (t.parada = true) }] } as unknown as MediaStream;
    },
    criarGravador: () => new GravadorFalso() as unknown as MediaRecorder,
    medirNivel: (_s, cb) => {
      aoQuadro = cb;
      return () => {
        aoQuadro = null;
      };
    },
    agora: () => agora,
  };
  const m = new MaosLivres(
    {
      aoFalar: async (_a, dur) => {
        falas.push(dur);
      },
      aoMudar: (e) => estados.push(e),
      podeOuvir,
    },
    dep,
  );
  const som = (nivel: number, n: number) => {
    for (let i = 0; i < n; i += 1) {
      agora += 50;
      aoQuadro?.(nivel);
    }
  };
  return { m, som, estados, falas, trilhas, avancar: (ms: number) => (agora += ms) };
}

describe('mãos livres', () => {
  afterEach(() => vi.useRealTimers());

  it('ouve, grava a fala, solta o microfone e volta a ouvir depois da resposta', async () => {
    vi.useFakeTimers();
    let ocupado = true;
    const t = montar(() => !ocupado);
    await t.m.ligar();
    expect(t.m.situacao).toBe('ouvindo');
    t.som(0.005, 10);
    t.som(0.2, 20);
    expect(t.m.situacao).toBe('gravando');
    t.som(0.005, 24);
    await vi.waitFor(() => expect(t.m.situacao).toBe('pensando'));
    expect(t.falas.length).toBe(1);
    expect(t.trilhas[0].parada).toBe(true); // microfone solto enquanto o Éden responde
    // Ainda respondendo: não volta a ouvir.
    vi.advanceTimersByTime(2000);
    expect(t.m.situacao).toBe('pensando');
    ocupado = false;
    t.avancar(PAUSA_DEPOIS_DA_RESPOSTA_MS + 200);
    vi.advanceTimersByTime(300);
    t.avancar(PAUSA_DEPOIS_DA_RESPOSTA_MS + 200);
    vi.advanceTimersByTime(300);
    await vi.waitFor(() => expect(t.m.situacao).toBe('ouvindo'));
    expect(t.trilhas.length).toBe(2);
    t.m.desligar();
    expect(t.m.situacao).toBe('desligado');
    expect(t.trilhas[1].parada).toBe(true);
  });

  it('desliga sozinho depois de 1 minuto em silêncio', async () => {
    const t = montar(() => true);
    await t.m.ligar();
    t.som(0.005, 1300); // 65 s
    expect(t.m.situacao).toBe('desligado');
    expect(t.trilhas[0].parada).toBe(true);
  });

  it('fala curta demais não é enviada', async () => {
    const t = montar(() => true);
    await t.m.ligar();
    t.som(0.2, 4); // 200 ms
    t.som(0.005, 24);
    await vi.waitFor(() => expect(t.m.situacao).toBe('ouvindo'));
    expect(t.falas).toEqual([]);
  });
});
