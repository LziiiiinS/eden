// Éden: testes da conversa enviada para a IA quando houve pesquisa na internet.
import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '../types';
import { MARCA_PESQUISA, ehPesquisa, mensagensParaIa } from './eden-pesquisa';

const msg = (role: 'user' | 'assistant', content: string, extra: Partial<ChatMessage> = {}): ChatMessage => ({
  id: `${role}-${content.length}`,
  role,
  content,
  timestamp: 1,
  ...extra,
});

describe('pesquisa na internet', () => {
  it('recognises search answers', () => {
    expect(ehPesquisa(msg('assistant', 'x', { edenPesquisa: true }))).toBe(true);
    expect(ehPesquisa(msg('assistant', 'x', { telemetry: { eden_reason: 'pesquisa' } }))).toBe(true);
    expect(ehPesquisa(msg('assistant', 'x', { telemetry: { eden_reason: 'escolha' } }))).toBe(false);
    expect(ehPesquisa(msg('assistant', 'x'))).toBe(false);
  });

  it('marks search answers as outside data and strips action blocks', () => {
    const bloco = '```eden-acao\n{"tipo":"tarefa.criar","titulo":"x"}\n```';
    const saida = mensagensParaIa([
      msg('user', 'Quem ganhou?'),
      msg('assistant', 'O Flamengo.\n\n**Fontes:**\n- [ge](https://ge.globo.com/)', { edenPesquisa: true }),
      msg('user', 'Anota isso'),
      msg('assistant', `Feito.\n${bloco}`),
    ]);
    expect(saida[0]).toEqual({ role: 'user', content: 'Quem ganhou?' });
    expect(saida[1].content.startsWith(`${MARCA_PESQUISA}\n\nO Flamengo.`)).toBe(true);
    expect(saida[3]).toEqual({ role: 'assistant', content: 'Feito.' });
  });

  it('never marks user messages', () => {
    const saida = mensagensParaIa([msg('user', 'oi', { edenPesquisa: true })]);
    expect(saida[0].content).toBe('oi');
  });
});
