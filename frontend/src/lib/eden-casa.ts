// Éden: casa (luzes, tomadas, ar-condicionado e rotinas) pelo Home Assistant.
// O endereço e o token do Home Assistant ficam só no servidor; o app só vê a
// lista de aparelhos que o Éden pode mexer.
import { edenJson } from './eden-org';

export type DominioCasa = 'light' | 'switch' | 'climate' | 'scene' | 'button';

export interface AparelhoCasa {
  entidade: string;
  nome: string;
  dominio: DominioCasa;
  acoes: string[];
}

export interface PassoCasa {
  entidade: string;
  acao: string;
  valor?: number | string;
}

export interface RotinaCasa {
  id: number;
  nome: string;
  passos: PassoCasa[];
  atualizado_em: number;
}

export interface SituacaoCasa {
  ligada: boolean;
  demo: boolean;
  aparelhos: AparelhoCasa[];
  cores: string[];
  rotinas: RotinaCasa[];
}

export interface EstadoAparelho {
  entidade: string;
  estado: string | null;
  temperatura?: number;
  erro?: string;
}

export interface FeitoCasa {
  feitos: string[];
  demo: boolean;
  rotina?: number;
}

export const NOME_ACAO: Record<string, string> = {
  ligar: 'Ligar',
  desligar: 'Desligar',
  cor: 'Cor',
  brilho: 'Brilho',
  temperatura: 'Temperatura',
  ativar: 'Ativar',
  apertar: 'Apertar',
};

/** Ações que levam um valor (e o valor inicial sugerido). */
export function valorPadrao(acao: string, cores: string[] = []): number | string | undefined {
  if (acao === 'temperatura') return 22;
  if (acao === 'brilho') return 70;
  if (acao === 'cor') return cores[0] ?? 'branca';
  return undefined;
}

/** O passo está completo? (mesmas regras do servidor) */
export function passoValido(p: PassoCasa, aparelhos: AparelhoCasa[], cores: string[]): boolean {
  const a = aparelhos.find((x) => x.entidade === p.entidade);
  if (!a || !a.acoes.includes(p.acao)) return false;
  if (p.acao === 'temperatura') return Number.isInteger(p.valor) && Number(p.valor) >= 16 && Number(p.valor) <= 30;
  if (p.acao === 'brilho') return Number.isInteger(p.valor) && Number(p.valor) >= 1 && Number(p.valor) <= 100;
  if (p.acao === 'cor') return typeof p.valor === 'string' && cores.includes(p.valor);
  return p.valor === undefined || p.valor === '';
}

/** "Luz da sala → cor azul" (igual ao cartão do servidor). */
export function textoPasso(p: PassoCasa, aparelhos: AparelhoCasa[]): string {
  const nome = aparelhos.find((a) => a.entidade === p.entidade)?.nome ?? p.entidade;
  if (p.acao === 'temperatura') return `${nome} → ${p.valor} °C`;
  if (p.acao === 'brilho') return `${nome} → brilho ${p.valor}%`;
  if (p.acao === 'cor') return `${nome} → cor ${p.valor}`;
  return `${nome} → ${p.acao}`;
}

/** Só o que o servidor aceita (tira o valor de quem não leva). */
export function limparPasso(p: PassoCasa): PassoCasa {
  const leva = p.acao === 'temperatura' || p.acao === 'brilho' || p.acao === 'cor';
  return leva ? { entidade: p.entidade, acao: p.acao, valor: p.valor } : { entidade: p.entidade, acao: p.acao };
}

export const lerCasa = () => edenJson<SituacaoCasa>('/casa');

export const lerEstados = () => edenJson<{ estados: EstadoAparelho[] }>('/casa/estados');

export const comandar = (p: PassoCasa) =>
  edenJson<FeitoCasa>('/casa/aparelho', { method: 'POST', body: limparPasso(p) });

export const salvarRotina = (dados: { nome: string; passos: PassoCasa[] }, id?: number) =>
  edenJson<{ rotina: RotinaCasa }>(id ? `/casa/rotinas/${id}` : '/casa/rotinas', {
    method: id ? 'PATCH' : 'POST',
    body: { nome: dados.nome, passos: dados.passos.map(limparPasso) },
  });

export const apagarRotina = (id: number) =>
  edenJson<{ ok: boolean }>(`/casa/rotinas/${id}`, { method: 'DELETE' });

export const rodarRotina = (id: number) =>
  edenJson<FeitoCasa>(`/casa/rotinas/${id}/rodar`, { method: 'POST' });
