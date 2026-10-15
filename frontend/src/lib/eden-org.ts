// Éden (Parte 2): organização pessoal — espaços, perfil, memórias, tarefas,
// notas e as ações que o Éden sugere. Tudo fica no servidor (/v1/eden/...);
// esta parte só busca, mostra e manda o que a pessoa fez na tela.
import { create } from 'zustand';
import { apiFetch } from './api';

export interface Espaco {
  id: string;
  nome: string;
  descricao: string;
  ordem: number;
  arquivado: boolean;
}

export interface Memoria {
  id: number;
  espaco: string | null;
  texto: string;
  origem: 'voce' | 'eden';
  criado_em: number;
  atualizado_em: number;
}

export interface Tarefa {
  id: number;
  espaco: string;
  titulo: string;
  notas: string;
  data: string | null;
  hora: string | null;
  lembrete_em: number | null;
  lembrete_enviado_em: number | null;
  feita: boolean;
  feita_em: number | null;
  origem: 'voce' | 'eden';
  criado_em: number;
  atualizado_em: number;
}

export interface Nota {
  id: number;
  espaco: string;
  tipo: 'nota' | 'ideia';
  titulo: string;
  texto: string;
  fixada: boolean;
  origem: 'voce' | 'eden';
  criado_em: number;
  atualizado_em: number;
}

export type EstadoAcao = 'pendente' | 'feita' | 'recusada' | 'expirada' | 'falhou';

export interface Acao {
  id: string;
  tipo: string;
  parametros: Record<string, unknown>;
  assinatura: string;
  resumo: string;
  estado: EstadoAcao;
  criado_em: number;
  expira_em: number;
  decidido_em: number | null;
  resultado: Record<string, unknown> | null;
}

export interface ResumoHoje {
  data: string;
  agora: number;
  atrasadas: Tarefa[];
  hoje: Tarefa[];
  proximas: Tarefa[];
  sem_data: Tarefa[];
  feitas_hoje: Tarefa[];
  notas_fixadas: Nota[];
}

/** Erro do servidor com a mensagem em português (campo "detail"). */
export class ErroEden extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function edenJson<T>(
  path: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await apiFetch(`/v1/eden${path}`, {
    method: init.method ?? 'GET',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : undefined;
    const msg =
      detail ??
      (res.status === 401
        ? 'Chave de acesso do servidor inválida.'
        : `O servidor recusou (erro ${res.status}).`);
    throw new ErroEden(msg, res.status, typeof data?.code === 'string' ? data.code : undefined);
  }
  return data as T;
}

// ── espaço ativo ────────────────────────────────────────────────────────────

const ESPACO_KEY = 'eden-espaco-ativo';

function lerEspacoSalvo(): string {
  try {
    return localStorage.getItem(ESPACO_KEY) || 'pessoal';
  } catch {
    return 'pessoal';
  }
}

interface EdenOrgState {
  espacos: Espaco[];
  espacoAtivo: string;
  carregado: boolean;
  setEspacoAtivo: (id: string) => void;
  carregarEspacos: () => Promise<void>;
}

export const useEdenOrg = create<EdenOrgState>((set, get) => ({
  espacos: [],
  espacoAtivo: lerEspacoSalvo(),
  carregado: false,
  setEspacoAtivo: (id: string) => {
    try {
      localStorage.setItem(ESPACO_KEY, id);
    } catch {
      // Melhor esforço.
    }
    set({ espacoAtivo: id });
  },
  carregarEspacos: async () => {
    try {
      const data = await edenJson<{ espacos: Espaco[] }>('/espacos');
      const espacos = data.espacos;
      const ativo = get().espacoAtivo;
      set({ espacos, carregado: true });
      if (espacos.length > 0 && !espacos.some((e) => e.id === ativo)) {
        get().setEspacoAtivo(espacos[0].id);
      }
    } catch {
      set({ carregado: true });
    }
  },
}));

export function nomeEspaco(espacos: Espaco[], id: string | null): string {
  if (id === null) return 'Todos os espaços';
  return espacos.find((e) => e.id === id)?.nome ?? id;
}

// ── datas ──────────────────────────────────────────────────────────────────

const DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

/** Data local do aparelho em AAAA-MM-DD. */
export function hojeIso(agora: Date = new Date()): string {
  const y = agora.getFullYear();
  const m = String(agora.getMonth() + 1).padStart(2, '0');
  const d = String(agora.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function somarDias(iso: string, dias: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d + dias);
  return hojeIso(dt);
}

/** "hoje 18:00", "amanhã", "sex 17/10", "02/01/2027", "sem data". */
export function textoData(data: string | null, hora: string | null, hoje: string = hojeIso()): string {
  if (!data) return 'sem data';
  let txt: string;
  if (data === hoje) txt = 'hoje';
  else if (data === somarDias(hoje, 1)) txt = 'amanhã';
  else if (data === somarDias(hoje, -1)) txt = 'ontem';
  else {
    const [y, m, d] = data.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    const mesmoAno = y === Number(hoje.slice(0, 4));
    txt = mesmoAno
      ? `${DIAS[dt.getDay()]} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`
      : `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`;
  }
  return hora ? `${txt} ${hora}` : txt;
}

export function atrasada(t: Pick<Tarefa, 'data' | 'feita'>, hoje: string = hojeIso()): boolean {
  return !t.feita && !!t.data && t.data < hoje;
}

/** Hora local "HH:MM" de um momento em milissegundos. */
export function horaDe(ms: number): string {
  const dt = new Date(ms);
  return `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
}
