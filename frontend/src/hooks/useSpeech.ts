import { useState, useCallback, useRef, useEffect } from 'react';
import { transcribeAudio, fetchSpeechHealth } from '../lib/api';

export type SpeechState = 'idle' | 'recording' | 'transcribing';

// Éden: formatos que a transcrição aceita (webm, mp4/m4a, mp3, wav), em ordem
// de preferência. O iPhone (Safari) grava em mp4; Chrome/Android, em webm.
// Antes o app sempre enviava "recording.webm", e o servidor tratava o áudio do
// iPhone como webm.
const PREFERRED_RECORDING_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
];

/** Éden: escolhe um formato de gravação que o navegador suporta e a transcrição aceita. */
export function pickRecordingMimeType(
  isSupported: (type: string) => boolean = (type) =>
    typeof MediaRecorder !== 'undefined' &&
    typeof MediaRecorder.isTypeSupported === 'function' &&
    MediaRecorder.isTypeSupported(type),
): string | undefined {
  return PREFERRED_RECORDING_TYPES.find((type) => {
    try {
      return isSupported(type);
    } catch {
      return false;
    }
  });
}

/** Éden: nome do arquivo com a extensão certa para o tipo de áudio gravado. */
export const MSG_SEM_CONEXAO =
  'A conexão com o Éden caiu enquanto o áudio era enviado. Confira se o Tailscale está ligado no celular e tente de novo.';

/** Erro de rede do navegador (no iPhone: "Load failed"), sem resposta do servidor. */
export function erroDeRede(err: unknown): boolean {
  return err instanceof TypeError;
}

/** Envia o áudio; se a conexão cair no meio, tenta mais uma vez. */
export async function enviarComNovaTentativa(
  blob: Blob,
  nome: string,
  durationMs?: number,
  enviar: typeof transcribeAudio = transcribeAudio,
  esperarMs = 1500,
): Promise<{ text: string }> {
  try {
    return await enviar(blob, nome, durationMs);
  } catch (err) {
    if (!erroDeRede(err)) throw err;
  }
  await new Promise((r) => setTimeout(r, esperarMs));
  try {
    return await enviar(blob, nome, durationMs);
  } catch (err) {
    if (erroDeRede(err)) throw new Error(MSG_SEM_CONEXAO);
    throw err;
  }
}

export function audioFilenameFor(mimeType: string): string {
  const type = (mimeType || '').toLowerCase();
  if (type.includes('mp4') || type.includes('m4a') || type.includes('aac')) return 'recording.mp4';
  if (type.includes('mpeg') || type.includes('mp3')) return 'recording.mp3';
  if (type.includes('wav')) return 'recording.wav';
  if (type.includes('ogg')) return 'recording.ogg';
  return 'recording.webm';
}

export function useSpeech() {
  const [state, setState] = useState<SpeechState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number | null>(null);

  // Check if speech backend is available on mount
  useEffect(() => {
    fetchSpeechHealth()
      .then((health) => setAvailable(health.available))
      .catch(() => setAvailable(false));
  }, []);

  const startRecording = useCallback(async (): Promise<void> => {
    setError(null);

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('Este navegador não permite gravar áudio.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = pickRecordingMimeType();
      // Éden: 32 kbit/s basta para voz e deixa o envio pequeno (rede fraca
      // ou 4G pelo Tailscale cortava o envio de áudios grandes).
      const opcoes: MediaRecorderOptions = { audioBitsPerSecond: 32_000 };
      if (mimeType) opcoes.mimeType = mimeType;
      let recorder: MediaRecorder;
      try {
        recorder = new MediaRecorder(stream, opcoes);
      } catch {
        recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      }
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      startedAtRef.current = Date.now();
      mediaRecorderRef.current = recorder;
      setState('recording');
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setError('Não foi possível usar o microfone. Libere o acesso ao microfone nas configurações do navegador.');
      setState('idle');
    }
  }, []);

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state !== 'recording') {
        reject(new Error('Not recording'));
        return;
      }

      recorder.onstop = async () => {
        setState('transcribing');

        // Stop all audio tracks
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        chunksRef.current = [];

        if (blob.size === 0) {
          setState('idle');
          const msg = 'Não gravei nada. Toque no microfone e fale de novo.';
          setError(msg);
          reject(new Error(msg));
          return;
        }

        try {
          const durationMs = startedAtRef.current ? Date.now() - startedAtRef.current : undefined;
          const result = await enviarComNovaTentativa(blob, audioFilenameFor(blob.type), durationMs);
          setState('idle');
          resolve(result.text);
        } catch (err) {
          setState('idle');
          const msg = err instanceof Error ? err.message : 'Falha na transcrição do áudio.';
          setError(msg);
          reject(err);
        }
      };

      recorder.stop();
    });
  }, []);

  return {
    state,
    error,
    available,
    startRecording,
    stopRecording,
    isRecording: state === 'recording',
    isTranscribing: state === 'transcribing',
  };
}
