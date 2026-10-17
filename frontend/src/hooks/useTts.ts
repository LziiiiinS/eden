import { useEffect } from 'react';
import { useTtsStore } from '../lib/tts';
import { useEdenVozStore } from '../lib/eden-voz';
import { useAppStore } from '../lib/store';
import { isEdenModel } from '../lib/eden-ai';

export type { TtsState } from '../lib/tts';

/**
 * Read-aloud controls backed by the shared voice-output store.
 *
 * Every consumer talks to the same utterance, so starting one reply stops the
 * previous one instead of layering on top of it. The health probe runs once per
 * document, no matter how many components mount this hook.
 */
export function useTts() {
  // Éden: no servidor do Éden, a voz vem da OpenAI pelo servidor (com limite
  // de gastos) e toca também no iPhone (lib/eden-voz.ts).
  const eden = useAppStore((s) => s.models.some((m) => isEdenModel(m.id)));
  const base = {
    state: useTtsStore((s) => s.state),
    speakingId: useTtsStore((s) => s.speakingId),
    error: useTtsStore((s) => s.error),
    errorId: useTtsStore((s) => s.errorId),
    available: useTtsStore((s) => s.available),
    speak: useTtsStore((s) => s.speak),
    stop: useTtsStore((s) => s.stop),
    ensureHealth: useTtsStore((s) => s.ensureHealth),
  };
  const voz = {
    state: useEdenVozStore((s) => s.state),
    speakingId: useEdenVozStore((s) => s.speakingId),
    error: useEdenVozStore((s) => s.error),
    errorId: useEdenVozStore((s) => s.errorId),
    available: useEdenVozStore((s) => s.available),
    speak: useEdenVozStore((s) => s.speak),
    stop: useEdenVozStore((s) => s.stop),
    ensureHealth: useEdenVozStore((s) => s.ensureHealth),
  };
  const { state, speakingId, error, errorId, available, speak, stop, ensureHealth } = eden ? voz : base;

  useEffect(() => {
    ensureHealth();
  }, [ensureHealth]);

  return {
    state,
    speakingId,
    error,
    errorId,
    available: available === true,
    speak,
    stop,
    isLoading: state === 'loading',
    isSpeaking: state === 'speaking',
  };
}
