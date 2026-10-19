// Éden: o estado do Éden visto de qualquer página (para o núcleo e o fundo
// 3D): o microfone, a voz e a resposta que está chegando.
import { useAppStore } from './store';
import { useEdenVozStore } from './eden-voz';
import { estadoNucleo, useNucleoStore, type EstadoNucleo } from './eden-nucleo';

export function useEstadoEden(): EstadoNucleo {
  const ouvindo = useNucleoStore((s) => s.ouvindo);
  const voz = useEdenVozStore((s) => s.state);
  const respondendo = useAppStore((s) => s.streamState.isStreaming);
  return estadoNucleo({ ouvindo, voz, respondendo });
}
