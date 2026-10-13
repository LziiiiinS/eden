// Éden: testes das regras de sincronização.
import { describe, expect, it } from 'vitest';
import type { Conversation } from '../types';
import { isMessagePending, mergeConversations, needsPush, planPull } from './eden-sync-merge';

function conv(updatedAt: number, ids: Array<[string, number, string?]>, title = 'T'): Conversation {
  return {
    id: 'c1',
    title,
    model: 'm',
    createdAt: 100,
    updatedAt,
    messages: ids.map(([id, timestamp, content]) => ({
      id,
      role: 'user' as const,
      content: content ?? id,
      timestamp,
    })),
  };
}

describe('mergeConversations', () => {
  it('takes the remote conversation when there is no local copy', () => {
    const remote = conv(200, [['a', 110]]);
    expect(mergeConversations(undefined, remote)).toEqual(remote);
  });

  it('joins messages from both devices without duplicates, in time order', () => {
    const local = conv(200, [['a', 110], ['b', 150]]);
    const remote = conv(300, [['a', 110], ['c', 120]], 'Remoto');
    const merged = mergeConversations(local, remote);
    expect(merged.messages.map((m) => m.id)).toEqual(['a', 'c', 'b']);
    expect(merged.title).toBe('Remoto');
  });

  it('keeps the newer version of the same message', () => {
    const local = conv(200, [['a', 110, 'velha']]);
    const remote = conv(300, [['a', 110, 'nova']]);
    expect(mergeConversations(local, remote).messages[0].content).toBe('nova');
  });

  it('marks the result as newer than the server when this device has extra messages', () => {
    const local = conv(200, [['a', 110], ['b', 190]]);
    const remote = conv(300, [['a', 110]]);
    const merged = mergeConversations(local, remote);
    expect(merged.updatedAt).toBe(301);
    expect(needsPush(merged, 300)).toBe(true);
  });

  it('does not bump the version when the server already has everything', () => {
    const local = conv(200, [['a', 110]]);
    const remote = conv(300, [['a', 110], ['c', 250]]);
    const merged = mergeConversations(local, remote);
    expect(merged.updatedAt).toBe(300);
    expect(needsPush(merged, 300)).toBe(false);
  });
});

describe('needsPush', () => {
  it('pushes conversations never confirmed or changed since', () => {
    expect(needsPush(conv(200, []), undefined)).toBe(true);
    expect(needsPush(conv(200, []), 150)).toBe(true);
    expect(needsPush(conv(200, []), 200)).toBe(false);
  });

  it('pushes a new message even when this device clock is behind', () => {
    const late = conv(150, [['a', 110], ['b', 150]]);
    expect(needsPush(late, 300, ['a'])).toBe(true);
    expect(needsPush(late, 300, ['a', 'b'])).toBe(false);
  });
});

describe('isMessagePending', () => {
  it('is pending until the server confirms the message id', () => {
    expect(isMessagePending('a', undefined)).toBe(true);
    expect(isMessagePending('a', ['b'])).toBe(true);
    expect(isMessagePending('a', ['a', 'b'])).toBe(false);
  });
});

describe('planPull', () => {
  const meta = (id: string, updatedAt: number, deleted = false) => ({
    id,
    title: '',
    model: '',
    createdAt: 100,
    updatedAt,
    deleted,
  });

  it('fetches new and newer conversations and removes ones deleted elsewhere', () => {
    const local = {
      c1: { ...conv(200, []), id: 'c1' },
      c2: { ...conv(200, []), id: 'c2' },
      c3: { ...conv(200, []), id: 'c3' },
      c5: { ...conv(500, []), id: 'c5' },
    };
    const plan = planPull(
      local,
      [meta('c1', 300), meta('c2', 200), meta('c3', 250, true), meta('c4', 100), meta('c5', 400, true)],
      {},
    );
    expect(plan.toFetch).toEqual(['c1', 'c4']);
    expect(plan.alreadySynced).toEqual({ c2: 200 });
    // c5 foi editada aqui depois da exclusão no outro aparelho: fica.
    expect(plan.toRemove).toEqual(['c3']);
  });

  it('does not bring back a conversation this device is deleting', () => {
    const plan = planPull({}, [meta('c1', 300)], { c1: 350 });
    expect(plan.toFetch).toEqual([]);
  });
});
