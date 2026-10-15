import type { ResearchEvent, SSEEvent } from '../types';
import { getBase, authHeaders } from './api';
import { routeFromHeaders } from './eden-ai';

/** Mensagem de erro do servidor (campo "detail"), quando houver. */
async function errorDetail(response: Response): Promise<string | undefined> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    return typeof detail === 'string' && detail ? detail : undefined;
  } catch {
    return undefined;
  }
}

export interface ChatRequest {
  model: string;
  messages: Array<{ role: string; content: string }>;
  stream: true;
  temperature?: number;
  max_tokens?: number;
}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
  extraHeaders: Record<string, string> = {},
): AsyncGenerator<SSEEvent> {
  const base = getBase();
  const response = await fetch(`${base}/v1/chat/completions`, {
    method: 'POST',
    headers: authHeaders({ ...extraHeaders, 'Content-Type': 'application/json' }),
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    // Éden: mostra o motivo em português (ex.: limite do mês atingido).
    const detail = await errorDetail(response);
    if (detail) throw new Error(detail);
    if (response.status === 401) throw new Error('Chave de acesso do servidor inválida.');
    throw new Error(`O servidor recusou o pedido (erro ${response.status}).`);
  }

  // Éden: avisa logo no começo qual IA vai responder.
  const route = routeFromHeaders(response.headers);
  if (route) yield { event: 'eden_route', data: JSON.stringify(route) };

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let currentEvent: string | undefined;

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6);
          if (data === '[DONE]') return;
          yield { event: currentEvent, data };
          currentEvent = undefined;
        } else if (line.trim() === '') {
          currentEvent = undefined;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function* streamResearch(
  query: string,
  model?: string,
  signal?: AbortSignal,
): AsyncGenerator<ResearchEvent> {
  // /api/research is mounted at the server root — strip any trailing /v1
  // from the base so configurations like "http://host:8000/v1" still resolve.
  const base = getBase().replace(/\/v1\/?$/, '');
  const response = await fetch(`${base}/api/research`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ query, ...(model ? { model } : {}) }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Research request failed: ${response.status}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data) as ResearchEvent;
          yield parsed;
          if (parsed.type === 'done') return;
        } catch {
          // skip malformed chunks
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
