// Éden: sincronização das conversas com o servidor (celular ↔ notebook).
//
// Como funciona:
// - O aparelho continua guardando as conversas localmente (funciona sem
//   internet). Toda mudança é enviada ao servidor assim que possível.
// - Uma mensagem só conta como salva quando o servidor confirma. Até lá, ela
//   aparece como "Não sincronizada".
// - Ao abrir o app, ao voltar para ele e a cada 30 s, o app busca no servidor
//   o que mudou em outros aparelhos e junta sem duplicar.
import { create } from 'zustand';
import { apiFetch } from './api';
import { useAppStore } from './store';
import type { Conversation } from '../types';
import {
  mergeConversations,
  needsPush,
  planPull,
  type RemoteConversationMeta,
} from './eden-sync-merge';

export type SyncStatus = 'idle' | 'syncing' | 'synced' | 'offline' | 'error';

interface PersistedSync {
  /** Versão (updatedAt) de cada conversa que o servidor já confirmou. */
  syncedVersions: Record<string, number>;
  /** IDs de mensagens que o servidor já confirmou, por conversa. */
  confirmedIds: Record<string, string[]>;
  /** Conversas apagadas aqui que o servidor ainda não soube. */
  pendingDeletes: Record<string, number>;
}

interface SyncStore extends PersistedSync {
  status: SyncStatus;
  lastSyncedAt: number | null;
  errorMessage: string | null;
}

// Mesmo formato e chave usados por lib/store.ts para guardar as conversas.
const CONVERSATIONS_KEY = 'openjarvis-conversations';
const SYNC_KEY = 'eden-sync';
const PUSH_DELAY_MS = 1500;
const POLL_MS = 30_000;

interface LocalConversationStore {
  version: 1;
  conversations: Record<string, Conversation>;
  activeId: string | null;
}

interface RemoteConversation extends Conversation {
  deleted?: boolean;
}

function loadPersisted(): PersistedSync {
  try {
    const raw = localStorage.getItem(SYNC_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        syncedVersions: parsed.syncedVersions ?? {},
        confirmedIds: parsed.confirmedIds ?? {},
        pendingDeletes: parsed.pendingDeletes ?? {},
      };
    }
  } catch {
    // Sem armazenamento local: tudo será reenviado; o servidor não duplica.
  }
  return { syncedVersions: {}, confirmedIds: {}, pendingDeletes: {} };
}

export const useSyncStore = create<SyncStore>(() => ({
  ...loadPersisted(),
  status: 'idle',
  lastSyncedAt: null,
  errorMessage: null,
}));

function persist(): void {
  const { syncedVersions, confirmedIds, pendingDeletes } = useSyncStore.getState();
  try {
    localStorage.setItem(SYNC_KEY, JSON.stringify({ syncedVersions, confirmedIds, pendingDeletes }));
  } catch {
    // Melhor esforço.
  }
}

/** Marca a versão e as mensagens que o servidor confirmou. */
function confirm(id: string, version: number, messageIds: string[]): void {
  useSyncStore.setState((s) => ({
    syncedVersions: { ...s.syncedVersions, [id]: version },
    confirmedIds: {
      ...s.confirmedIds,
      [id]: [...new Set([...(s.confirmedIds[id] ?? []), ...messageIds])],
    },
  }));
}

function forget(id: string): void {
  useSyncStore.setState((s) => {
    const syncedVersions = { ...s.syncedVersions };
    const confirmedIds = { ...s.confirmedIds };
    delete syncedVersions[id];
    delete confirmedIds[id];
    return { syncedVersions, confirmedIds };
  });
}

function readLocal(): LocalConversationStore {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.version === 1) {
        return {
          version: 1,
          conversations: parsed.conversations ?? {},
          activeId: parsed.activeId ?? null,
        };
      }
    }
  } catch {
    // Trata como vazio.
  }
  return { version: 1, conversations: {}, activeId: null };
}

function streamingConversationId(): string | null {
  const s = useAppStore.getState().streamState;
  return s.isStreaming ? s.conversationId : null;
}

// IDs que este módulo tirou do aparelho por causa do servidor (para não
// confundir com o usuário apagando).
const removedByRemote = new Set<string>();

/** Grava no aparelho o que veio do servidor e atualiza a tela. */
function applyRemote(upserts: Conversation[], removals: string[]): void {
  if (upserts.length === 0 && removals.length === 0) return;
  const skip = streamingConversationId();
  const store = readLocal();
  for (const remote of upserts) {
    if (remote.id === skip) continue;
    store.conversations[remote.id] = mergeConversations(store.conversations[remote.id], remote);
  }
  for (const id of removals) {
    if (id === skip || !store.conversations[id]) continue;
    delete store.conversations[id];
    removedByRemote.add(id);
    if (store.activeId === id) store.activeId = null;
  }
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(store));
  } catch {
    return;
  }
  const app = useAppStore.getState();
  app.loadConversations();
  app.loadMessages(useAppStore.getState().activeId);
}

class HttpError extends Error {
  status: number;

  constructor(status: number) {
    super(`HTTP ${status}`);
    this.status = status;
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) throw new HttpError(res.status);
  return (await res.json()) as T;
}

async function fetchRemote(id: string): Promise<RemoteConversation> {
  const data = await requestJson<{ conversation: RemoteConversation }>(
    `/v1/eden/conversations/${encodeURIComponent(id)}`,
  );
  return data.conversation;
}

/** Baixa uma conversa do servidor e junta com a deste aparelho. */
async function fetchAndMerge(id: string): Promise<void> {
  const remote = await fetchRemote(id);
  if (remote.deleted) {
    applyRemote([], [id]);
    forget(id);
    return;
  }
  if (id === streamingConversationId()) return; // tenta de novo depois da resposta
  applyRemote([remote], []);
  confirm(
    id,
    remote.updatedAt,
    remote.messages.map((m) => m.id),
  );
}

async function pull(): Promise<void> {
  const { pendingDeletes } = useSyncStore.getState();
  const list = await requestJson<{ conversations: RemoteConversationMeta[] }>(
    '/v1/eden/conversations',
  );
  const skip = streamingConversationId();
  const local = readLocal().conversations;
  const plan = planPull(local, list.conversations, pendingDeletes);

  for (const id of plan.toFetch) {
    if (id === skip) continue;
    await fetchAndMerge(id);
  }
  for (const [id, version] of Object.entries(plan.alreadySynced)) {
    // Mesma versão nos dois lados: as mensagens daqui estão no servidor.
    confirm(
      id,
      version,
      (local[id]?.messages ?? []).map((m) => m.id),
    );
  }
  const removals = plan.toRemove.filter((id) => id !== skip);
  applyRemote([], removals);
  removals.forEach(forget);
}

async function pushDeletes(): Promise<void> {
  const pending = { ...useSyncStore.getState().pendingDeletes };
  for (const [id, deletedAt] of Object.entries(pending)) {
    const data = await requestJson<{ conversation: RemoteConversationMeta }>(
      `/v1/eden/conversations/${encodeURIComponent(id)}?deleted_at=${deletedAt}`,
      { method: 'DELETE' },
    );
    useSyncStore.setState((s) => {
      const pendingDeletes = { ...s.pendingDeletes };
      delete pendingDeletes[id];
      return { pendingDeletes };
    });
    forget(id);
    if (!data.conversation.deleted) {
      // Outro aparelho mexeu na conversa depois da exclusão: ela volta.
      await fetchAndMerge(id);
    }
  }
}

async function pushChanges(): Promise<void> {
  const skip = streamingConversationId();
  const { syncedVersions, confirmedIds } = useSyncStore.getState();
  const local = readLocal().conversations;
  for (const conv of Object.values(local)) {
    if (conv.id === skip) continue;
    if (!needsPush(conv, syncedVersions[conv.id], confirmedIds[conv.id] ?? [])) continue;
    const data = await requestJson<{
      conversation: RemoteConversationMeta;
      serverHasMore?: boolean;
    }>(`/v1/eden/conversations/${encodeURIComponent(conv.id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(conv),
    });
    const meta = data.conversation;
    if (meta.deleted) {
      applyRemote([], [conv.id]);
      forget(conv.id);
      continue;
    }
    confirm(
      conv.id,
      conv.updatedAt,
      conv.messages.map((m) => m.id),
    );
    if (meta.updatedAt > conv.updatedAt || data.serverHasMore) {
      // O servidor tem algo que este aparelho não tem: busca e junta.
      await fetchAndMerge(conv.id);
    }
  }
}

let current: Promise<void> | null = null;
let rerun = false;

async function runRounds(): Promise<void> {
  do {
    rerun = false;
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      useSyncStore.setState({ status: 'offline', errorMessage: null });
      return;
    }
    useSyncStore.setState({ status: 'syncing' });
    try {
      await pushDeletes();
      await pull();
      await pushChanges();
      useSyncStore.setState({ status: 'synced', lastSyncedAt: Date.now(), errorMessage: null });
    } catch (err) {
      if (err instanceof HttpError) {
        useSyncStore.setState({
          status: 'error',
          errorMessage:
            err.status === 401
              ? 'Chave de acesso do servidor inválida.'
              : err.status === 404
                ? 'Este servidor ainda não tem a sincronização do Éden.'
                : `O servidor recusou (erro ${err.status}).`,
        });
      } else {
        useSyncStore.setState({ status: 'offline', errorMessage: null });
      }
      return;
    } finally {
      persist();
    }
  } while (rerun);
}

/**
 * Faz uma rodada completa: envia exclusões, busca novidades e envia mudanças.
 * Se já houver uma rodada em andamento, agenda outra logo depois e devolve a
 * mesma promessa (quem espera recebe o fim das duas).
 */
export function syncNow(): Promise<void> {
  if (current) {
    rerun = true;
    return current;
  }
  current = runRounds().finally(() => {
    current = null;
  });
  return current;
}

let pushTimer: ReturnType<typeof setTimeout> | null = null;

function schedule(delay = PUSH_DELAY_MS): void {
  if (pushTimer) clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    pushTimer = null;
    void syncNow();
  }, delay);
}

let started = false;

/** Liga a sincronização. Chamar uma vez, quando o app abre. */
export function startEdenSync(): void {
  if (started || typeof window === 'undefined') return;
  started = true;

  let knownIds = new Set(useAppStore.getState().conversations.map((c) => c.id));

  useAppStore.subscribe((state, prev) => {
    if (state.conversations !== prev.conversations) {
      const currentIds = new Set(state.conversations.map((c) => c.id));
      let deleted = false;
      for (const id of knownIds) {
        if (currentIds.has(id)) continue;
        if (removedByRemote.has(id)) {
          removedByRemote.delete(id);
          continue;
        }
        useSyncStore.setState((s) => ({
          pendingDeletes: { ...s.pendingDeletes, [id]: Date.now() },
        }));
        deleted = true;
      }
      knownIds = currentIds;
      if (deleted) persist();
      schedule();
    }
    // Quando uma resposta termina, envia a conversa.
    if (prev.streamState.isStreaming && !state.streamState.isStreaming) schedule(300);
  });

  window.addEventListener('online', () => schedule(0));
  window.addEventListener('offline', () =>
    useSyncStore.setState({ status: 'offline', errorMessage: null }),
  );
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') schedule(0);
  });
  setInterval(() => {
    if (document.visibilityState === 'visible') void syncNow();
  }, POLL_MS);

  void syncNow();
}
