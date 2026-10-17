// Éden (Parte 3): documentos que a pessoa escolhe para a conversa.
// O servidor guarda só o texto; o arquivo original não fica lá.
import { apiFetch } from './api';
import { edenJson, ErroEden } from './eden-org';

export interface Documento {
  id: number;
  espaco: string;
  nome: string;
  tipo: 'pdf' | 'docx' | 'txt' | 'md';
  bytes: number;
  paginas: number | null;
  caracteres: number;
  cortado: boolean;
  criado_em: number;
  previa?: string;
}

export interface LimitesDocumentos {
  arquivo_bytes: number;
  por_conversa: number;
  por_espaco: number;
  no_contexto: number;
}

export const TIPOS_ACEITOS = ['pdf', 'docx', 'txt', 'md'] as const;
export const ACCEPT = '.pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
export const MAX_ARQUIVO = 10 * 1024 * 1024;

/** Confere antes de enviar (o servidor confere de novo). */
export function problemaDoArquivo(nome: string, tamanho: number): string | null {
  const ext = nome.includes('.') ? nome.split('.').pop()!.toLowerCase() : '';
  if (!(TIPOS_ACEITOS as readonly string[]).includes(ext)) {
    return 'Use PDF, Word (.docx), .txt ou .md.';
  }
  if (tamanho > MAX_ARQUIVO) return 'Arquivo grande demais (até 10 MB).';
  if (tamanho === 0) return 'Arquivo vazio.';
  return null;
}

/** "12 mil caracteres", "850 caracteres". */
export function tamanhoTexto(caracteres: number): string {
  if (caracteres >= 1000) {
    const mil = caracteres / 1000;
    const txt = mil >= 10 ? Math.round(mil).toString() : mil.toFixed(1).replace('.', ',').replace(',0', '');
    return `${txt} mil caracteres`;
  }
  return `${caracteres} caracteres`;
}

/** Linha de detalhes do documento: "PDF · 12 páginas · 30 mil caracteres". */
export function detalhesDocumento(d: Pick<Documento, 'tipo' | 'paginas' | 'caracteres' | 'cortado'>): string {
  const partes = [d.tipo === 'docx' ? 'Word' : d.tipo.toUpperCase()];
  if (d.paginas) partes.push(d.paginas === 1 ? '1 página' : `${d.paginas} páginas`);
  partes.push(tamanhoTexto(d.caracteres));
  if (d.cortado) partes.push('guardado só o começo');
  return partes.join(' · ');
}

/** O documento é grande para ir inteiro em cada mensagem? */
export function vaiCortado(caracteres: number, anexados: number, noContexto = 30000): boolean {
  return caracteres > Math.floor(noContexto / Math.max(1, anexados));
}

export function listarDocumentos(espaco: string) {
  return edenJson<{ documentos: Documento[]; limites: LimitesDocumentos }>(
    `/documentos?espaco=${encodeURIComponent(espaco)}`,
  );
}

export function documentosDaConversa(conversaId: string) {
  return edenJson<{ documentos: Documento[] }>(`/documentos/conversa/${encodeURIComponent(conversaId)}`);
}

export function anexarDocumento(conversaId: string, id: number) {
  return edenJson<{ documentos: Documento[] }>(
    `/documentos/conversa/${encodeURIComponent(conversaId)}/${id}`,
    { method: 'PUT' },
  );
}

export function desanexarDocumento(conversaId: string, id: number) {
  return edenJson<{ documentos: Documento[] }>(
    `/documentos/conversa/${encodeURIComponent(conversaId)}/${id}`,
    { method: 'DELETE' },
  );
}

export function apagarDocumento(id: number) {
  return edenJson<{ ok: boolean }>(`/documentos/${id}`, { method: 'DELETE' });
}

/** Envia o arquivo cru (o nome vai codificado no cabeçalho). */
export async function enviarDocumento(espaco: string, arquivo: File): Promise<Documento> {
  const problema = problemaDoArquivo(arquivo.name, arquivo.size);
  if (problema) throw new ErroEden(problema, 400);
  const res = await apiFetch(`/v1/eden/documentos?espaco=${encodeURIComponent(espaco)}`, {
    method: 'POST',
    headers: {
      'Content-Type': arquivo.type || 'application/octet-stream',
      'X-Eden-Nome': encodeURIComponent(arquivo.name),
    },
    body: arquivo,
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detalhe = typeof data?.detail === 'string' ? data.detail : null;
    throw new ErroEden(detalhe ?? `O servidor recusou o arquivo (erro ${res.status}).`, res.status);
  }
  return data.documento as Documento;
}
