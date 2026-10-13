// Éden: testes do formato de gravação e do nome do arquivo de áudio.
import { describe, expect, it, vi } from 'vitest';

vi.mock('../lib/api', () => ({
  transcribeAudio: vi.fn(),
  fetchSpeechHealth: vi.fn(),
}));

import { audioFilenameFor, pickRecordingMimeType } from './useSpeech';

describe('audioFilenameFor', () => {
  it('names iPhone (Safari) recordings as mp4', () => {
    expect(audioFilenameFor('audio/mp4')).toBe('recording.mp4');
    expect(audioFilenameFor('audio/mp4;codecs=mp4a.40.2')).toBe('recording.mp4');
  });

  it('names Chrome/Android recordings as webm', () => {
    expect(audioFilenameFor('audio/webm;codecs=opus')).toBe('recording.webm');
  });

  it('keeps other known types', () => {
    expect(audioFilenameFor('audio/mpeg')).toBe('recording.mp3');
    expect(audioFilenameFor('audio/wav')).toBe('recording.wav');
    expect(audioFilenameFor('audio/ogg;codecs=opus')).toBe('recording.ogg');
  });

  it('falls back to webm when the type is empty', () => {
    expect(audioFilenameFor('')).toBe('recording.webm');
  });
});

describe('pickRecordingMimeType', () => {
  it('prefers webm/opus when supported', () => {
    expect(pickRecordingMimeType(() => true)).toBe('audio/webm;codecs=opus');
  });

  it('picks mp4 when only mp4 is supported (iPhone)', () => {
    expect(pickRecordingMimeType((t) => t === 'audio/mp4')).toBe('audio/mp4');
  });

  it('returns undefined when nothing is supported', () => {
    expect(pickRecordingMimeType(() => false)).toBeUndefined();
  });

  it('treats a throwing check as unsupported', () => {
    expect(
      pickRecordingMimeType((t) => {
        if (t.startsWith('audio/webm')) throw new Error('boom');
        return t === 'audio/mp4';
      }),
    ).toBe('audio/mp4');
  });
});
