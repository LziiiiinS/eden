// Éden: testes dos textos do e-mail.
import { describe, expect, it } from 'vitest';
import { mensagemDaVoltaEmail, quando, remetente } from './eden-email';

describe('email', () => {
  it('formats sender and date', () => {
    const base = { id: 'm1', assunto: 'x', trecho: '', recebido_em: 0, nao_lido: false };
    expect(remetente({ ...base, de: { nome: 'Ana', email: 'ana@x.com' } })).toBe('Ana');
    expect(remetente({ ...base, de: { nome: '', email: 'ana@x.com' } })).toBe('ana@x.com');
    const agora = new Date(2026, 9, 17, 20, 0);
    expect(quando(new Date(2026, 9, 17, 14, 5).getTime(), agora)).toBe('hoje 14:05');
    expect(quando(new Date(2026, 9, 16, 9, 0).getTime(), agora)).toBe('16/10');
  });

  it('explains the return from Google', () => {
    expect(mensagemDaVoltaEmail('conectado')).toContain('só leitura');
    expect(mensagemDaVoltaEmail('xyz')).toBeNull();
  });
});
