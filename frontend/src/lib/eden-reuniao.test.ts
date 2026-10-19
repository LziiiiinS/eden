import { describe, expect, it } from 'vitest';
import { ErroEden } from './eden-org';
import {
  duracaoTexto,
  esperaDaTentativa,
  GravadorDeReuniao,
  valeTentarDeNovo,
  type SituacaoGravador,
} from './eden-reuniao';

describe('modo reunião', () => {
  it('espera cada vez mais entre as tentativas, até 30 s', () => {
    expect(esperaDaTentativa(0)).toBe(2000);
    expect(esperaDaTentativa(2)).toBe(8000);
    expect(esperaDaTentativa(10)).toBe(30_000);
  });

  it('tenta de novo só quando faz sentido', () => {
    expect(valeTentarDeNovo(new TypeError('Load failed'))).toBe(true);
    expect(valeTentarDeNovo(new ErroEden('ocupado', 502))).toBe(true);
    expect(valeTentarDeNovo(new ErroEden('em andamento', 409))).toBe(true);
    expect(valeTentarDeNovo(new ErroEden('terminou', 404))).toBe(false);
    expect(valeTentarDeNovo(new ErroEden('chave', 401))).toBe(false);
    expect(valeTentarDeNovo(new Error('outro'))).toBe(false);
  });

  it('mostra a duração', () => {
    expect(duracaoTexto(247)).toBe('4:07');
    expect(duracaoTexto(3909)).toBe('1:05:09');
  });

  it('a fila manda os pedaços em ordem e espera a internet voltar', async () => {
    const enviados: number[] = [];
    let falhas = 1;
    const enviar = async (_id: number, n: number) => {
      if (falhas > 0) {
        falhas -= 1;
        throw new TypeError('Load failed');
      }
      enviados.push(n);
      return { repetido: false };
    };
    const esperas: number[] = [];
    const situacoes: SituacaoGravador[] = [];
    const g = new GravadorDeReuniao(1, (s) => situacoes.push(s), enviar, async (ms) => {
      esperas.push(ms);
    });
    g.adicionarPedaco(new Blob(['a'], { type: 'audio/webm' }), 60_000);
    g.adicionarPedaco(new Blob(['b'], { type: 'audio/webm' }), 60_000);
    await g.terminar();
    expect(enviados).toEqual([0, 1]);
    // (3000 = a espera do último pedaço ao terminar; 2000 = a nova tentativa)
    expect(esperas).toContain(2000);
    expect(situacoes[situacoes.length - 1]).toMatchObject({ enviados: 2, naFila: 0, erro: null });
  });

  it('erro definitivo para a fila e avisa', async () => {
    const g = new GravadorDeReuniao(
      1,
      () => {},
      async () => {
        throw new ErroEden('esta reunião já terminou', 404);
      },
      async () => {},
    );
    g.adicionarPedaco(new Blob(['a']), 1000);
    await expect(g.terminar()).rejects.toThrow('esta reunião já terminou');
  });
});
