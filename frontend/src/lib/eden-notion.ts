// Éden (Parte 4): Notion pela conexão interna (a chave fica no servidor).
import { edenJson } from './eden-org';
import type { Documento } from './eden-documentos';

export interface PaginaNotion {
  id: string;
  titulo: string;
  link: string | null;
  editado_em: string | null;
}

export interface StatusNotion {
  configurado: boolean;
  pai: { id: string; titulo: string } | null;
  fonte: string;
}

/** "editada 17/10" a partir da data do Notion (ISO). */
export function editadaEm(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `editada ${m[3]}/${m[2]}/${m[1]}` : '';
}

export const statusNotion = () => edenJson<StatusNotion>('/notion/status');
export const buscarNotion = (q: string) =>
  edenJson<{ resultados: PaginaNotion[] }>(`/notion/buscar?q=${encodeURIComponent(q)}`);
export const escolherPaiNotion = (id: string) =>
  edenJson<{ pai: { id: string; titulo: string } }>('/notion/pai', { method: 'POST', body: { id } });
export const esquecerPaiNotion = () => edenJson<{ pai: null }>('/notion/pai', { method: 'DELETE' });
export const importarDoNotion = (espaco: string, id: string) =>
  edenJson<{ documento: Documento & { aviso?: string } }>('/notion/importar', {
    method: 'POST',
    body: { espaco, id },
  });
export const salvarNoNotion = (titulo: string, markdown: string) =>
  edenJson<{ pagina: PaginaNotion }>('/notion/salvar', { method: 'POST', body: { titulo, markdown } });
