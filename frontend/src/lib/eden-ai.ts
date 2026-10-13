// Éden: qual IA responde (ChatGPT no dia a dia, Claude nas missões).
//
// O app escolhe um dos três "modelos" do Éden; o servidor troca pelo modelo de
// verdade e devolve, nos cabeçalhos X-Eden-*, qual IA respondeu e por quê.
import type { ChatMessage } from '../types';

export const EDEN_AUTO = 'eden-auto';
export const EDEN_AUTO_IN_MISSION = 'eden-auto+missao';
export const EDEN_DAILY = 'eden-dia';
export const EDEN_MISSION = 'eden-missao';

export interface EdenModeOption {
  id: string;
  short: string;
  hint: string;
}

export const EDEN_MODES: EdenModeOption[] = [
  { id: EDEN_AUTO, short: 'Automático', hint: 'O Éden escolhe: ChatGPT no dia a dia, Claude nas missões' },
  { id: EDEN_DAILY, short: 'Dia a dia', hint: 'Sempre o ChatGPT' },
  { id: EDEN_MISSION, short: 'Missão', hint: 'Sempre o Claude (documentos, propostas, projetos)' },
];

export type EdenMode = 'dia' | 'missao';
export type EdenProvider = 'openai' | 'anthropic';

export interface EdenRoute {
  mode: EdenMode;
  model: string;
  provider: EdenProvider;
  reason: string;
}

export function isEdenModel(id: string | undefined | null): boolean {
  return id === EDEN_AUTO || id === EDEN_DAILY || id === EDEN_MISSION;
}

const MODEL_LABEL: Record<string, string> = {
  [EDEN_AUTO]: 'Éden · automático',
  [EDEN_DAILY]: 'ChatGPT · dia a dia',
  [EDEN_MISSION]: 'Claude · missão',
};

/** Nome amigável do modelo escolhido (para o menu). */
export function friendlyModelName(id: string): string {
  return MODEL_LABEL[id] ?? id;
}

export const REASON_LABEL: Record<string, string> = {
  escolha: 'modo escolhido por você',
  comando: 'você pediu com /missao ou /dia',
  entrega: 'pedido de documento ou entrega',
  cliente: 'mensagem para cliente',
  longo: 'pedido longo',
  continua: 'a conversa já estava em missão',
  padrao: 'dia a dia',
};

export function providerName(provider: string | undefined): string {
  if (provider === 'anthropic') return 'Claude';
  if (provider === 'openai') return 'ChatGPT';
  return 'IA';
}

/**
 * Modelo a pedir ao servidor. No automático, se a última resposta desta
 * conversa foi uma missão, avisa o servidor para continuar no Claude
 * (respostas curtas como "deixa mais curto" não voltam para o ChatGPT).
 */
export function requestModelFor(selected: string, history: ChatMessage[]): string {
  if (selected !== EDEN_AUTO) return selected;
  for (let i = history.length - 1; i >= 0; i--) {
    const m = history[i];
    if (m.role !== 'assistant') continue;
    const mode = m.telemetry?.eden_mode;
    if (mode) return mode === 'missao' ? EDEN_AUTO_IN_MISSION : EDEN_AUTO;
  }
  return EDEN_AUTO;
}

/** Lê dos cabeçalhos da resposta qual IA respondeu. */
export function routeFromHeaders(headers: Headers): EdenRoute | undefined {
  const mode = headers.get('X-Eden-Mode');
  const provider = headers.get('X-Eden-Provider');
  const model = headers.get('X-Eden-Model');
  if ((mode !== 'dia' && mode !== 'missao') || (provider !== 'openai' && provider !== 'anthropic') || !model) {
    return undefined;
  }
  return { mode, provider, model, reason: headers.get('X-Eden-Reason') ?? '' };
}
