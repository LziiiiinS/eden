// Éden (Parte 5): contas e impostos. O Éden só anota e avisa: não paga nada,
// não liga em banco e não emite nota.
import { hojeIso } from './eden-org';

export type TipoConta = 'pagar' | 'receber';
export type Repete = 'nao' | 'mensal' | 'anual';

export interface Conta {
  id: number;
  espaco: string;
  tipo: TipoConta;
  descricao: string;
  valor_centavos: number;
  vencimento: string;
  dia: number;
  repete: Repete;
  categoria: string;
  aviso_dias: number;
  pago_em: number | null;
  paga: boolean;
  notas: string;
  origem: string;
  criado_em: number;
  atualizado_em?: number;
  versao?: number;
  gerada_de?: number | null;
}

export interface ResumoContas {
  hoje: string;
  atrasadas: number;
  proximas_7_dias: number;
  a_pagar_no_mes: number;
  a_receber_no_mes: number;
  atrasado_a_pagar: number;
  pago_no_ano: number;
  recebido_no_ano: number;
}

/** 123456 → "R$ 1.234,56"; 0 → "sem valor". */
export function reais(centavos: number): string {
  if (!centavos) return 'sem valor';
  const inteiro = Math.floor(centavos / 100);
  const frac = String(centavos % 100).padStart(2, '0');
  const milhares = String(inteiro).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `R$ ${milhares},${frac}`;
}

/** Centavos → texto para o campo de valor ("1500,00"). */
export function valorParaCampo(centavos: number): string {
  if (!centavos) return '';
  return `${Math.floor(centavos / 100)},${String(centavos % 100).padStart(2, '0')}`;
}

function iso(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function ultimoDia(y: number, m: number): number {
  return new Date(y, m, 0).getDate();
}

/** Próxima data com o dia ``dia`` (hoje conta). Dia 31 vira o último dia dos
 * meses curtos. */
export function proximoDia(dia: number, hoje: string = hojeIso()): string {
  const [y, m, d] = hoje.split('-').map(Number);
  if (d <= Math.min(dia, ultimoDia(y, m))) return iso(y, m, Math.min(dia, ultimoDia(y, m)));
  const ny = m === 12 ? y + 1 : y;
  const nm = m === 12 ? 1 : m + 1;
  return iso(ny, nm, Math.min(dia, ultimoDia(ny, nm)));
}

/** Próxima data com dia/mês fixos (hoje conta). */
export function proximaData(mes: number, dia: number, hoje: string = hojeIso()): string {
  const y = Number(hoje.slice(0, 4));
  const esteAno = iso(y, mes, Math.min(dia, ultimoDia(y, mes)));
  return esteAno >= hoje ? esteAno : iso(y + 1, mes, Math.min(dia, ultimoDia(y + 1, mes)));
}

export interface Modelo {
  rotulo: string;
  descricao: string;
  tipo: TipoConta;
  repete: Repete;
  categoria: string;
  vencimento: (hoje?: string) => string;
  aviso_dias: number;
  dica: string;
}

// Prazos conhecidos do MEI. Os valores mudam todo ano (salário mínimo), por
// isso o modelo não traz valor: confira no Portal do Empreendedor.
export const MODELOS: Modelo[] = [
  {
    rotulo: 'DAS do MEI',
    descricao: 'DAS do MEI',
    tipo: 'pagar',
    repete: 'mensal',
    categoria: 'Impostos',
    vencimento: (hoje) => proximoDia(20, hoje),
    aviso_dias: 3,
    dica: 'Vence todo dia 20. Confira o valor do ano no Portal do Empreendedor.',
  },
  {
    rotulo: 'Declaração anual do MEI',
    descricao: 'Declaração anual do MEI (DASN-SIMEI)',
    tipo: 'pagar',
    repete: 'anual',
    categoria: 'Impostos',
    vencimento: (hoje) => proximaData(5, 31, hoje),
    aviso_dias: 15,
    dica: 'Prazo até 31 de maio, sem valor a pagar. Confira o prazo no Portal do Empreendedor.',
  },
];

export interface GruposContas {
  atrasadas: Conta[];
  semana: Conta[];
  depois: Conta[];
}

function somarDias(data: string, dias: number): string {
  const [y, m, d] = data.split('-').map(Number);
  const dt = new Date(y, m - 1, d + dias);
  return iso(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
}

export function agrupar(contas: Conta[], hoje: string = hojeIso()): GruposContas {
  const semana = somarDias(hoje, 7);
  return {
    atrasadas: contas.filter((c) => c.vencimento < hoje),
    semana: contas.filter((c) => c.vencimento >= hoje && c.vencimento <= semana),
    depois: contas.filter((c) => c.vencimento > semana),
  };
}

export function textoAviso(dias: number): string {
  if (dias < 0) return 'sem aviso';
  if (dias === 0) return 'aviso no dia';
  return dias === 1 ? 'aviso 1 dia antes' : `aviso ${dias} dias antes`;
}

export const TEXTO_REPETE: Record<Repete, string> = {
  nao: 'uma vez',
  mensal: 'todo mês',
  anual: 'todo ano',
};
