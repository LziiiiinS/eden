// Éden (Parte 5): e-mail (Gmail) só para ler, pelo servidor.
import { edenJson } from './eden-org';
import type { Documento } from './eden-documentos';

export interface ResumoEmail {
  id: string;
  de: { nome: string; email: string };
  assunto: string;
  trecho: string;
  recebido_em: number;
  nao_lido: boolean;
}

export interface Email extends ResumoEmail {
  texto: string;
}

export interface StatusEmail {
  configurado: boolean;
  conectado: boolean;
  conta: string | null;
}

/** "Ana" ou "ana@cliente.com". */
export function remetente(e: ResumoEmail): string {
  return e.de.nome || e.de.email || 'Desconhecido';
}

/** "hoje 14:05", "16/10". */
export function quando(ms: number, agora = new Date()): string {
  if (!ms) return '';
  const d = new Date(ms);
  if (d.toDateString() === agora.toDateString()) {
    return `hoje ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** Mensagem da volta do Google (?email=…) nas Configurações. */
export function mensagemDaVoltaEmail(situacao: string | null): string | null {
  switch (situacao) {
    case 'conectado':
      return 'E-mail conectado (só leitura).';
    case 'negado':
      return 'Você não autorizou no Google. Nada foi ligado.';
    case 'sem-permissao':
      return 'A permissão de ler os e-mails não foi marcada. Tente de novo e marque a caixa.';
    case 'expirou':
      return 'O pedido expirou. Toque em Conectar de novo.';
    case 'erro':
      return 'Não deu para conectar agora. Tente de novo.';
    default:
      return null;
  }
}

export const statusEmail = () => edenJson<StatusEmail>('/email/status');
export const urlConectarEmail = async () => (await edenJson<{ url: string }>('/email/conectar', { method: 'POST' })).url;
export const desconectarEmail = () => edenJson<{ ok: boolean; revogado: boolean }>('/email/desconectar', { method: 'POST' });
export const listarEmails = (busca = '', atualizar = false) =>
  edenJson<{ conectado: boolean; mensagens: ResumoEmail[]; aviso?: string }>(
    `/email/mensagens?busca=${encodeURIComponent(busca)}${atualizar ? '&atualizar=true' : ''}`,
  );
export const lerEmail = (id: string) => edenJson<{ mensagem: Email }>(`/email/mensagens/${encodeURIComponent(id)}`);
export const importarEmail = (espaco: string, id: string) =>
  edenJson<{ documento: Documento }>('/email/importar', { method: 'POST', body: { espaco, id } });
