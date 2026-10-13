// Éden: regras puras da sincronização de conversas (sem rede, sem estado).
// Ficam separadas para poder testar sem navegador.
import type { ChatMessage, Conversation } from '../types';

/** Dados de uma conversa como o servidor lista (sem mensagens). */
export interface RemoteConversationMeta {
  id: string;
  title: string;
  model: string;
  createdAt: number;
  updatedAt: number;
  deleted: boolean;
}

/**
 * Junta a versão do aparelho com a do servidor sem perder nem duplicar
 * mensagens. Mensagens com o mesmo ID ficam com a versão da conversa mais
 * nova; título e modelo também vêm da conversa mais nova.
 */
export function mergeConversations(
  local: Conversation | undefined,
  remote: Conversation,
): Conversation {
  if (!local) {
    return { ...remote, messages: [...remote.messages] };
  }
  const remoteIsNewer = remote.updatedAt >= local.updatedAt;
  const newer = remoteIsNewer ? remote : local;
  const older = remoteIsNewer ? local : remote;

  const byId = new Map<string, { msg: ChatMessage; order: number }>();
  let order = 0;
  for (const msg of older.messages) byId.set(msg.id, { msg, order: order++ });
  for (const msg of newer.messages) {
    const prev = byId.get(msg.id);
    byId.set(msg.id, { msg, order: prev ? prev.order : order++ });
  }
  const messages = [...byId.values()]
    .sort((a, b) => a.msg.timestamp - b.msg.timestamp || a.order - b.order)
    .map((entry) => entry.msg);

  // Se o aparelho tem mensagens que o servidor não tem, a conversa juntada
  // precisa ficar "mais nova" que a do servidor, para ser enviada de volta.
  const remoteIds = new Set(remote.messages.map((m) => m.id));
  const hasLocalOnly = local.messages.some((m) => !remoteIds.has(m.id));
  let updatedAt = Math.max(local.updatedAt, remote.updatedAt);
  if (hasLocalOnly && updatedAt <= remote.updatedAt) updatedAt = remote.updatedAt + 1;

  return {
    id: local.id,
    title: newer.title,
    model: newer.model,
    createdAt: Math.min(local.createdAt, remote.createdAt),
    updatedAt,
    messages,
  };
}

/**
 * A conversa tem mudanças que o servidor ainda não confirmou?
 * Além da versão, confere os IDs das mensagens: se o relógio deste aparelho
 * estiver atrasado, a versão pode parecer "velha" mesmo com mensagem nova.
 */
export function needsPush(
  conv: Conversation,
  syncedVersion: number | undefined,
  confirmedIds?: readonly string[],
): boolean {
  if (syncedVersion === undefined || conv.updatedAt > syncedVersion) return true;
  if (!confirmedIds) return false;
  const confirmed = new Set(confirmedIds);
  return conv.messages.some((m) => !confirmed.has(m.id));
}

/**
 * A mensagem ainda não chegou ao servidor? Vale para mensagens do usuário,
 * que não mudam depois de criadas: só conta como salva quando o servidor
 * confirmou aquele ID.
 */
export function isMessagePending(
  messageId: string,
  confirmedIds: readonly string[] | undefined,
): boolean {
  return !(confirmedIds ?? []).includes(messageId);
}

export interface PullPlan {
  /** Conversas que precisam ser baixadas inteiras do servidor. */
  toFetch: string[];
  /** Conversas apagadas em outro aparelho que devem sair deste. */
  toRemove: string[];
  /** Conversas que já estão iguais nos dois lados. */
  alreadySynced: Record<string, number>;
}

/** Compara a lista do servidor com o que está no aparelho. */
export function planPull(
  local: Record<string, Conversation>,
  remote: RemoteConversationMeta[],
  pendingDeletes: Record<string, number>,
): PullPlan {
  const plan: PullPlan = { toFetch: [], toRemove: [], alreadySynced: {} };
  for (const meta of remote) {
    const mine = local[meta.id];
    if (meta.deleted) {
      if (mine && mine.updatedAt <= meta.updatedAt) plan.toRemove.push(meta.id);
      continue;
    }
    if (pendingDeletes[meta.id] !== undefined) continue;
    if (!mine || meta.updatedAt > mine.updatedAt) {
      plan.toFetch.push(meta.id);
    } else if (meta.updatedAt === mine.updatedAt) {
      plan.alreadySynced[meta.id] = meta.updatedAt;
    }
  }
  return plan;
}
