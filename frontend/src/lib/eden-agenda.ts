// Éden (Parte 3): Google Agenda — estado da ligação e eventos do dia.
import { edenJson } from './eden-org';

export interface EventoAgenda {
  id: string;
  titulo: string;
  local: string;
  inicio: string;
  fim: string | null;
  dia_inteiro: boolean;
}

export interface StatusAgenda {
  configurado: boolean;
  conectado: boolean;
  endereco_retorno: string | null;
  atualizado_em: number | null;
}

export function statusAgenda(): Promise<StatusAgenda> {
  return edenJson<StatusAgenda>('/google/status');
}

export async function urlParaConectar(): Promise<string> {
  const { url } = await edenJson<{ url: string }>('/google/conectar', { method: 'POST' });
  // Só segue para o endereço de autorização do próprio Google.
  const destino = new URL(url);
  if (destino.protocol !== 'https:' || destino.hostname !== 'accounts.google.com') {
    throw new Error('Endereço de autorização inesperado.');
  }
  return destino.toString();
}

export function desconectarAgenda(): Promise<{ ok: boolean }> {
  return edenJson('/google/desconectar', { method: 'POST' });
}

export function eventosDoDia(): Promise<{ conectado: boolean; eventos: EventoAgenda[]; aviso?: string }> {
  return edenJson('/google/eventos?dias=1');
}

/** "14:00–15:30", "o dia todo". */
export function horarioEvento(e: Pick<EventoAgenda, 'inicio' | 'fim' | 'dia_inteiro'>): string {
  if (e.dia_inteiro) return 'o dia todo';
  const hora = (iso: string) => {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  };
  return e.fim ? `${hora(e.inicio)}–${hora(e.fim)}` : hora(e.inicio);
}

/** Mensagem para o resultado da volta do Google (/settings?google=…). */
export function mensagemDaVolta(situacao: string | null): { texto: string; ok: boolean } | null {
  switch (situacao) {
    case 'conectado':
      return { texto: 'Google Agenda conectada.', ok: true };
    case 'negado':
      return { texto: 'A ligação foi cancelada na tela do Google.', ok: false };
    case 'expirou':
      return { texto: 'O pedido de ligação expirou. Toque em Conectar de novo.', ok: false };
    case 'sem-permissao':
      return { texto: 'Faltou marcar a permissão da agenda na tela do Google. Tente de novo.', ok: false };
    case 'erro':
      return { texto: 'Não deu para concluir a ligação com o Google. Tente de novo.', ok: false };
    default:
      return null;
  }
}
