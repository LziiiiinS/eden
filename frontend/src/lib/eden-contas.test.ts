import { describe, expect, it } from 'vitest';
import { agrupar, MODELOS, proximaData, proximoDia, reais, textoAviso, valorParaCampo, type Conta } from './eden-contas';

function conta(vencimento: string, id = 1): Conta {
  return {
    id,
    espaco: 'pessoal',
    tipo: 'pagar',
    descricao: 'Fictícia',
    valor_centavos: 1000,
    vencimento,
    dia: Number(vencimento.slice(8, 10)),
    repete: 'nao',
    categoria: '',
    aviso_dias: 2,
    pago_em: null,
    paga: false,
    notas: '',
    origem: 'voce',
    criado_em: 0,
  };
}

describe('eden-contas', () => {
  it('formats money like Brazil', () => {
    expect(reais(123456)).toBe('R$ 1.234,56');
    expect(reais(150000000)).toBe('R$ 1.500.000,00');
    expect(reais(5)).toBe('R$ 0,05');
    expect(reais(0)).toBe('sem valor');
    expect(valorParaCampo(150050)).toBe('1500,50');
    expect(valorParaCampo(0)).toBe('');
  });

  it('finds the next day of the month', () => {
    expect(proximoDia(20, '2026-10-17')).toBe('2026-10-20');
    expect(proximoDia(20, '2026-10-20')).toBe('2026-10-20');
    expect(proximoDia(20, '2026-10-21')).toBe('2026-11-20');
    expect(proximoDia(20, '2026-12-25')).toBe('2027-01-20');
    expect(proximoDia(31, '2026-02-10')).toBe('2026-02-28');
    expect(proximaData(5, 31, '2026-10-17')).toBe('2027-05-31');
    expect(proximaData(5, 31, '2026-03-01')).toBe('2026-05-31');
  });

  it('has MEI presets without made-up values', () => {
    const das = MODELOS[0];
    expect(das.repete).toBe('mensal');
    expect(das.vencimento('2026-10-17')).toBe('2026-10-20');
    expect(MODELOS.every((m) => m.dica.includes('Portal do Empreendedor'))).toBe(true);
  });

  it('groups by due date', () => {
    const g = agrupar([conta('2026-10-10', 1), conta('2026-10-20', 2), conta('2026-11-30', 3)], '2026-10-17');
    expect(g.atrasadas.map((c) => c.id)).toEqual([1]);
    expect(g.semana.map((c) => c.id)).toEqual([2]);
    expect(g.depois.map((c) => c.id)).toEqual([3]);
  });

  it('describes the reminder', () => {
    expect(textoAviso(-1)).toBe('sem aviso');
    expect(textoAviso(0)).toBe('aviso no dia');
    expect(textoAviso(1)).toBe('aviso 1 dia antes');
    expect(textoAviso(3)).toBe('aviso 3 dias antes');
  });
});
