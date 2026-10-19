// Éden: o "núcleo" 3D — uma esfera animada que mostra o que o Éden está
// fazendo (em repouso, ouvindo, pensando, falando). Liga/desliga em
// Configurações → Aparência; fica guardado só neste aparelho.
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

/** Cor (RGB 0–1) e energia (0–1: quanto a superfície se mexe) de cada estado. */
export const VISUAL: Record<EstadoNucleo, { cor: [number, number, number]; energia: number; texto: string }> = {
  repouso: { cor: [0.16, 0.72, 0.86], energia: 0.18, texto: 'Éden em repouso' },
  ouvindo: { cor: [0.22, 0.95, 0.62], energia: 0.62, texto: 'Éden ouvindo' },
  pensando: { cor: [0.56, 0.46, 1.0], energia: 0.45, texto: 'Éden pensando' },
  falando: { cor: [0.2, 0.82, 1.0], energia: 0.8, texto: 'Éden falando' },
};
