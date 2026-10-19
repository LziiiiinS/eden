// Éden: núcleo 3D (WebGL, sem biblioteca). Uma esfera "viva" desenhada por
// raymarching: a superfície ondula conforme o estado (repouso, ouvindo,
// pensando, falando), com brilho na borda e um halo.
//
// Cuidados com bateria e desempenho (iPhone e Samsung):
// - no máximo 30 quadros por segundo e resolução limitada;
// - para quando sai da tela ou o app vai para segundo plano;
// - "reduzir movimento" do aparelho → um quadro parado;
// - sem WebGL (ou se o navegador perder o contexto) → esfera simples em CSS.
import { useEffect, useRef, useState } from 'react';
import { VISUAL, type EstadoNucleo } from '../../lib/eden-nucleo';

const VERTICE = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const FRAGMENTO = `
precision mediump float;
uniform vec2 u_res;
uniform float u_t;
uniform vec3 u_cor;
uniform float u_energia;

float hash(vec3 p) {
  p = fract(p * 0.3183099 + 0.1);
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float ruido(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash(i), hash(i + vec3(1.0, 0.0, 0.0)), f.x),
        mix(hash(i + vec3(0.0, 1.0, 0.0)), hash(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
    mix(mix(hash(i + vec3(0.0, 0.0, 1.0)), hash(i + vec3(1.0, 0.0, 1.0)), f.x),
        mix(hash(i + vec3(0.0, 1.0, 1.0)), hash(i + vec3(1.0, 1.0, 1.0)), f.x), f.y),
    f.z);
}

float mapa(vec3 p) {
  float n = ruido(p * 2.3 + vec3(0.0, u_t * 0.35, u_t * 0.6));
  n += 0.5 * ruido(p * 4.6 - vec3(u_t * 0.5, 0.0, 0.0));
  return length(p) - 0.95 - (0.05 + 0.16 * u_energia) * n;
}

vec3 normal(vec3 p) {
  vec2 e = vec2(0.003, 0.0);
  return normalize(vec3(
    mapa(p + e.xyy) - mapa(p - e.xyy),
    mapa(p + e.yxy) - mapa(p - e.yxy),
    mapa(p + e.yyx) - mapa(p - e.yyx)));
}

void main() {
  vec2 uv = (gl_FragCoord.xy * 2.0 - u_res) / min(u_res.x, u_res.y);
  vec3 ro = vec3(0.0, 0.0, 3.4);
  vec3 rd = normalize(vec3(uv, -2.1));
  float a = u_t * 0.22;
  mat2 r = mat2(cos(a), -sin(a), sin(a), cos(a));
  ro.xz = r * ro.xz;
  rd.xz = r * rd.xz;

  float t = 0.0;
  bool bateu = false;
  for (int i = 0; i < 44; i++) {
    float d = mapa(ro + rd * t);
    if (d < 0.003) { bateu = true; break; }
    t += d * 0.85;
    if (t > 6.0) break;
  }

  float raio = length(uv);
  float halo = exp(-5.0 * max(raio - 0.58, 0.0)) * (0.3 + 0.5 * u_energia)
      * (1.0 - smoothstep(0.7, 1.0, raio));
  vec3 cor = vec3(0.0);
  float alfa = 0.0;
  if (bateu) {
    vec3 p = ro + rd * t;
    vec3 n = normal(p);
    vec3 luz = normalize(vec3(0.5, 0.8, 0.6));
    float dif = max(dot(n, luz), 0.0);
    float borda = pow(1.0 - max(dot(n, -rd), 0.0), 2.4);
    float faixas = 0.5 + 0.5 * sin(14.0 * p.y + u_t * 2.4);
    cor = u_cor * (0.14 + 0.55 * dif)
        + u_cor * borda * 1.5
        + vec3(1.0) * pow(dif, 28.0) * 0.4
        + u_cor * faixas * (0.06 + 0.14 * u_energia);
    alfa = 1.0;
  } else {
    cor = u_cor * halo;
    alfa = clamp(halo, 0.0, 1.0);
  }
  gl_FragColor = vec4(cor, alfa);
}
`;

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

function reduzirMovimento(): boolean {
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

function EsferaSimples({ tamanho, estado }: { tamanho: number; estado: EstadoNucleo }) {
  const [r, g, b] = VISUAL[estado].cor.map((c) => Math.round(c * 255));
  return (
    <div
      className="eden-nucleo-css rounded-full"
      style={{
        width: tamanho * 0.62,
        height: tamanho * 0.62,
        margin: tamanho * 0.19,
        background: `radial-gradient(circle at 35% 30%, rgba(255,255,255,.55), rgba(${r},${g},${b},.9) 35%, rgba(${r},${g},${b},.25) 70%, transparent 72%)`,
        boxShadow: `0 0 ${tamanho * 0.25}px rgba(${r},${g},${b},.45)`,
      }}
    />
  );
}

export function EdenNucleo({ tamanho, estado }: { tamanho: number; estado: EstadoNucleo }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const estadoRef = useRef(estado);
  const [semWebgl, setSemWebgl] = useState(false);
  estadoRef.current = estado;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || semWebgl) return;
    const gl = canvas.getContext('webgl', { premultipliedAlpha: true, antialias: false, alpha: true });
    if (!gl) {
      setSemWebgl(true);
      return;
    }
    const vs = compilar(gl, gl.VERTEX_SHADER, VERTICE);
    const fs = compilar(gl, gl.FRAGMENT_SHADER, FRAGMENTO);
    const prog = gl.createProgram();
    if (!vs || !fs || !prog) {
      setSemWebgl(true);
      return;
    }
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      setSemWebgl(true);
      return;
    }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(prog, 'a_pos');
    gl.enableVertexAttribArray(pos);
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    const uRes = gl.getUniformLocation(prog, 'u_res');
    const uT = gl.getUniformLocation(prog, 'u_t');
    const uCor = gl.getUniformLocation(prog, 'u_cor');
    const uEnergia = gl.getUniformLocation(prog, 'u_energia');

    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(tamanho * dpr);
    canvas.height = Math.round(tamanho * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);

    const parado = reduzirMovimento();
    const cor = [...VISUAL[estadoRef.current].cor];
    let energia = VISUAL[estadoRef.current].energia;
    let quadro = 0;
    let ultimo = 0;
    let visivel = true;
    const inicio = performance.now();

    const desenhar = (agora: number) => {
      const alvo = VISUAL[estadoRef.current];
      // Transição suave entre os estados.
      for (let i = 0; i < 3; i++) cor[i] += (alvo.cor[i] - cor[i]) * 0.08;
      const pulso = estadoRef.current === 'falando' ? 0.15 * Math.sin(agora / 140) : 0;
      energia += (alvo.energia + pulso - energia) * 0.1;
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uT, parado ? 1.0 : (agora - inicio) / 1000);
      gl.uniform3f(uCor, cor[0], cor[1], cor[2]);
      gl.uniform1f(uEnergia, Math.max(0, energia));
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };

    const laco = (agora: number) => {
      quadro = requestAnimationFrame(laco);
      if (!visivel || document.hidden) return;
      if (agora - ultimo < 33) return; // ~30 quadros por segundo
      ultimo = agora;
      desenhar(agora);
    };

    if (parado) {
      desenhar(performance.now());
    } else {
      quadro = requestAnimationFrame(laco);
    }

    const observador =
      typeof IntersectionObserver !== 'undefined'
        ? new IntersectionObserver((entradas) => {
            visivel = entradas.some((e) => e.isIntersecting);
          })
        : null;
    observador?.observe(canvas);

    const perdeu = (e: Event) => {
      e.preventDefault();
      setSemWebgl(true);
    };
    canvas.addEventListener('webglcontextlost', perdeu);

    return () => {
      cancelAnimationFrame(quadro);
      observador?.disconnect();
      canvas.removeEventListener('webglcontextlost', perdeu);
      gl.deleteBuffer(buf);
      gl.deleteProgram(prog);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
    };
  }, [tamanho, semWebgl]);

  return (
    <div
      role="img"
      aria-label={VISUAL[estado].texto}
      title={VISUAL[estado].texto}
      style={{ width: tamanho, height: tamanho, flexShrink: 0 }}
    >
      {semWebgl ? (
        <EsferaSimples tamanho={tamanho} estado={estado} />
      ) : (
        <canvas ref={canvasRef} style={{ width: tamanho, height: tamanho, display: 'block' }} />
      )}
    </div>
  );
}
