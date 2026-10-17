// Éden: testes dos textos da Google Agenda.
import { describe, expect, it } from 'vitest';
import { horarioEvento, mensagemDaVolta } from './eden-agenda';

describe('horarioEvento', () => {
  it('shows start and end, or all day', () => {
    const inicio = new Date(2026, 9, 17, 14, 0).toISOString();
    const fim = new Date(2026, 9, 17, 15, 30).toISOString();
    expect(horarioEvento({ inicio, fim, dia_inteiro: false })).toBe('14:00–15:30');
    expect(horarioEvento({ inicio, fim: null, dia_inteiro: false })).toBe('14:00');
    expect(horarioEvento({ inicio, fim, dia_inteiro: true })).toBe('o dia todo');
  });
});

describe('mensagemDaVolta', () => {
  it('explains each result of the Google screen', () => {
    expect(mensagemDaVolta('conectado')).toEqual({ texto: 'Google Agenda conectada.', ok: true });
    expect(mensagemDaVolta('negado')?.ok).toBe(false);
    expect(mensagemDaVolta('qualquer')).toBeNull();
    expect(mensagemDaVolta(null)).toBeNull();
  });
});
