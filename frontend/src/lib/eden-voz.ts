// Éden (Parte 4): respostas em voz, com a voz da OpenAI (pelo servidor, que
// confere o limite de gastos). Funciona no iPhone: o áudio é "destravado" no
// toque de enviar ou do microfone, e depois o mesmo elemento de áudio toca as
// respostas (o Safari só deixa tocar sozinho um áudio que já tocou com toque).
//
// A resposta vira texto de fala (sem markdown, links, código ou fontes), é
// dividida em pedaços e cada pedaço toca assim que fica pronto, enquanto o
// próximo é gerado.
import { create } from 'zustand';
import { apiFetch } from './api';

export type EstadoVoz = 'idle' | 'loading' | 'speaking';

/** Tamanho máximo falado de uma resposta; o resto fica na tela. */
export const MAX_FALA = 1500;
const PRIMEIRO_PEDACO = 220;
const PEDACO = 600;

// ── texto para fala ──────────────────────────────────────────────────────

/** Markdown da resposta → texto bom de ouvir. */
export function textoParaFala(md: string): string {
  let t = md.replace(/\r\n?/g, '\n');
  // Blocos de ação (já viram cartões) e de código.
  t = t.replace(/```eden[-‑]acao[\s\S]*?(```|$)/gi, '');
  t = t.replace(/```[\s\S]*?(```|$)/g, ' (tem um trecho de código na tela) ');
  // "Fontes:" da pesquisa e tudo depois.
  t = t.replace(/\n\s*\**Fontes:?\**\s*\n[\s\S]*$/i, '');
  // Tabelas: só avisa.
  t = t.replace(/(^\|.*\|\s*$\n?)+/gm, ' (tem uma tabela na tela) ');
  // Imagens e links: fica o texto.
  t = t.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  t = t.replace(/https?:\/\/\S+/g, '');
  // Marcas de markdown.
  t = t.replace(/^\s{0,3}#{1,6}\s+/gm, '');
  t = t.replace(/^\s*>\s?/gm, '');
  t = t.replace(/^\s*[-*+]\s+/gm, '');
  t = t.replace(/^\s*(\d+)[.)]\s+/gm, '$1. ');
  t = t.replace(/(\*\*|__|\*|_|~~|`)/g, '');
  // Emojis e símbolos que a voz leria por extenso.
  t = t.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{200D}]/gu, '');
  // Linhas viram pausas.
  t = t
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => (/[.!?:;…]$/.test(l) ? l : `${l}.`))
    .join(' ');
  return t.replace(/\s+/g, ' ').replace(/\s+([.,!?;:])/g, '$1').trim();
}

/** Divide em pedaços que terminam em fim de frase (o primeiro é curto, para
 * começar a falar logo). Respostas longas param em MAX_FALA. */
export function dividirParaFala(texto: string): string[] {
  let resto = texto.trim();
  let cortado = false;
  if (resto.length > MAX_FALA) {
    const corte = resto.lastIndexOf('. ', MAX_FALA);
    resto = resto.slice(0, corte > MAX_FALA / 2 ? corte + 1 : MAX_FALA).trim();
    cortado = true;
  }
  const pedacos: string[] = [];
  while (resto) {
    const limite = pedacos.length === 0 ? PRIMEIRO_PEDACO : PEDACO;
    if (resto.length <= limite) {
      pedacos.push(resto);
      break;
    }
    const janela = resto.slice(0, limite);
    let fim = Math.max(janela.lastIndexOf('. '), janela.lastIndexOf('! '), janela.lastIndexOf('? '));
    if (fim < limite / 3) fim = janela.lastIndexOf(', ');
    if (fim < limite / 3) fim = janela.lastIndexOf(' ');
    if (fim <= 0) fim = limite - 1;
    pedacos.push(resto.slice(0, fim + 1).trim());
    resto = resto.slice(fim + 1).trim();
  }
  if (cortado) pedacos.push('O resto está na tela.');
  return pedacos.filter(Boolean);
}

// ── escolha da voz (neste aparelho) ──────────────────────────────────────

export const VOZES: Array<{ id: string; nome: string }> = [
  { id: 'marin', nome: 'Marin (feminina, natural)' },
  { id: 'cedar', nome: 'Cedar (masculina, natural)' },
  { id: 'coral', nome: 'Coral (feminina)' },
  { id: 'ash', nome: 'Ash (masculina)' },
  { id: 'nova', nome: 'Nova (feminina)' },
  { id: 'onyx', nome: 'Onyx (masculina, grave)' },
  { id: 'sage', nome: 'Sage (calma)' },
];
const CHAVE_VOZ = 'eden.voz.nome';

export function vozEscolhida(): string {
  try {
    const v = window.localStorage.getItem(CHAVE_VOZ);
    return v && VOZES.some((x) => x.id === v) ? v : 'marin';
  } catch {
    return 'marin';
  }
}

export function definirVoz(id: string): void {
  try {
    window.localStorage.setItem(CHAVE_VOZ, id);
  } catch {
    // sem armazenamento: fica a voz padrão
  }
}

// ── tocador (um só para o app inteiro) ──────────────────────────────────

let elemento: HTMLAudioElement | null = null;
let urlAtual: string | null = null;
let controle: AbortController | null = null;
let vez = 0;
let sonda: Promise<void> | null = null;
// Termina o pedaço que está tocando (para o laço não ficar esperando à toa).
let terminarAtual: ((fim: 'fim' | 'pausa') => void) | null = null;

function audio(): HTMLAudioElement {
  if (!elemento) {
    elemento = new Audio();
    elemento.preload = 'auto';
  }
  return elemento;
}

/** WAV de silêncio (0,1 s), como blob (a regra de segurança aceita blob:). */
function silencio(): string {
  const taxa = 8000;
  const amostras = taxa / 10;
  const buf = new ArrayBuffer(44 + amostras);
  const v = new DataView(buf);
  const escreve = (o: number, s: string) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  escreve(0, 'RIFF');
  v.setUint32(4, 36 + amostras, true);
  escreve(8, 'WAVEfmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, taxa, true);
  v.setUint32(28, taxa, true);
  v.setUint16(32, 1, true);
  v.setUint16(34, 8, true);
  escreve(36, 'data');
  v.setUint32(40, amostras, true);
  for (let i = 0; i < amostras; i++) v.setUint8(44 + i, 128);
  return URL.createObjectURL(new Blob([buf], { type: 'audio/wav' }));
}

/** Chame dentro de um toque (enviar, microfone): no iPhone, só um áudio que
 * já tocou com toque pode tocar depois sozinho. */
export function desbloquearAudio(): void {
  try {
    const el = audio();
    if (useEdenVozStore.getState().state !== 'idle') return;
    const url = silencio();
    el.src = url;
    const p = el.play();
    if (p && typeof p.then === 'function') {
      p.then(() => {
        // Só pausa se ainda for o silêncio (uma resposta pode já estar tocando).
        if (el.src === url) el.pause();
      })
        .catch(() => {})
        .finally(() => URL.revokeObjectURL(url));
    }
  } catch {
    // navegador sem áudio: as respostas ficam só em texto
  }
}

function soltar(): void {
  if (elemento) {
    elemento.onended = null;
    elemento.onerror = null;
    elemento.onpause = null;
    elemento.pause();
  }
  const terminar = terminarAtual;
  terminarAtual = null;
  terminar?.('pausa');
  if (urlAtual) {
    URL.revokeObjectURL(urlAtual);
    urlAtual = null;
  }
  if (controle) {
    controle.abort();
    controle = null;
  }
}

async function sintetizar(texto: string, signal: AbortSignal): Promise<Blob> {
  const res = await apiFetch('/v1/eden/voz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ texto, voz: vozEscolhida() }),
    signal,
  });
  if (!res.ok) {
    let detalhe = '';
    try {
      const corpo = await res.json();
      detalhe = typeof corpo?.detail === 'string' ? corpo.detail : '';
    } catch {
      // sem corpo JSON
    }
    throw new Error(detalhe || `A voz falhou (erro ${res.status}).`);
  }
  return res.blob();
}

/** Toca um pedaço. 'pausa' = o aparelho parou o som (ligação, Siri, app em
 * segundo plano) ou a pessoa parou: aí a fala para de vez. */
function tocar(blob: Blob, minha: number): Promise<'fim' | 'pausa'> {
  return new Promise((resolve, reject) => {
    if (minha !== vez) {
      resolve('pausa');
      return;
    }
    const el = audio();
    if (urlAtual) URL.revokeObjectURL(urlAtual);
    urlAtual = URL.createObjectURL(blob);
    terminarAtual = resolve;
    el.onended = () => {
      terminarAtual = null;
      resolve('fim');
    };
    el.onpause = () => {
      if (!el.ended) {
        terminarAtual = null;
        resolve('pausa');
      }
    };
    el.onerror = () => {
      terminarAtual = null;
      reject(new Error('Não consegui tocar o áudio.'));
    };
    el.src = urlAtual;
    const p = el.play();
    if (p && typeof p.then === 'function') {
      p.then(() => {
        if (minha === vez) useEdenVozStore.setState({ state: 'speaking' });
      }).catch((e: unknown) => reject(e instanceof Error ? e : new Error('Não consegui tocar o áudio.')));
    }
  });
}

interface EdenVozStore {
  state: EstadoVoz;
  speakingId: string | null;
  error: string | null;
  errorId: string | null;
  available: boolean | null;
  autoSpokenId: string | null;
  speak: (id: string, text: string) => Promise<void>;
  stop: () => void;
  ensureHealth: () => Promise<void>;
  markAutoSpoken: (id: string) => void;
}

export const useEdenVozStore = create<EdenVozStore>((set) => ({
  state: 'idle',
  speakingId: null,
  error: null,
  errorId: null,
  available: null,
  autoSpokenId: null,

  ensureHealth: () => {
    if (sonda) return sonda;
    sonda = apiFetch('/v1/eden/voz/status')
      .then(async (res) => {
        const corpo = res.ok ? await res.json() : null;
        const ok = Boolean(corpo?.available);
        set({ available: ok });
        if (!ok) sonda = null;
      })
      .catch(() => {
        set({ available: false });
        sonda = null;
      });
    return sonda;
  },

  markAutoSpoken: (id) => set({ autoSpokenId: id }),

  speak: async (id, text) => {
    const pedacos = dividirParaFala(textoParaFala(text));
    vez += 1;
    const minha = vez;
    soltar();
    if (pedacos.length === 0) {
      set({ state: 'idle', speakingId: null });
      return;
    }
    set({ state: 'loading', speakingId: id, error: null, errorId: null });
    const ac = new AbortController();
    controle = ac;
    // Gera um pedaço à frente enquanto o anterior toca.
    const prontos: Array<Promise<Blob> | undefined> = [];
    const pedir = (i: number) => {
      if (i < pedacos.length && !prontos[i]) {
        prontos[i] = sintetizar(pedacos[i], ac.signal);
        prontos[i]!.catch(() => {}); // o erro aparece quando chegar a vez dele
      }
    };
    try {
      pedir(0);
      for (let i = 0; i < pedacos.length; i++) {
        pedir(i + 1);
        const blob = await prontos[i]!;
        if (minha !== vez) return;
        const fim = await tocar(blob, minha);
        if (minha !== vez) return;
        if (fim === 'pausa') {
          // Interrompido pelo aparelho: não continua sozinho depois.
          vez += 1;
          soltar();
          set({ state: 'idle', speakingId: null });
          return;
        }
      }
      if (minha === vez) {
        soltar();
        set({ state: 'idle', speakingId: null });
      }
    } catch (err) {
      if (minha !== vez) return;
      if (err instanceof DOMException && err.name === 'AbortError') {
        soltar();
        set({ state: 'idle', speakingId: null });
        return;
      }
      soltar();
      let msg = err instanceof Error ? err.message : 'A voz falhou.';
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        msg = 'O aparelho bloqueou o som: toque no alto-falante da mensagem para ouvir.';
      }
      set({ state: 'idle', speakingId: null, error: msg, errorId: id });
    }
  },

  stop: () => {
    vez += 1;
    soltar();
    set({ state: 'idle', speakingId: null, error: null, errorId: null });
  },
}));

/** Para testes: zera o tocador entre os casos. */
export function __zerarVozParaTestes(): void {
  soltar();
  elemento = null;
  vez = 0;
  sonda = null;
  useEdenVozStore.setState({
    state: 'idle',
    speakingId: null,
    error: null,
    errorId: null,
    available: null,
    autoSpokenId: null,
  });
}
