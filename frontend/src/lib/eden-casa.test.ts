import { describe, expect, it } from 'vitest';
import { limparPasso, passoValido, textoPasso, valorPadrao, type AparelhoCasa } from './eden-casa';

const APARELHOS: AparelhoCasa[] = [
  { entidade: 'light.sala', nome: 'Luz da sala', dominio: 'light', acoes: ['ligar', 'desligar', 'cor', 'brilho'] },
  { entidade: 'climate.ar', nome: 'Ar', dominio: 'climate', acoes: ['ligar', 'desligar', 'temperatura'] },
];
const CORES = ['azul', 'branca'];

describe('casa', () => {
  it('confere os passos como o servidor', () => {
    expect(passoValido({ entidade: 'climate.ar', acao: 'temperatura', valor: 20 }, APARELHOS, CORES)).toBe(true);
    expect(passoValido({ entidade: 'climate.ar', acao: 'temperatura', valor: 31 }, APARELHOS, CORES)).toBe(false);
    expect(passoValido({ entidade: 'light.sala', acao: 'cor', valor: 'dourada' }, APARELHOS, CORES)).toBe(false);
    expect(passoValido({ entidade: 'light.sala', acao: 'temperatura', valor: 20 }, APARELHOS, CORES)).toBe(false);
    expect(passoValido({ entidade: 'lock.porta', acao: 'ligar' }, APARELHOS, CORES)).toBe(false);
    expect(passoValido({ entidade: 'light.sala', acao: 'ligar' }, APARELHOS, CORES)).toBe(true);
  });

  it('escreve o passo igual ao cartão', () => {
    expect(textoPasso({ entidade: 'climate.ar', acao: 'temperatura', valor: 20 }, APARELHOS)).toBe('Ar → 20 °C');
    expect(textoPasso({ entidade: 'light.sala', acao: 'cor', valor: 'azul' }, APARELHOS)).toBe('Luz da sala → cor azul');
  });

  it('manda só o que o servidor aceita', () => {
    expect(limparPasso({ entidade: 'light.sala', acao: 'ligar', valor: 70 })).toEqual({ entidade: 'light.sala', acao: 'ligar' });
    expect(valorPadrao('cor', CORES)).toBe('azul');
    expect(valorPadrao('ligar')).toBeUndefined();
  });
});
