// Éden: modo reunião — grava em pedaços de ~1 minuto e manda cada pedaço ao
// servidor assim que fica pronto. Se a internet cair, o pedaço espera na fila
// e vai de novo (o servidor não transcreve nem cobra duas vezes o mesmo).
// O Éden só escuta enquanto a pessoa deixar gravando.
import { apiFetch } from './api';
import { edenJson, ErroEden, type Acao } from './eden-org';
import { audioFilenameFor, pickRecordingMimeType } from '../hooks/useSpeech';

export type EstadoReuniao = 'gravando' | 'resumindo' | 'pronta' | 'erro';

export interface Reuniao {
  id: number;
  titulo: string;
  espaco: string;
  estado: EstadoReuniao;
  criado_em: number;
  terminado_em: number | null;
  pedacos: number;
  segundos: number;
  erro: string | null;
}

export interface ReuniaoCompleta extends Reuniao {
  resumo: string | null;
  tarefas: { titulo: string; data?: string }[];
  transcricao: string;
  cartoes: Acao[];
}

/** Cada pedaço tem ~1 minuto (arquivo completo, transcrito sozinho). */
export const PEDACO_MS = 60_000;

export const listarReunioes = () => edenJson<{ reunioes: Reuniao[] }>('/reunioes');
export const comecarReuniao = (titulo: string, espaco: string) =>
  edenJson<{ reuniao: ReuniaoCompleta }>('/reunioes', { method: 'POST', body: { titulo, espaco } });
export const abrirReuniao = (id: number) => edenJson<{ reuniao: ReuniaoCompleta }>(`/reunioes/${id}`);
export const terminarReuniao = (id: number) =>
  edenJson<{ ok: boolean }>(`/reunioes/${id}/terminar`, { method: 'POST', body: {} });
export const apagarReuniao = (id: number) => edenJson<{ ok: boolean }>(`/reunioes/${id}`, { method: 'DELETE' });
export const cartoesDeNovo = (id: number) =>
  edenJson<{ cartoes: Acao[]; recusadas: string[] }>(`/reunioes/${id}/cartoes`, { method: 'POST', body: {} });

export async function enviarPedaco(
  id: number,
  n: number,
  audio: Blob,
  nome: string,
  duracaoMs: number,
): Promise<{ repetido: boolean }> {
  const dados = new FormData();
  dados.append('n', String(n));
  if (duracaoMs > 0) dados.append('duration_ms', String(Math.round(duracaoMs)));
  dados.append('file', audio, nome);
  const res = await apiFetch(`/v1/eden/reunioes/${id}/pedaco`, { method: 'POST', body: dados });
  let corpo: any = null;
  try {
    corpo = await res.json();
  } catch {
    corpo = null;
  }
  if (!res.ok) {
    const detalhe = typeof corpo?.detail === 'string' ? corpo.detail : `O servidor recusou (erro ${res.status}).`;
    throw new ErroEden(detalhe, res.status);
  }
  return { repetido: Boolean(corpo?.repetido) };
}

/** Espera antes de mandar de novo: 2 s, 4 s, 8 s… até 30 s. */
export function esperaDaTentativa(tentativa: number): number {
  return Math.min(30_000, 2000 * 2 ** Math.max(0, tentativa));
}

/** Vale tentar de novo? (internet caiu, servidor ocupado ou reiniciando) */
export function valeTentarDeNovo(erro: unknown): boolean {
  if (erro instanceof TypeError) return true; // sem conexão ("Load failed")
  if (erro instanceof ErroEden) return [0, 409, 429, 500, 502, 503, 504].includes(erro.status);
  return false;
}

/** "1:05:09" ou "4:07". */
export function duracaoTexto(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`;
}

export interface SituacaoGravador {
  gravando: boolean;
  enviados: number;
  naFila: number;
  tentando: boolean;
  erro: string | null;
}

interface ItemDaFila {
  n: number;
  audio: Blob;
  nome: string;
  duracaoMs: number;
}

/**
 * Grava a reunião em pedaços: a cada ~1 minuto o gravador para (o pedaço
 * vira um arquivo completo) e recomeça na hora. Os pedaços vão em fila.
 */
export class GravadorDeReuniao {
  private stream: MediaStream | null = null;
  private gravador: MediaRecorder | null = null;
  private relogio = 0;
  private proximo = 0;
  private continuar = false;
  private fila: ItemDaFila[] = [];
  private enviando = false;
  private tentativas = 0;
  private trava: WakeLockSentinel | null = null;
  private esperandoFim: (() => void) | null = null;
  private parou: Promise<void> = Promise.resolve();
  private situacao: SituacaoGravador = { gravando: false, enviados: 0, naFila: 0, tentando: false, erro: null };
  private readonly aoVoltar = () => {
    if (document.visibilityState === 'visible' && this.continuar) void this.travarTela();
  };

  constructor(
    private readonly reuniaoId: number,
    private readonly aoMudar: (s: SituacaoGravador) => void,
    private readonly enviar: typeof enviarPedaco = enviarPedaco,
    private readonly esperar: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
    private readonly pedacoMs: number = PEDACO_MS,
  ) {}

  private avisar(mudanca: Partial<SituacaoGravador>): void {
    this.situacao = { ...this.situacao, ...mudanca, naFila: this.fila.length };
    this.aoMudar(this.situacao);
  }

  async comecar(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      throw new Error('Este navegador não permite gravar áudio.');
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      throw new Error('Não foi possível usar o microfone. Libere o acesso nas configurações do navegador.');
    }
    this.continuar = true;
    document.addEventListener('visibilitychange', this.aoVoltar);
    await this.travarTela();
    this.novoPedaco();
    this.avisar({ gravando: true, erro: null });
  }

  /** Tela ligada enquanto grava (no iPhone, a gravação para com a tela travada). */
  private async travarTela(): Promise<void> {
    try {
      const wl = (navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<WakeLockSentinel> } })
        .wakeLock;
      if (wl && !this.trava) {
        this.trava = await wl.request('screen');
        this.trava.addEventListener('release', () => {
          this.trava = null;
        });
      }
    } catch {
      // Sem suporte (ou economia de bateria): a tela da página avisa.
    }
  }

  private novoPedaco(): void {
    if (!this.stream || !this.continuar) return;
    const tipo = pickRecordingMimeType();
    const opcoes: MediaRecorderOptions = { audioBitsPerSecond: 32_000 };
    if (tipo) opcoes.mimeType = tipo;
    let gravador: MediaRecorder;
    try {
      gravador = new MediaRecorder(this.stream, opcoes);
    } catch {
      gravador = tipo ? new MediaRecorder(this.stream, { mimeType: tipo }) : new MediaRecorder(this.stream);
    }
    const partes: Blob[] = [];
    let avisarParou: () => void = () => {};
    this.parou = new Promise((r) => {
      avisarParou = r;
    });
    gravador.ondataavailable = (e) => {
      if (e.data.size > 0) partes.push(e.data);
    };
    const inicio = Date.now();
    gravador.onstop = () => {
      const audio = new Blob(partes, { type: gravador.mimeType || tipo || 'audio/webm' });
      this.adicionarPedaco(audio, Date.now() - inicio);
      // Recomeça na hora (o intervalo entre os pedaços é de milissegundos).
      if (this.continuar) this.novoPedaco();
      avisarParou();
    };
    this.gravador = gravador;
    gravador.start();
    clearTimeout(this.relogio);
    this.relogio = window.setTimeout(() => {
      if (gravador.state === 'recording') gravador.stop();
    }, this.pedacoMs);
  }

  /** Um pedaço pronto entra na fila (e a fila anda). */
  adicionarPedaco(audio: Blob, duracaoMs: number): void {
    if (audio.size === 0) return;
    this.fila.push({ n: this.proximo++, audio, nome: audioFilenameFor(audio.type), duracaoMs });
    this.avisar({});
    void this.mandarFila();
  }

  private async mandarFila(): Promise<void> {
    if (this.enviando) return;
    this.enviando = true;
    try {
      while (this.fila.length > 0) {
        const item = this.fila[0];
        try {
          await this.enviar(this.reuniaoId, item.n, item.audio, item.nome, item.duracaoMs);
          this.fila.shift();
          this.tentativas = 0;
          this.avisar({ enviados: this.situacao.enviados + 1, tentando: false, erro: null });
        } catch (erro) {
          if (!valeTentarDeNovo(erro)) {
            this.avisar({ tentando: false, erro: (erro as Error).message || 'Não deu para mandar o áudio.' });
            return;
          }
          const espera = esperaDaTentativa(this.tentativas++);
          this.avisar({ tentando: true });
          await this.esperar(espera);
        }
      }
    } finally {
      this.enviando = false;
      // Quem espera o fim confere depois se sobrou algo na fila.
      if (this.esperandoFim) {
        const fim = this.esperandoFim;
        this.esperandoFim = null;
        fim();
      }
    }
  }

  /** Para de gravar e espera todos os pedaços chegarem ao servidor. */
  async terminar(): Promise<void> {
    const ultimo = this.parou;
    this.parar();
    // O último pedaço entra na fila (no máximo 3 s de espera).
    await Promise.race([ultimo, this.esperar(3000)]);
    if (this.fila.length > 0) {
      await new Promise<void>((resolve) => {
        this.esperandoFim = resolve;
        if (!this.enviando) void this.mandarFila();
      });
    }
    if (this.fila.length > 0) throw new Error(this.situacao.erro || 'Ainda há áudio para mandar.');
  }

  /** Para tudo (sem esperar a fila). */
  parar(): void {
    this.continuar = false;
    clearTimeout(this.relogio);
    if (this.gravador && this.gravador.state === 'recording') this.gravador.stop();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', this.aoVoltar);
    void this.trava?.release().catch(() => {});
    this.trava = null;
    this.avisar({ gravando: false });
  }

  /** Cancela: para e joga fora o que estava na fila. */
  cancelar(): void {
    this.fila = [];
    this.parar();
  }

  /** Tenta de novo depois de um erro que parou a fila. */
  tentarDeNovo(): void {
    this.tentativas = 0;
    this.avisar({ erro: null });
    void this.mandarFila();
  }
}
