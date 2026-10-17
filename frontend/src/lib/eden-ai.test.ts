// Éden: testes da escolha de IA no app.
import { describe, expect, it } from 'vitest';
import type { ChatMessage } from '../types';
import {
  EDEN_AUTO,
  EDEN_AUTO_IN_MISSION,
  EDEN_DAILY,
  EDEN_MISSION,
  friendlyModelName,
  isEdenModel,
  requestModelFor,
  routeFromHeaders,
} from './eden-ai';

function reply(mode?: 'dia' | 'missao'): ChatMessage {
  return {
    id: `a-${mode ?? 'x'}`,
    role: 'assistant',
    content: 'ok',
    timestamp: 1,
    telemetry: mode ? { eden_mode: mode, eden_provider: mode === 'missao' ? 'anthropic' : 'openai' } : undefined,
  };
}

const ask: ChatMessage = { id: 'u', role: 'user', content: 'deixa mais curto', timestamp: 2 };

describe('requestModelFor', () => {
  it('keeps a conversation that became a mission with Claude', () => {
    expect(requestModelFor(EDEN_AUTO, [reply('missao'), ask])).toBe(EDEN_AUTO_IN_MISSION);
  });

  it('uses the latest answer that has a route', () => {
    expect(requestModelFor(EDEN_AUTO, [reply('missao'), reply('dia'), ask])).toBe(EDEN_AUTO);
    expect(requestModelFor(EDEN_AUTO, [reply('missao'), reply(undefined), ask])).toBe(EDEN_AUTO_IN_MISSION);
  });

  it('ignores web search answers (always Claude, not a mission)', () => {
    const busca: ChatMessage = {
      ...reply('missao'),
      id: 'busca',
      edenPesquisa: true,
      telemetry: { eden_mode: 'missao', eden_provider: 'anthropic', eden_reason: 'pesquisa' },
    };
    expect(requestModelFor(EDEN_AUTO, [reply('dia'), busca, ask])).toBe(EDEN_AUTO);
    expect(requestModelFor(EDEN_AUTO, [busca, ask])).toBe(EDEN_AUTO);
  });

  it('never changes a mode the user chose', () => {
    expect(requestModelFor(EDEN_DAILY, [reply('missao'), ask])).toBe(EDEN_DAILY);
    expect(requestModelFor('qwen3.5:4b', [reply('missao')])).toBe('qwen3.5:4b');
  });
});

describe('routeFromHeaders', () => {
  it('reads which AI answered', () => {
    const headers = new Headers({
      'X-Eden-Mode': 'missao',
      'X-Eden-Provider': 'anthropic',
      'X-Eden-Model': 'claude-sonnet-5-5',
      'X-Eden-Reason': 'entrega',
    });
    expect(routeFromHeaders(headers)).toEqual({
      mode: 'missao',
      provider: 'anthropic',
      model: 'claude-sonnet-5-5',
      reason: 'entrega',
    });
  });

  it('ignores servers without the Éden', () => {
    expect(routeFromHeaders(new Headers())).toBe(undefined);
  });
});

describe('names', () => {
  it('shows friendly names for the Éden modes only', () => {
    expect(friendlyModelName(EDEN_MISSION)).toBe('Claude · missão');
    expect(friendlyModelName('gpt-6.1-sol')).toBe('gpt-6.1-sol');
    expect(isEdenModel(EDEN_AUTO)).toBe(true);
    expect(isEdenModel(EDEN_AUTO_IN_MISSION)).toBe(false);
  });
});
