// Éden (Parte 2): ações que o Éden sugere na conversa.
//
// O Éden escreve as sugestões em blocos ```eden-acao {...}``` no fim da
// resposta. O servidor lê esses blocos, guarda cada sugestão como "ação
// pendente" e manda ao app (evento eden_acoes) o resumo e a assinatura. O app
// esconde os blocos e mostra um cartão com Confirmar / Recusar. Confirmar
// manda só o id e a assinatura: o servidor executa o que ELE guardou.
import type { EstadoAcao } from './eden-org';

/** O que fica guardado na mensagem (e sincroniza entre aparelhos). */
export interface EdenActionRef {
  id: string;
  tipo: string;
  resumo: string;
  assinatura: string;
  estado: EstadoAcao;
  expira_em: number;
}

const BLOCO = /```[ \t]*eden-acao[ \t]*\r?\n[\s\S]*?```/g;
// Bloco aberto que ainda não fechou (durante o streaming ou resposta cortada).
const BLOCO_ABERTO = /```[ \t]*eden-acao\b[\s\S]*$/;

/** Texto da resposta sem os blocos de ação (o que a pessoa vê). */
export function removeActionBlocks(text: string): string {
  if (!text.includes('eden-acao')) return text;
  return text
    .replace(BLOCO, '')
    .replace(BLOCO_ABERTO, '')
    .replace(/\n{3,}/g, '\n\n')
    .trimEnd();
}

/** Lê o evento eden_acoes do streaming. */
export function parseActionsEvent(data: string): { acoes: EdenActionRef[]; recusadas: string[] } {
  try {
    const raw = JSON.parse(data);
    const acoes: EdenActionRef[] = Array.isArray(raw?.acoes)
      ? raw.acoes
          .filter((a: any) => a && typeof a.id === 'string' && typeof a.resumo === 'string')
          .map((a: any) => ({
            id: a.id,
            tipo: String(a.tipo ?? ''),
            resumo: a.resumo,
            assinatura: String(a.assinatura ?? ''),
            estado: (a.estado ?? 'pendente') as EstadoAcao,
            expira_em: Number(a.expira_em ?? 0),
          }))
      : [];
    const recusadas: string[] = Array.isArray(raw?.recusadas)
      ? raw.recusadas.filter((r: unknown) => typeof r === 'string')
      : [];
    return { acoes, recusadas };
  } catch {
    return { acoes: [], recusadas: [] };
  }
}

/** Estado que o cartão mostra (a pendente que passou da validade vira expirada). */
export function visibleState(ref: Pick<EdenActionRef, 'estado' | 'expira_em'>, now: number = Date.now()): EstadoAcao {
  if (ref.estado === 'pendente' && ref.expira_em > 0 && ref.expira_em <= now) return 'expirada';
  return ref.estado;
}
