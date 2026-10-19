// Éden: os desenhos 3D (shaders WebGL 1) do núcleo e do horizonte.
// Ficam aqui, separados dos componentes, para dar para testar fora do app.

/** Um retângulo que cobre o quadro; o desenho todo é feito por pixel. */
export const NUCLEO_VERTICE = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

/**
 * Núcleo: esfera de vidro com a superfície ondulando (raymarching), uma luz
 * por dentro que aparece pelo vidro, dois anéis tracejados em volta (que
 * passam por trás e pela frente da esfera) e um halo.
 * Saída com alfa pré-multiplicado.
 */
export const NUCLEO_FRAGMENTO = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 u_res;
uniform float u_t;
uniform vec3 u_cor;
uniform float u_energia;
// u_giro: quanto os anéis já giraram (soma da velocidade de cada estado).
uniform float u_giro;

const float RAIO = 0.7;

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

// Ruído "líquido": um ruído desloca o outro.
float campo(vec3 p) {
  vec3 q = p * 1.45 + vec3(0.0, u_t * 0.3, u_t * 0.45);
  float w = ruido(q);
  return ruido(q * 1.5 + w * 1.4 - vec3(u_t * 0.4, 0.0, 0.0));
}

float mapa(vec3 p) {
  return length(p) - RAIO - (0.03 + 0.12 * u_energia) * campo(p);
}

vec3 normal(vec3 p) {
  vec2 e = vec2(0.004, 0.0);
  return normalize(vec3(
    mapa(p + e.xyy) - mapa(p - e.xyy),
    mapa(p + e.yxy) - mapa(p - e.yxy),
    mapa(p + e.yyx) - mapa(p - e.yyx)));
}

vec3 girarY(vec3 v, float a) {
  float c = cos(a);
  float s = sin(a);
  return vec3(c * v.x + s * v.z, v.y, -s * v.x + c * v.z);
}

// Anel tracejado no plano que passa pelo centro com a normal n.
// Devolve (alfa, distância até o anel).
vec2 anel(vec3 ro, vec3 rd, vec3 n, float r, float voltas, float vel, float px) {
  float den = dot(rd, n);
  if (abs(den) < 0.0001) return vec2(0.0, 100.0);
  float t = -dot(ro, n) / den;
  if (t <= 0.0) return vec2(0.0, 100.0);
  vec3 p = ro + rd * t;
  float w = max(0.014, 1.3 * px * t);
  float linha = (1.0 - smoothstep(w * 0.35, w, abs(length(p) - r))) * (0.014 / w + 0.3);
  vec3 e1 = normalize(cross(n, vec3(0.31, 0.95, 0.07)));
  vec3 e2 = cross(n, e1);
  float ang = atan(dot(p, e2), dot(p, e1));
  float f = fract(ang / 6.2831853 * voltas + u_giro * vel);
  float traco = smoothstep(0.0, 0.06, f) * (1.0 - smoothstep(0.5, 0.58, f));
  return vec2(clamp(linha * mix(0.3, 1.0, traco), 0.0, 1.0), t);
}

void main() {
  float menor = min(u_res.x, u_res.y);
  vec2 uv = (gl_FragCoord.xy * 2.0 - u_res) / menor;
  float px = 2.0 / menor / 2.4;
  vec3 ro = vec3(0.0, 0.0, 3.9);
  vec3 rd = normalize(vec3(uv, -2.4));
  // Vista um pouco de cima, girando devagar.
  float inc = -0.18;
  ro.yz = mat2(cos(inc), -sin(inc), sin(inc), cos(inc)) * ro.yz;
  rd.yz = mat2(cos(inc), -sin(inc), sin(inc), cos(inc)) * rd.yz;
  float a = u_t * 0.2;
  ro = girarY(ro, a);
  rd = girarY(rd, a);

  // Só procura a superfície dentro da esfera que a envolve.
  float b = dot(ro, rd);
  float c = dot(ro, ro) - 1.0;
  float h = b * b - c;
  bool bateu = false;
  float t = 100.0;
  if (h > 0.0) {
    float sai = -b + sqrt(h);
    t = -b - sqrt(h);
    for (int i = 0; i < 40; i++) {
      float d = mapa(ro + rd * t);
      if (d < 0.002) { bateu = true; break; }
      t += d * 0.8;
      if (t > sai) break;
    }
    if (!bateu) t = 100.0;
  }

  // Luz de dentro: o quanto o raio passa perto do centro.
  vec3 perto = ro - rd * b;
  float nucleo = exp(-dot(perto, perto) * 5.0);
  vec3 corDentro = mix(u_cor, vec3(1.0), 0.5) * nucleo * (1.3 + 0.9 * u_energia)
      + u_cor * 0.18;

  float raio = length(uv);
  float halo = exp(-3.6 * max(raio - 0.44, 0.0)) * (0.24 + 0.45 * u_energia)
      * (1.0 - smoothstep(0.72, 1.0, raio));
  vec4 cor = vec4(u_cor * halo * 0.8, halo * 0.8);

  if (bateu) {
    vec3 p = ro + rd * t;
    vec3 n = normal(p);
    vec3 l1 = normalize(vec3(0.6, 0.8, 0.5));
    vec3 l2 = normalize(vec3(-0.7, -0.4, 0.3));
    float dif = max(dot(n, l1), 0.0);
    float dif2 = max(dot(n, l2), 0.0);
    float brilho = pow(max(dot(n, normalize(l1 - rd)), 0.0), 48.0);
    float borda = pow(1.0 - max(dot(n, -rd), 0.0), 2.2);
    vec3 cor2 = u_cor.zxy * 0.55 + vec3(0.28);
    vec3 tinta = mix(u_cor, cor2, 0.35 * borda + 0.12 * sin(p.y * 6.0 + u_t));
    float veios = smoothstep(0.55, 0.95, campo(p * 1.3));
    vec3 vidro = tinta * (0.08 + 0.42 * dif + 0.14 * dif2)
        + tinta * borda * 1.5
        + vec3(1.0) * brilho * 0.6
        + u_cor * veios * (0.12 + 0.35 * u_energia);
    float opaco = clamp(0.32 + 0.68 * borda, 0.0, 1.0);
    cor = vec4(vidro * opaco + corDentro * (1.0 - opaco), 1.0);
  }

  // Anéis: na frente da esfera aparecem inteiros; atrás, quase somem.
  vec3 n1 = girarY(normalize(vec3(0.0, 1.0, 0.8)), u_t * 0.15);
  vec3 n2 = girarY(normalize(vec3(0.75, 1.0, -0.85)), -u_t * 0.11);
  vec2 a1 = anel(ro, rd, n1, 1.2, 9.0, 1.0, px);
  vec2 a2 = anel(ro, rd, n2, 1.0, 5.0, -1.6, px);
  float f1 = a1.x * (a1.y < t ? 1.0 : 0.12);
  float f2 = a2.x * (a2.y < t ? 0.7 : 0.1);
  vec3 corAnel = mix(u_cor, vec3(1.0), 0.3);
  cor = vec4(corAnel * f1, f1) + cor * (1.0 - f1);
  cor = vec4(corAnel * f2, f2) + cor * (1.0 - f2);

  gl_FragColor = cor;
}
`;

/**
 * Horizonte: um campo de pontos de luz em perspectiva, como um gramado de
 * luz que vai até o horizonte. As ondas saem do ponto embaixo do núcleo
 * (como som na água) e ficam mais fortes quando o Éden ouve ou fala.
 * u_modo 0 = o chão; 1 = partículas soltas no ar.
 */
export const HORIZONTE_VERTICE = `
attribute vec2 a_grade;
attribute float a_semente;
uniform float u_t;
uniform float u_energia;
uniform float u_ritmo;
uniform float u_fase;
uniform vec2 u_res;
uniform vec2 u_olhar;
uniform float u_escala;
uniform float u_modo;
uniform float u_largura;
varying float v_alfa;
varying float v_brilho;

void main() {
  vec3 p;
  float onda = 0.0;
  if (u_modo < 0.5) {
    float x = (a_grade.x - 0.5) * u_largura + (a_semente - 0.5) * 0.012 * u_largura;
    float z = 2.0 - a_grade.y * 24.0 + (fract(a_semente * 7.31) - 0.5) * 0.2;
    float d = length(vec2(x, z + 4.0));
    onda = sin(d * 1.5 - u_fase) * exp(-d * 0.11);
    float base = sin(x * 0.33 + u_t * 0.22) * 0.22 + cos(z * 0.28 - u_t * 0.16) * 0.22;
    p = vec3(x, -1.45 + base * 0.6 + onda * (0.06 + 0.5 * u_energia), z);
  } else {
    float x = (a_grade.x - 0.5) * u_largura * 0.8;
    float z = 1.0 - a_grade.y * 18.0;
    float y = mod(a_semente * 3.7 + u_t * 0.04, 3.2) - 1.3;
    p = vec3(x + sin(u_t * 0.2 + a_semente * 6.28) * 0.2, y, z);
  }

  vec3 cam = vec3(u_olhar.x * 0.7, 0.3 + u_olhar.y * 0.18, 4.0);
  vec3 alvo = vec3(0.0, -1.5, -6.0);
  vec3 f = normalize(alvo - cam);
  vec3 r = normalize(cross(f, vec3(0.0, 1.0, 0.0)));
  vec3 u = cross(r, f);
  vec3 rel = p - cam;
  vec3 v = vec3(dot(rel, r), dot(rel, u), dot(rel, f));
  if (v.z < 0.2) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    gl_PointSize = 0.0;
    v_alfa = 0.0;
    v_brilho = 0.0;
    return;
  }
  float foco = 1.9;
  float aspecto = u_res.x / u_res.y;
  gl_Position = vec4(v.x * foco / max(aspecto, 0.0001), v.y * foco, 0.0, v.z);

  float perto = 1.0 - smoothstep(6.0, 28.0, v.z);
  float lados = 1.0 - smoothstep(0.33 * u_largura, 0.5 * u_largura, abs(p.x));
  if (u_modo < 0.5) {
    v_brilho = 0.7 + 0.8 * max(onda, 0.0) * (0.3 + u_energia);
    v_alfa = perto * lados * smoothstep(0.5, 3.0, v.z);
    gl_PointSize = clamp(u_escala * (7.0 + 6.0 * max(onda, 0.0) * u_energia) * 2.4 / v.z, 1.5, 10.0 * u_escala);
  } else {
    v_brilho = 0.6 + 0.4 * sin(u_t * 1.3 + a_semente * 40.0);
    v_alfa = perto * lados * 0.55 * smoothstep(-1.3, -0.6, p.y) * (1.0 - smoothstep(1.2, 1.9, p.y));
    gl_PointSize = clamp(u_escala * 9.0 / v.z, 1.0, 6.0 * u_escala);
  }
}
`;

export const HORIZONTE_FRAGMENTO = `
precision mediump float;
uniform vec3 u_cor;
uniform float u_claro;
uniform float u_intensidade;
uniform float u_linha;
varying float v_alfa;
varying float v_brilho;

void main() {
  float a;
  vec3 cor = u_cor;
  if (u_linha > 0.5) {
    // A malha (as linhas entre os pontos), bem fraquinha.
    a = v_alfa * (0.1 + 0.12 * (v_brilho - 0.7)) * u_intensidade;
  } else {
    vec2 c = gl_PointCoord - 0.5;
    float r = length(c);
    float disco = 1.0 - smoothstep(0.08, 0.5, r);
    disco *= disco;
    a = disco * v_alfa * v_brilho * u_intensidade;
    cor = mix(u_cor, vec3(1.0), 0.35 * (1.0 - smoothstep(0.0, 0.22, r)));
  }
  if (u_claro > 0.5) {
    cor = u_cor * 0.35;
    a = min(a * 1.1, 1.0);
  }
  a = clamp(a, 0.0, 1.0);
  gl_FragColor = vec4(cor * a, a);
}
`;
