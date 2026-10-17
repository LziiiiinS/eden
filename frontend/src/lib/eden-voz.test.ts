// Éden: testes da resposta em voz (texto de fala, pedaços e tocador).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from './api';
import {
  MAX_FALA,
  __zerarVozParaTestes,
  desbloquearAudio,
  dividirParaFala,
  textoParaFala,
  useEdenVozStore,
} from './eden-voz';

const fetchMock = vi.mocked(apiFetch);

class FakeAudio {
  static instances: FakeAudio[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  src = '';
  preload = '';
  plays: string[] = [];
  constructor() {
    FakeAudio.instances.push(this);
  }
  play(): Promise<void> {
    this.plays.push(this.src);
    return Promise.resolve();
  }
  pause(): void {}
}

beforeEach(() => {
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio);
  let n = 0;
  vi.stubGlobal('URL', { createObjectURL: () => `blob:fake/${++n}`, revokeObjectURL: () => {} });
  fetchMock.mockReset();
  __zerarVozParaTestes();
  FakeAudio.instances = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('texto de fala', () => {
  it('removes markdown, links, code, tables and sources', () => {
    const md =
      '## Amanhã\n\nVai **chover** em [Barra](https://x.com) 🌧️.\n\n- Leve guarda-chuva\n\n| a | b |\n|---|---|\n\n```py\nprint(1)\n```\n\n**Fontes:**\n- [g1](https://g1.globo.com)';
    expect(textoParaFala(md)).toBe(
      'Amanhã. Vai chover em Barra. Leve guarda-chuva. (tem uma tabela na tela) (tem um trecho de código na tela).',
    );
    expect(textoParaFala('```eden-acao\n{"tipo":"x"}\n```')).toBe('');
  });

  it('splits into sentences, short first piece, capped length', () => {
    const longo = 'Frase número um bem comprida para testar. '.repeat(60);
    const pedacos = dividirParaFala(longo);
    expect(pedacos[0].length).toBeLessThanOrEqual(220);
    expect(pedacos.every((p) => p.length <= 600)).toBe(true);
    expect(pedacos[pedacos.length - 1]).toBe('O resto está na tela.');
    expect(pedacos.slice(0, -1).join(' ').length).toBeLessThanOrEqual(MAX_FALA);
    expect(dividirParaFala('Oi, Levi!')).toEqual(['Oi, Levi!']);
    expect(dividirParaFala('   ')).toEqual([]);
  });
});

describe('tocador', () => {
  const ok = () => ({ ok: true, blob: () => Promise.resolve(new Blob(['mp3'])) }) as unknown as Response;

  it('speaks each piece in order on the same audio element', async () => {
    fetchMock.mockImplementation(() => Promise.resolve(ok()));
    desbloquearAudio();
    const texto = 'Primeira frase curta. ' + 'Outra frase que continua a resposta. '.repeat(10);
    const fala = useEdenVozStore.getState().speak('m1', texto);
    // Toca o primeiro pedaço e termina cada um.
    for (let i = 0; i < 10; i++) {
      await new Promise((r) => setTimeout(r, 0));
      FakeAudio.instances[0]?.onended?.();
    }
    await fala;
    expect(FakeAudio.instances).toHaveLength(1);
    const corpos = fetchMock.mock.calls.map((c) => JSON.parse(String((c[1] as RequestInit).body)));
    expect(corpos.length).toBeGreaterThanOrEqual(2);
    expect(corpos[0].texto).toBe('Primeira frase curta. Outra frase que continua a resposta. Outra frase que continua a resposta. Outra frase que continua a resposta. Outra frase que continua a resposta. Outra frase que continua a resposta.');
    expect(fetchMock.mock.calls[0][0]).toBe('/v1/eden/voz');
    expect(useEdenVozStore.getState().state).toBe('idle');
  });

  it('shows the server message when the voice fails', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      json: () => Promise.resolve({ detail: 'Limite do mês atingido.' }),
    } as unknown as Response);
    await useEdenVozStore.getState().speak('m2', 'Olá.');
    const s = useEdenVozStore.getState();
    expect(s.error).toBe('Limite do mês atingido.');
    expect(s.errorId).toBe('m2');
    expect(s.state).toBe('idle');
  });

  it('health probe reads the Éden voice status', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve({ available: true }) } as unknown as Response);
    await useEdenVozStore.getState().ensureHealth();
    expect(useEdenVozStore.getState().available).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith('/v1/eden/voz/status');
  });
});
