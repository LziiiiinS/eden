// Éden: utilidades do visual 3D (WebGL 1, sem biblioteca).
import { useCallback, useEffect, useRef, useState } from 'react';

function compilar(gl: WebGLRenderingContext, tipo: number, fonte: string): WebGLShader | null {
  const s = gl.createShader(tipo);
  if (!s) return null;
  gl.shaderSource(s, fonte);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    gl.deleteShader(s);
    return null;
  }
  return s;
}

/** Programa pronto (ou null se o aparelho não conseguir montar). */
export function criarPrograma(
  gl: WebGLRenderingContext,
  vertice: string,
  fragmento: string,
): { prog: WebGLProgram; apagar: () => void } | null {
  const vs = compilar(gl, gl.VERTEX_SHADER, vertice);
  const fs = compilar(gl, gl.FRAGMENT_SHADER, fragmento);
  const prog = gl.createProgram();
  const apagar = () => {
    if (prog) gl.deleteProgram(prog);
    if (vs) gl.deleteShader(vs);
    if (fs) gl.deleteShader(fs);
  };
  if (!vs || !fs || !prog) {
    apagar();
    return null;
  }
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    apagar();
    return null;
  }
  return { prog, apagar };
}

/** Solta o contexto WebGL na hora e tira o canvas da tela. */
export function liberarCanvas(gl: WebGLRenderingContext | null, canvas: HTMLCanvasElement): void {
  try {
    gl?.getExtension('WEBGL_lose_context')?.loseContext();
  } catch {
    // já perdido
  }
  canvas.remove();
}

/**
 * Laço de desenho com quadros por segundo limitados. Entre um quadro e outro
 * o JavaScript dorme (não acorda 60–120 vezes por segundo à toa) e o laço
 * para quando o desenho sai da tela ou o app vai para segundo plano.
 */
export function lacoDeDesenho(desenhar: (agora: number) => void, quadrosPorSegundo: () => number) {
  let rodando = false;
  let encerrado = false;
  let visivel = true;
  let timer = 0;
  let quadro = 0;
  const passo = (agora: number) => {
    if (encerrado || !visivel || document.hidden) {
      rodando = false;
      return;
    }
    const inicio = performance.now();
    desenhar(agora);
    const espera = 1000 / quadrosPorSegundo() - (performance.now() - inicio) - 2;
    timer = window.setTimeout(() => {
      quadro = requestAnimationFrame(passo);
    }, Math.max(0, espera));
  };
  const ligar = () => {
    if (rodando || encerrado || !visivel || document.hidden) return;
    rodando = true;
    quadro = requestAnimationFrame(passo);
  };
  const aoVoltar = () => {
    if (!document.hidden) ligar();
  };
  document.addEventListener('visibilitychange', aoVoltar);
  return {
    ligar,
    visibilidade(v: boolean) {
      visivel = v;
      if (v) ligar();
    },
    parar() {
      encerrado = true;
      clearTimeout(timer);
      cancelAnimationFrame(quadro);
      document.removeEventListener('visibilitychange', aoVoltar);
    },
  };
}

/**
 * O navegador pode perder o contexto WebGL (comum no iPhone quando o app vai
 * para segundo plano). Em vez de ficar sem 3D até recarregar, tenta de novo
 * quando o app volta; depois de 3 perdas, fica no desenho simples (CSS).
 */
export function useContextoWebgl() {
  const [geracao, setGeracao] = useState(0);
  const [semWebgl, setSemWebgl] = useState(false);
  const perdas = useRef(0);
  const perdeu = useCallback(() => {
    perdas.current += 1;
    if (perdas.current > 3) {
      setSemWebgl(true);
      return;
    }
    const tentar = () => {
      if (document.hidden) return;
      document.removeEventListener('visibilitychange', tentar);
      window.setTimeout(() => setGeracao((g) => g + 1), 400);
    };
    if (document.hidden) document.addEventListener('visibilitychange', tentar);
    else tentar();
  }, []);
  const semSuporte = useCallback(() => setSemWebgl(true), []);
  return { geracao, semWebgl, perdeu, semSuporte };
}

export function reduzirMovimento(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

function lerTemaEscuro(): boolean {
  const raiz = document.documentElement.classList;
  if (raiz.contains('dark')) return true;
  if (raiz.contains('light')) return false;
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch {
    return false;
  }
}

/** Tema escuro agora (acompanha a troca de tema e o modo automático). */
export function useTemaEscuro(): boolean {
  const [escuro, setEscuro] = useState(lerTemaEscuro);
  useEffect(() => {
    const atualizar = () => setEscuro(lerTemaEscuro());
    const observador = new MutationObserver(atualizar);
    observador.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    let mq: MediaQueryList | null = null;
    try {
      mq = window.matchMedia('(prefers-color-scheme: dark)');
      mq.addEventListener('change', atualizar);
    } catch {
      mq = null;
    }
    return () => {
      observador.disconnect();
      mq?.removeEventListener('change', atualizar);
    };
  }, []);
  return escuro;
}
