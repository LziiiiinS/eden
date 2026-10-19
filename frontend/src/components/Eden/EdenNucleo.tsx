// Éden: núcleo 3D (WebGL, sem biblioteca). Uma esfera de vidro "viva"
// desenhada por raymarching: a superfície ondula conforme o estado (repouso,
// ouvindo, pensando, falando), com uma luz por dentro, dois anéis em volta e
// um halo. O desenho está em eden-shaders.ts.
//
// Cuidados com bateria e desempenho (iPhone e Samsung):
// - no máximo 30 quadros por segundo e resolução limitada;
// - para quando sai da tela ou o app vai para segundo plano;
// - "reduzir movimento" do aparelho → um quadro parado;
// - sem WebGL (ou se o navegador perder o contexto) → esfera simples em CSS.
import { useEffect, useRef, useState } from 'react';
import { useNucleoStore, VISUAL, type EstadoNucleo } from '../../lib/eden-nucleo';
import { useEstadoEden } from '../../lib/eden-estado';
import { criarPrograma, reduzirMovimento } from '../../lib/eden-webgl';
import { NUCLEO_FRAGMENTO, NUCLEO_VERTICE } from './eden-shaders';

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
  const caixaRef = useRef<HTMLDivElement | null>(null);
  const estadoRef = useRef(estado);
  const [semWebgl, setSemWebgl] = useState(false);
  const redesenharRef = useRef<() => void>(() => {});
  estadoRef.current = estado;

  // Com "reduzir movimento", o quadro parado é refeito quando o estado muda.
  useEffect(() => {
    redesenharRef.current();
  }, [estado]);

  useEffect(() => {
    const caixa = caixaRef.current;
    if (!caixa || semWebgl) return;
    // Um canvas novo a cada vez: ao sair, o contexto WebGL é liberado na hora
    // (o navegador tem um limite de contextos abertos).
    const canvas = document.createElement('canvas');
    canvas.style.width = `${tamanho}px`;
    canvas.style.height = `${tamanho}px`;
    canvas.style.display = 'block';
    caixa.appendChild(canvas);
    const gl = canvas.getContext('webgl', {
      premultipliedAlpha: true,
      antialias: false,
      alpha: true,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
    });
    if (!gl) {
      canvas.remove();
      setSemWebgl(true);
      return;
    }
    const programa = criarPrograma(gl, NUCLEO_VERTICE, NUCLEO_FRAGMENTO);
    if (!programa) {
      canvas.remove();
      setSemWebgl(true);
      return;
    }
    const { prog } = programa;
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
    const uGiro = gl.getUniformLocation(prog, 'u_giro');

    const dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    canvas.width = Math.round(tamanho * dpr);
    canvas.height = Math.round(tamanho * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clearColor(0, 0, 0, 0);

    const parado = reduzirMovimento();
    const cor = [...VISUAL[estadoRef.current].cor];
    let energia = VISUAL[estadoRef.current].energia;
    let giro = VISUAL[estadoRef.current].giro;
    let voltas = 0;
    let anterior = performance.now();
    let quadro = 0;
    let ultimo = 0;
    let visivel = true;
    const inicio = performance.now();

    const desenhar = (agora: number) => {
      const alvo = VISUAL[estadoRef.current];
      // Transição suave entre os estados (parado: vai direto).
      const k = parado ? 1 : 0.08;
      for (let i = 0; i < 3; i++) cor[i] += (alvo.cor[i] - cor[i]) * k;
      const pulso = estadoRef.current === 'falando' && !parado ? 0.15 * Math.sin(agora / 140) : 0;
      energia += (alvo.energia + pulso - energia) * (parado ? 1 : 0.1);
      giro += (alvo.giro - giro) * k;
      // Os anéis giram pela soma da velocidade (trocar de estado não dá pulo).
      const dt = Math.min((agora - anterior) / 1000, 0.1);
      anterior = agora;
      voltas = (voltas + dt * giro) % 1000;
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uT, parado ? 1.0 : ((agora - inicio) / 1000) % 3600);
      gl.uniform1f(uGiro, voltas);
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
      redesenharRef.current = () => desenhar(performance.now());
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
      redesenharRef.current = () => {};
      observador?.disconnect();
      canvas.removeEventListener('webglcontextlost', perdeu);
      gl.deleteBuffer(buf);
      programa.apagar();
      gl.getExtension('WEBGL_lose_context')?.loseContext();
      canvas.remove();
    };
  }, [tamanho, semWebgl]);

  return (
    <div
      role="img"
      aria-label={VISUAL[estado].texto}
      title={VISUAL[estado].texto}
      style={{ width: tamanho, height: tamanho, flexShrink: 0 }}
    >
      {semWebgl ? <EsferaSimples tamanho={tamanho} estado={estado} /> : <div ref={caixaRef} />}
    </div>
  );
}

/** Núcleo pequeno no topo das páginas: segue o estado do Éden. */
export function EdenNucleoMini({ tamanho = 36 }: { tamanho?: number }) {
  const ativo = useNucleoStore((s) => s.ativo);
  const estado = useEstadoEden();
  if (!ativo) return null;
  return <EdenNucleo tamanho={tamanho} estado={estado} />;
}
