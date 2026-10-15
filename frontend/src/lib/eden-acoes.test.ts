// Éden: testes das ações sugeridas e das datas da organização.
import { describe, expect, it } from 'vitest';
import { parseActionsEvent, removeActionBlocks, visibleState } from './eden-acoes';
import { atrasada, textoData } from './eden-org';

describe('removeActionBlocks', () => {
  it('hides finished and unfinished action blocks', () => {
    const text = 'Posso criar.\n\n```eden-acao\n{"tipo": "tarefa.criar"}\n```\n';
    expect(removeActionBlocks(text)).toBe('Posso criar.');
    expect(removeActionBlocks('Ok.\n```eden-acao\n{"tipo": ')).toBe('Ok.');
  });

  it('keeps normal code blocks and text untouched', () => {
    const text = 'Veja:\n```python\nprint(1)\n```';
    expect(removeActionBlocks(text)).toBe(text);
  });
});

describe('parseActionsEvent', () => {
  it('reads actions and refusals', () => {
    const data = JSON.stringify({
      acoes: [{ id: 'abc12345', tipo: 'tarefa.criar', resumo: 'Criar', assinatura: 'f'.repeat(64), estado: 'pendente', expira_em: 10 }],
      recusadas: ['tipo de ação desconhecido'],
    });
    const { acoes, recusadas } = parseActionsEvent(data);
    expect(acoes).toHaveLength(1);
    expect(acoes[0].resumo).toBe('Criar');
    expect(recusadas).toEqual(['tipo de ação desconhecido']);
  });

  it('ignores garbage', () => {
    expect(parseActionsEvent('{x')).toEqual({ acoes: [], recusadas: [] });
    expect(parseActionsEvent(JSON.stringify({ acoes: [{ id: 1 }] })).acoes).toEqual([]);
  });
});

describe('visibleState', () => {
  it('turns an old pending action into expired', () => {
    expect(visibleState({ estado: 'pendente', expira_em: 1000 }, 2000)).toBe('expirada');
    expect(visibleState({ estado: 'pendente', expira_em: 3000 }, 2000)).toBe('pendente');
    expect(visibleState({ estado: 'feita', expira_em: 1000 }, 2000)).toBe('feita');
  });
});

describe('textoData', () => {
  const hoje = '2026-10-15';
  it('uses friendly words near today', () => {
    expect(textoData(null, null, hoje)).toBe('sem data');
    expect(textoData('2026-10-15', '18:00', hoje)).toBe('hoje 18:00');
    expect(textoData('2026-10-16', null, hoje)).toBe('amanhã');
    expect(textoData('2026-10-14', null, hoje)).toBe('ontem');
    expect(textoData('2026-10-20', null, hoje)).toBe('ter 20/10');
    expect(textoData('2027-01-02', null, hoje)).toBe('02/01/2027');
  });

  it('knows late tasks', () => {
    expect(atrasada({ data: '2026-10-14', feita: false }, hoje)).toBe(true);
    expect(atrasada({ data: '2026-10-14', feita: true }, hoje)).toBe(false);
    expect(atrasada({ data: null, feita: false }, hoje)).toBe(false);
  });
});
