// Éden: utilidades do visual 3D (WebGL 1, sem biblioteca).
import { useEffect, useState } from 'react';

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
  if (!vs || !fs || !prog) return null;
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
  return {
    prog,
    apagar: () => {
      gl.deleteProgram(prog);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
    },
  };
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
