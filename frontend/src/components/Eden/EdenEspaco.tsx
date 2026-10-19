// Éden: o fundo 3D de todas as páginas — um campo de luz em perspectiva
// (malha e pontos até o horizonte) que ondula quando o Éden ouve, pensa ou
// fala. Fica atrás de tudo e não recebe toques.
//
// Cuidados com bateria e desempenho (iPhone e Samsung):
// - 30 quadros por segundo com o Éden ativo e 20 em repouso;
// - resolução limitada (o campo é suave, mais pixels só gastariam bateria);
// - para quando o app vai para segundo plano;
// - "reduzir movimento" do aparelho → um quadro parado (muda só a cor);
// - sem WebGL (ou se o navegador perder o contexto) → o fundo antigo, em CSS.
import { useEffect, useRef, useState } from 'react';
import { corCss, gradeDoHorizonte, quadrosPorSegundo, resolucaoDoFundo, VISUAL } from '../../lib/eden-nucleo';
import { useEstadoEden } from '../../lib/eden-estado';
import { criarPrograma, reduzirMovimento, useTemaEscuro } from '../../lib/eden-webgl';
import { HORIZONTE_FRAGMENTO, HORIZONTE_VERTICE } from './eden-shaders';

const PARTICULAS = 140;

export function EdenEspaco() {
  const estado = useEstadoEden();
  const escuro = useTemaEscuro();
  const caixaRef = useRef<HTMLDivElement | null>(null);
  const estadoRef = useRef(estado);
  const escuroRef = useRef(escuro);
  const redesenharRef = useRef<() => void>(() => {});
  const [semWebgl, setSemWebgl] = useState(false);
  estadoRef.current = estado;
  escuroRef.current = escuro;

  // Com "reduzir movimento", o quadro parado é refeito quando o estado ou o
  // tema mudam (no modo normal, o laço já faz isso).
  useEffect(() => {
    redesenharRef.current();
  }, [estado, escuro]);

  useEffect(() => {
    const caixa = caixaRef.current;
    if (!caixa || semWebgl) return;
    // Canvas novo a cada vez: ao sair, o contexto WebGL é liberado na hora.
    const canvas = document.createElement('canvas');
    canvas.className = 'eden-espaco-tela';
    caixa.appendChild(canvas);
    const gl = canvas.getContext('webgl', {
      premultipliedAlpha: true,
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
    });
    if (!gl) {
      canvas.remove();
      setSemWebgl(true);
      return;
    }
    const programa = criarPrograma(gl, HORIZONTE_VERTICE, HORIZONTE_FRAGMENTO);
    if (!programa) {
      canvas.remove();
      setSemWebgl(true);
      return;
    }
    const { prog } = programa;
    gl.useProgram(prog);
    const local = (nome: string) => gl.getUniformLocation(prog, nome);
    const u = {
      t: local('u_t'),
      energia: local('u_energia'),
      ritmo: local('u_ritmo'),
      fase: local('u_fase'),
      res: local('u_res'),
      olhar: local('u_olhar'),
      escala: local('u_escala'),
      modo: local('u_modo'),
      largura: local('u_largura'),
      cor: local('u_cor'),
      claro: local('u_claro'),
      intensidade: local('u_intensidade'),
      linha: local('u_linha'),
    };
    const aGrade = gl.getAttribLocation(prog, 'a_grade');
    const aSemente = gl.getAttribLocation(prog, 'a_semente');
    gl.enableVertexAttribArray(aGrade);
    gl.enableVertexAttribArray(aSemente);

    const bufChao = gl.createBuffer();
    const bufAr = gl.createBuffer();
    const bufMalha = gl.createBuffer();
    let grade = gradeDoHorizonte(window.innerWidth);
    let nChao = 0;
    let nMalha = 0;

    const montarGrade = () => {
      grade = gradeDoHorizonte(window.innerWidth);
      const { colunas, linhas } = grade;
      const dados = new Float32Array(colunas * linhas * 3);
      let k = 0;
      for (let j = 0; j < linhas; j++) {
        for (let i = 0; i < colunas; i++) {
          dados[k++] = i / (colunas - 1);
          dados[k++] = j / (linhas - 1);
          dados[k++] = Math.random();
        }
      }
      nChao = colunas * linhas;
      gl.bindBuffer(gl.ARRAY_BUFFER, bufChao);
      gl.bufferData(gl.ARRAY_BUFFER, dados, gl.STATIC_DRAW);

      // Malha: as linhas de lado a lado e, de duas em duas colunas, as que
      // vão até o horizonte.
      const indices: number[] = [];
      for (let j = 0; j < linhas; j++) {
        for (let i = 0; i < colunas - 1; i++) indices.push(j * colunas + i, j * colunas + i + 1);
      }
      for (let i = 0; i < colunas; i += 2) {
        for (let j = 0; j < linhas - 1; j++) indices.push(j * colunas + i, (j + 1) * colunas + i);
      }
      nMalha = indices.length;
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, bufMalha);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);

      const ar = new Float32Array(PARTICULAS * 3);
      for (let i = 0; i < ar.length; i++) ar[i] = Math.random();
      gl.bindBuffer(gl.ARRAY_BUFFER, bufAr);
      gl.bufferData(gl.ARRAY_BUFFER, ar, gl.STATIC_DRAW);
    };

    let escala = 1;
    const dimensionar = () => {
      const r = resolucaoDoFundo(window.innerWidth, window.innerHeight, window.devicePixelRatio);
      canvas.width = r.w;
      canvas.height = r.h;
      escala = r.escala;
      gl.viewport(0, 0, r.w, r.h);
    };

    const usar = (buf: WebGLBuffer | null) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.vertexAttribPointer(aGrade, 2, gl.FLOAT, false, 12, 0);
      gl.vertexAttribPointer(aSemente, 1, gl.FLOAT, false, 12, 8);
    };

    montarGrade();
    dimensionar();
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);

    const parado = reduzirMovimento();
    const inicial = VISUAL[estadoRef.current];
    const cor = [...inicial.cor];
    let energia = inicial.energia;
    let ritmo = inicial.ritmo;
    let fase = 0;
    const olhar = [0, 0];
    const olharAlvo = [0, 0];
    const inicio = performance.now();
    let anterior = inicio;
    let quadro = 0;
    let ultimo = 0;

    const desenhar = (agora: number) => {
      const alvo = VISUAL[estadoRef.current];
      const dt = parado ? 1 : Math.min((agora - anterior) / 1000, 0.1);
      anterior = agora;
      const k = (v: number) => Math.min(1, dt * v);
      for (let i = 0; i < 3; i++) cor[i] += (alvo.cor[i] - cor[i]) * k(3);
      energia += (alvo.energia - energia) * k(2.5);
      ritmo += (alvo.ritmo - ritmo) * k(2);
      if (!parado) fase = (fase + dt * ritmo) % (Math.PI * 2000);
      for (let i = 0; i < 2; i++) olhar[i] += (olharAlvo[i] - olhar[i]) * k(2.5);

      const claro = !escuroRef.current;
      gl.clear(gl.COLOR_BUFFER_BIT);
      // Escuro: as luzes se somam (brilham); claro: tinta por cima.
      if (claro) gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      else gl.blendFunc(gl.ONE, gl.ONE);
      gl.uniform1f(u.t, parado ? 4 : ((agora - inicio) / 1000) % 3600);
      gl.uniform1f(u.energia, Math.max(0, energia));
      gl.uniform1f(u.ritmo, ritmo);
      gl.uniform1f(u.fase, parado ? 2 : fase);
      gl.uniform2f(u.res, canvas.width, canvas.height);
      gl.uniform2f(u.olhar, olhar[0], olhar[1]);
      gl.uniform1f(u.escala, escala);
      gl.uniform1f(u.largura, grade.extensao);
      gl.uniform3f(u.cor, cor[0], cor[1], cor[2]);
      gl.uniform1f(u.claro, claro ? 1 : 0);
      gl.uniform1f(u.intensidade, claro ? 0.9 : 0.85);

      usar(bufChao);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, bufMalha);
      gl.uniform1f(u.modo, 0);
      gl.uniform1f(u.linha, 1);
      gl.drawElements(gl.LINES, nMalha, gl.UNSIGNED_SHORT, 0);
      gl.uniform1f(u.linha, 0);
      gl.drawArrays(gl.POINTS, 0, nChao);
      usar(bufAr);
      gl.uniform1f(u.modo, 1);
      gl.drawArrays(gl.POINTS, 0, PARTICULAS);
    };

    const laco = (agora: number) => {
      quadro = requestAnimationFrame(laco);
      if (document.hidden) return;
      if (agora - ultimo < 1000 / quadrosPorSegundo(estadoRef.current) - 2) return;
      ultimo = agora;
      desenhar(agora);
    };

    if (parado) {
      desenhar(performance.now());
      redesenharRef.current = () => desenhar(performance.now());
    } else {
      quadro = requestAnimationFrame(laco);
    }

    // No notebook, o campo acompanha um pouco o mouse (dá a sensação de
    // profundidade). No celular, não.
    let mouseFino = false;
    try {
      mouseFino = window.matchMedia('(pointer: fine)').matches;
    } catch {
      mouseFino = false;
    }
    const aoMover = (e: PointerEvent) => {
      olharAlvo[0] = (e.clientX / window.innerWidth) * 2 - 1;
      olharAlvo[1] = -((e.clientY / window.innerHeight) * 2 - 1);
    };
    if (mouseFino && !parado) window.addEventListener('pointermove', aoMover, { passive: true });

    const aoRedimensionar = () => {
      const antes = grade.colunas;
      dimensionar();
      if (gradeDoHorizonte(window.innerWidth).colunas !== antes) montarGrade();
      if (parado) desenhar(performance.now());
    };
    window.addEventListener('resize', aoRedimensionar);

    const perdeu = (e: Event) => {
      e.preventDefault();
      setSemWebgl(true);
    };
    canvas.addEventListener('webglcontextlost', perdeu);

    return () => {
      cancelAnimationFrame(quadro);
      redesenharRef.current = () => {};
      window.removeEventListener('pointermove', aoMover);
      window.removeEventListener('resize', aoRedimensionar);
      canvas.removeEventListener('webglcontextlost', perdeu);
      gl.deleteBuffer(bufChao);
      gl.deleteBuffer(bufAr);
      gl.deleteBuffer(bufMalha);
      programa.apagar();
      gl.getExtension('WEBGL_lose_context')?.loseContext();
      canvas.remove();
    };
  }, [semWebgl]);

  return (
    <div className="eden-espaco" aria-hidden="true">
      <div className="eden-espaco-brilho" style={{ color: corCss(estado) }} />
      {semWebgl ? <div className="hud-backdrop" /> : <div ref={caixaRef} />}
    </div>
  );
}
