// Éden: "mãos livres" (modo conversa contínuo). A pessoa liga, fala, o Éden
// percebe quando ela parou de falar, envia, responde em voz e volta a ouvir.
//
// Regras (pedido do Levi, 04/11): só ouve quando a pessoa liga, só com o app
// aberto na tela, e o silêncio não sai do aparelho — quem decide se há fala é
// o próprio celular (nível do som). Desliga sozinho depois de um tempo em
// silêncio. Enquanto o Éden responde, o microfone fica desligado (ele não
// ouve a si mesmo e, no iPhone, o som sai pelo alto-falante).

export type EstadoMaosLivres = 'desligado' | 'ouvindo' | 'gravando' | 'pensando';

/** Quanto tempo cada leitura do nível do som representa. */
export const QUADRO_MS = 50;

export interface ParametrosDetector {
  /** Quadros seguidos acima do limite para contar como começo de fala. */
  quadrosParaComecar: number;
  /** Quadros seguidos de silêncio para dar a fala por terminada. */
  quadrosParaTerminar: number;
  /** Limites mínimos (RMS de 0 a 1), mesmo com o ambiente muito quieto. */
  minimoComeco: number;
  minimoFim: number;
  /** Quanto acima do ruído de fundo a voz precisa estar. */
  fatorComeco: number;
  fatorFim: number;
}

export const PADRAO_DETECTOR: ParametrosDetector = {
  quadrosParaComecar: 3, // 150 ms
  quadrosParaTerminar: 24, // 1,2 s de silêncio
  minimoComeco: 0.02,
  minimoFim: 0.014,
  fatorComeco: 2.6,
  fatorFim: 1.8,
};

export type EventoDetector = 'comecou' | 'terminou' | null;

/**
 * Decide, só pelo nível do som, quando alguém começou e terminou de falar.
 * Acompanha o ruído de fundo (ventilador, rua) para não disparar à toa.
 */
/** Quadros do começo só para medir o ruído de fundo (400 ms). */
const QUADROS_DE_AQUECIMENTO = 8;

export class DetectorDeFala {
  private fundo = 0.008;
  private acima = 0;
  private abaixo = 0;
  private falando = false;
  private vistos = 0;
  private somaAquecimento = 0;

  constructor(private readonly p: ParametrosDetector = PADRAO_DETECTOR) {}

  get emFala(): boolean {
    return this.falando;
  }

  get ruidoDeFundo(): number {
    return this.fundo;
  }

  zerar(): void {
    this.acima = 0;
    this.abaixo = 0;
    this.falando = false;
  }

  /** Um quadro de som (RMS de 0 a 1). */
  quadro(nivel: number): EventoDetector {
    const v = Number.isFinite(nivel) ? Math.max(0, Math.min(1, nivel)) : 0;
    if (this.vistos < QUADROS_DE_AQUECIMENTO) {
      // Primeiro só escuta o ambiente (ventilador, rua) para saber o fundo.
      this.vistos += 1;
      this.somaAquecimento += v;
      this.fundo = Math.max(0.002, this.somaAquecimento / this.vistos);
      return null;
    }
    const limiteComeco = Math.max(this.p.minimoComeco, this.fundo * this.p.fatorComeco);
    const limiteFim = Math.max(this.p.minimoFim, this.fundo * this.p.fatorFim);
    if (!this.falando) {
      if (v >= limiteComeco) {
        this.acima += 1;
        if (this.acima >= this.p.quadrosParaComecar) {
          this.falando = true;
          this.abaixo = 0;
          return 'comecou';
        }
      } else {
        this.acima = 0;
        // Só aprende o ruído de fundo fora da fala (e devagar).
        this.fundo = this.fundo * 0.95 + v * 0.05;
      }
      return null;
    }
    if (v < limiteFim) {
      this.abaixo += 1;
      if (this.abaixo >= this.p.quadrosParaTerminar) {
        this.falando = false;
        this.acima = 0;
        this.abaixo = 0;
        return 'terminou';
      }
    } else {
      this.abaixo = 0;
    }
    return null;
  }
}

/** RMS (0 a 1) de um pedaço de áudio. */
export function nivelRms(amostras: ArrayLike<number>): number {
  if (!amostras.length) return 0;
  let soma = 0;
  for (let i = 0; i < amostras.length; i += 1) soma += amostras[i] * amostras[i];
  return Math.sqrt(soma / amostras.length);
}

/** O que foi falado vale a pena mandar? (ruído às vezes vira "Obrigado.") */
export function valeEnviar(texto: string): boolean {
  return texto.trim().split(/\s+/).filter(Boolean).length >= 2;
}

// ── controle (microfone, gravação e tempos) ───────────────────────────────

export interface DependenciasMaosLivres {
  pedirMicrofone: () => Promise<MediaStream>;
  criarGravador: (stream: MediaStream) => MediaRecorder;
  /** Lê o nível do som do microfone; devolve uma função que para a leitura. */
  medirNivel: (stream: MediaStream, aoQuadro: (nivel: number) => void) => () => void;
  agora: () => number;
  /** Mantém a tela ligada (no iPhone, a tela travada para o microfone). */
  travarTela?: () => Promise<{ release: () => Promise<void> } | null>;
}

export interface OpcoesMaosLivres {
  /** Transcreve e envia. Pode demorar (a resposta vem por fluxo). */
  aoFalar: (audio: Blob, duracaoMs: number) => Promise<void>;
  aoMudar: (estado: EstadoMaosLivres, aviso?: string) => void;
  /** O Éden terminou de responder e de falar? (aí volta a ouvir) */
  podeOuvir: () => boolean;
  silencioMaximoMs?: number;
  falaMaximaMs?: number;
  falaMinimaMs?: number;
}

export const SILENCIO_MAXIMO_MS = 60_000;
export const FALA_MAXIMA_MS = 60_000;
export const FALA_MINIMA_MS = 450;
/** Depois que o Éden termina de falar, espera um pouco antes de ouvir. */
export const PAUSA_DEPOIS_DA_RESPOSTA_MS = 700;

export class MaosLivres {
  private estado: EstadoMaosLivres = 'desligado';
  private stream: MediaStream | null = null;
  private pararMedidor: (() => void) | null = null;
  private gravador: MediaRecorder | null = null;
  private pedacos: Blob[] = [];
  private inicioFala = 0;
  private ultimaAtividade = 0;
  private detector = new DetectorDeFala();
  private espera: ReturnType<typeof setInterval> | null = null;
  private livreDesde = 0;
  private trava: { release: () => Promise<void> } | null = null;
  private geracao = 0;

  constructor(
    private readonly opcoes: OpcoesMaosLivres,
    private readonly dep: DependenciasMaosLivres,
  ) {}

  get situacao(): EstadoMaosLivres {
    return this.estado;
  }

  private mudar(estado: EstadoMaosLivres, aviso?: string): void {
    this.estado = estado;
    this.opcoes.aoMudar(estado, aviso);
  }

  /** Chame no toque da pessoa (o navegador só libera o microfone assim). */
  async ligar(): Promise<void> {
    if (this.estado !== 'desligado') return;
    this.geracao += 1;
    try {
      this.trava = (await this.dep.travarTela?.()) ?? null;
    } catch {
      this.trava = null; // sem trava de tela: a página avisa
    }
    await this.ouvir(this.geracao);
  }

  desligar(aviso?: string): void {
    this.geracao += 1;
    this.soltarMicrofone(true);
    this.pararEspera();
    void this.trava?.release().catch(() => {});
    this.trava = null;
    if (this.estado !== 'desligado') this.mudar('desligado', aviso);
  }

  private async ouvir(minha: number): Promise<void> {
    let stream: MediaStream;
    try {
      stream = await this.dep.pedirMicrofone();
    } catch {
      if (minha === this.geracao) {
        this.desligar('Não consegui usar o microfone. Libere o acesso nas configurações.');
      }
      return;
    }
    if (minha !== this.geracao) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    this.stream = stream;
    this.detector = new DetectorDeFala();
    this.ultimaAtividade = this.dep.agora();
    this.mudar('ouvindo');
    this.pararMedidor = this.dep.medirNivel(stream, (nivel) => this.quadro(nivel, minha));
  }

  private quadro(nivel: number, minha: number): void {
    if (minha !== this.geracao || !this.stream) return;
    const agora = this.dep.agora();
    const evento = this.detector.quadro(nivel);
    if (this.estado === 'ouvindo') {
      if (evento === 'comecou') {
        this.comecarGravacao(agora);
      } else if (agora - this.ultimaAtividade > (this.opcoes.silencioMaximoMs ?? SILENCIO_MAXIMO_MS)) {
        this.desligar('Mãos livres desligado depois de 1 minuto em silêncio.');
      }
      return;
    }
    if (this.estado === 'gravando') {
      const longa = agora - this.inicioFala > (this.opcoes.falaMaximaMs ?? FALA_MAXIMA_MS);
      if (evento === 'terminou' || longa) {
        // Quanto foi fala de verdade (sem o silêncio do fim).
        const silencioFinal = evento === 'terminou' ? PADRAO_DETECTOR.quadrosParaTerminar * QUADRO_MS : 0;
        void this.terminarGravacao(minha, agora, agora - this.inicioFala - silencioFinal);
      }
    }
  }

  private comecarGravacao(agora: number): void {
    if (!this.stream) return;
    let gravador: MediaRecorder;
    try {
      gravador = this.dep.criarGravador(this.stream);
    } catch {
      this.desligar('Este navegador não permite gravar áudio.');
      return;
    }
    this.pedacos = [];
    gravador.ondataavailable = (e) => {
      if (e.data.size > 0) this.pedacos.push(e.data);
    };
    gravador.start();
    this.gravador = gravador;
    this.inicioFala = agora;
    this.mudar('gravando');
  }

  private async terminarGravacao(minha: number, agora: number, fala: number): Promise<void> {
    const gravador = this.gravador;
    if (!gravador) return;
    this.gravador = null;
    const duracao = agora - this.inicioFala;
    const parou = new Promise<void>((resolve) => {
      gravador.onstop = () => resolve();
    });
    try {
      if (gravador.state !== 'inactive') gravador.stop();
    } catch {
      // já parado
    }
    await parou;
    const tipo = gravador.mimeType || 'audio/webm';
    const audio = new Blob(this.pedacos, { type: tipo });
    this.pedacos = [];
    if (minha !== this.geracao) return;
    if (fala < (this.opcoes.falaMinimaMs ?? FALA_MINIMA_MS) || audio.size === 0) {
      // Barulho curto (porta, tosse): continua ouvindo, sem mandar nada.
      this.detector.zerar();
      this.mudar('ouvindo');
      return;
    }
    // Microfone desligado enquanto o Éden transcreve, responde e fala.
    this.soltarMicrofone(false);
    this.mudar('pensando');
    try {
      await this.opcoes.aoFalar(audio, duracao);
    } catch (e) {
      if (minha !== this.geracao) return;
      this.opcoes.aoMudar('pensando', e instanceof Error ? e.message : 'Não deu para entender.');
    }
    if (minha !== this.geracao) return;
    this.esperarResposta(minha);
  }

  /** Volta a ouvir quando o Éden terminar de responder e de falar. */
  private esperarResposta(minha: number): void {
    this.pararEspera();
    this.livreDesde = 0;
    this.espera = setInterval(() => {
      if (minha !== this.geracao) {
        this.pararEspera();
        return;
      }
      const agora = this.dep.agora();
      if (!this.opcoes.podeOuvir()) {
        this.livreDesde = 0;
        return;
      }
      if (!this.livreDesde) this.livreDesde = agora;
      if (agora - this.livreDesde >= PAUSA_DEPOIS_DA_RESPOSTA_MS) {
        this.pararEspera();
        void this.ouvir(minha);
      }
    }, 150);
  }

  private pararEspera(): void {
    if (this.espera) clearInterval(this.espera);
    this.espera = null;
  }

  private soltarMicrofone(descartarGravacao: boolean): void {
    this.pararMedidor?.();
    this.pararMedidor = null;
    if (descartarGravacao && this.gravador) {
      const g = this.gravador;
      this.gravador = null;
      g.ondataavailable = null;
      try {
        if (g.state !== 'inactive') g.stop();
      } catch {
        // já parado
      }
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.detector.zerar();
  }
}

// ── implementação de verdade (navegador) ──────────────────────────────────

let contexto: AudioContext | null = null;

/** Liga o processamento de som (chame no toque da pessoa, por causa do iPhone). */
export function prepararAudio(): void {
  try {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    if (!contexto) contexto = new Ctx();
    if (contexto.state === 'suspended') void contexto.resume();
  } catch {
    contexto = null;
  }
}

export function dependenciasDoNavegador(criarGravador: (stream: MediaStream) => MediaRecorder): DependenciasMaosLivres {
  return {
    pedirMicrofone: () =>
      navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      }),
    criarGravador,
    medirNivel: (stream, aoQuadro) => {
      prepararAudio();
      if (!contexto) return () => {};
      const fonte = contexto.createMediaStreamSource(stream);
      const analisador = contexto.createAnalyser();
      analisador.fftSize = 1024;
      fonte.connect(analisador);
      const dados = new Float32Array(analisador.fftSize);
      const relogio = setInterval(() => {
        analisador.getFloatTimeDomainData(dados);
        aoQuadro(nivelRms(dados));
      }, QUADRO_MS);
      return () => {
        clearInterval(relogio);
        try {
          fonte.disconnect();
        } catch {
          // já desligado
        }
      };
    },
    agora: () => Date.now(),
    travarTela: async () => {
      const wl = (navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<WakeLockSentinel> } })
        .wakeLock;
      return wl ? wl.request('screen') : null;
    },
  };
}
