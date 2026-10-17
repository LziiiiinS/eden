// Éden: testes dos textos do Notion.
import { describe, expect, it } from 'vitest';
import { editadaEm } from './eden-notion';

describe('notion', () => {
  it('formats the last edit date', () => {
    expect(editadaEm('2026-10-17T12:00:00.000Z')).toBe('editada 17/10/2026');
    expect(editadaEm(null)).toBe('');
    expect(editadaEm('ontem')).toBe('');
  });
});
