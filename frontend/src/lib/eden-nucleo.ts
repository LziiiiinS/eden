// Éden: o visual 3D — o "núcleo" (uma esfera de vidro com luz por dentro e
// anéis em volta) e o "horizonte" (um campo de pontos de luz no fundo de
// todas as páginas). Os dois mostram o que o Éden está fazendo: em repouso,
// ouvindo, pensando ou falando. Liga/desliga em Configurações → Aparência;
// fica guardado só neste aparelho.
import { create } from 'zustand';

export type EstadoNucleo = 'repouso' | 'ouvindo' | 'pensando' | 'falando';

const CHAVE = 'eden-nucleo-3d';

function lerAtivo(): boolean {
  try {
    return localStorage.getItem(CHAVE) !== 'nao';
  } catch {
    return true;
  }
}

interface NucleoStore {
  ativo: boolean;
  ouvindo: boolean;
  setAtivo: (ativo: boolean) => void;
  setOuvindo: (ouvindo: boolean) => void;
}

export const useNucleoStore = create<NucleoStore>((set) => ({
  ativo: lerAtivo(),
  ouvindo: false,
  setAtivo: (ativo) => {
    try {
      localStorage.setItem(CHAVE, ativo ? 'sim' : 'nao');
    } catch {
      // sem armazenamento (aba anônima): vale só até fechar
    }
    set({ ativo });
  },
  setOuvindo: (ouvindo) => set({ ouvindo }),
}));

/** O que o núcleo mostra, a partir do microfone, da voz e da resposta. */
export function estadoNucleo(p: {
  ouvindo: boolean;
  voz: 'idle' | 'loading' | 'speaking';
  respondendo: boolean;
}): EstadoNucleo {
  if (p.ouvindo) return 'ouvindo';
  if (p.voz === 'speaking') return 'falando';
  if (p.respondendo || p.voz === 'loading') return 'pensando';
  return 'repouso';
}

/**
 * Cada estado: cor (RGB 0–1), energia (0–1: quanto a superfície e o campo se
 * mexem), ritmo (velocidade das ondas no horizonte), giro (velocidade dos
 * anéis) e o texto para leitor de tela.
 */
export const VISUAL: Record<
  EstadoNucleo,
  { cor: [number, number, number]; energia: number; ritmo: number; giro: number; texto: string }
> = {
  repouso: { cor: [0.16, 0.72, 0.86], energia: 0.18, ritmo: 0.7, giro: 0.04, texto: 'Éden em repouso' },
  ouvindo: { cor: [0.22, 0.95, 0.62], energia: 0.62, ritmo: 2.4, giro: 0.1, texto: 'Éden ouvindo' },
  pensando: { cor: [0.56, 0.46, 1.0], energia: 0.45, ritmo: 1.3, giro: 0.32, texto: 'Éden pensando' },
  falando: { cor: [0.2, 0.82, 1.0], energia: 0.8, ritmo: 3.2, giro: 0.14, texto: 'Éden falando' },
};

/** A cor do estado em CSS (para o brilho do horizonte, que é CSS). */
export function corCss(estado: EstadoNucleo): string {
  const [r, g, b] = VISUAL[estado].cor.map((c) => Math.round(c * 255));
  return `rgb(${r}, ${g}, ${b})`;
}

/**
 * Quantos pontos o horizonte desenha e a largura do campo. Tela estreita
 * (celular) tem menos pontos num campo mais estreito: fica igual de bonito
 * e gasta menos bateria.
 */
export function gradeDoHorizonte(largura: number): { colunas: number; linhas: number; extensao: number } {
  if (largura < 700) return { colunas: 48, linhas: 44, extensao: 10 };
  if (largura < 1200) return { colunas: 80, linhas: 56, extensao: 15 };
  return { colunas: 96, linhas: 64, extensao: 18 };
}

/**
 * Tamanho do desenho do fundo em pixels: no máximo 1,5× a densidade da tela
 * e no máximo ~1,4 milhão de pixels (o campo é suave; mais que isso só gasta
 * bateria).
 */
export function resolucaoDoFundo(
  largura: number,
  altura: number,
  dpr: number,
): { w: number; h: number; escala: number } {
  let escala = Math.min(Math.max(dpr || 1, 1), 1.5);
  const maximo = 1_400_000;
  const pixels = largura * altura * escala * escala;
  if (pixels > maximo) escala *= Math.sqrt(maximo / pixels);
  return {
    w: Math.max(1, Math.round(largura * escala)),
    h: Math.max(1, Math.round(altura * escala)),
    escala,
  };
}

/** Quadros por segundo: mais quando o Éden está ativo, menos em repouso. */
export function quadrosPorSegundo(estado: EstadoNucleo): number {
  return estado === 'repouso' ? 20 : 30;
}
