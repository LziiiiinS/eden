// Éden (Parte 5): chave por aparelho — lista, criar (só no notebook) e desligar.
import { edenJson } from './eden-org';

export interface Aparelho {
  id: number;
  nome: string;
  criado_em: number;
  ultimo_uso: number | null;
}

export const listarAparelhos = () => edenJson<{ aparelhos: Aparelho[]; eu: number | null }>('/aparelhos');
export const criarAparelho = (nome: string) =>
  edenJson<{ id: number; chave: string }>('/aparelhos', { method: 'POST', body: { nome } });
export const desligarAparelho = (id: number) => edenJson<{ ok: boolean }>(`/aparelhos/${id}`, { method: 'DELETE' });

/** "hoje 14:05", "ontem 09:10", "12/10", ou "nunca usado". */
export function quandoUsado(ms: number | null, agora = new Date()): string {
  if (!ms) return 'nunca usado';
  const d = new Date(ms);
  const hora = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const mesmoDia = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (mesmoDia(d, agora)) return `hoje ${hora}`;
  const ontem = new Date(agora);
  ontem.setDate(agora.getDate() - 1);
  if (mesmoDia(d, ontem)) return `ontem ${hora}`;
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
}
