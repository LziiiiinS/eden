// Éden (Parte 4): rotas e trânsito (TomTom, pelo servidor).
import { edenJson } from './eden-org';

export interface Ponto {
  nome: string;
  latitude: number;
  longitude: number;
}

export interface Trajeto {
  id: number;
  nome: string;
  origem: Ponto;
  destino: Ponto;
}

export interface ResultadoEndereco extends Ponto {
  endereco: string;
}

export interface TempoTrajeto {
  trajeto: Trajeto;
  segundos?: number;
  sem_transito_s?: number | null;
  atraso_s?: number;
  metros?: number | null;
  chegada?: string | null;
  calculado_em?: number;
  erro?: string;
}

/** "28 min", "1 h 07 min". */
export function minutos(segundos: number | null | undefined): string {
  if (segundos === null || segundos === undefined) return '–';
  const m = Math.max(1, Math.round(segundos / 60));
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

/** "28 min agora · +8 min de trânsito · 14,2 km · chega 17:28". */
export function resumoTempo(t: TempoTrajeto): string {
  if (t.erro) return t.erro;
  const partes = [`${minutos(t.segundos)} agora`];
  if (t.atraso_s && t.atraso_s >= 60) partes.push(`+${minutos(t.atraso_s)} de trânsito`);
  if (t.metros) partes.push(`${(t.metros / 1000).toFixed(1).replace('.', ',')} km`);
  if (t.chegada) partes.push(`chega ${t.chegada.slice(11, 16)}`);
  return partes.join(' · ');
}

/** Coordenadas coladas do Google Maps ("-22.97, -43.18"). */
export function lerCoordenadas(texto: string): { latitude: number; longitude: number } | null {
  const numeros = texto.trim().match(/^\s*(-?\d+(?:[.,]\d+)?)\s*[, ;]\s*(-?\d+(?:[.,]\d+)?)\s*$/);
  if (!numeros) return null;
  const lat = Number(numeros[1].replace(',', '.'));
  const lon = Number(numeros[2].replace(',', '.'));
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { latitude: lat, longitude: lon };
}

export const statusRotas = () =>
  edenJson<{ configurado: boolean; trajetos: Trajeto[]; fonte: string }>('/rotas/status');
export const buscarEndereco = (q: string) =>
  edenJson<{ resultados: ResultadoEndereco[] }>(`/rotas/buscar?q=${encodeURIComponent(q)}`);
export const criarTrajeto = (dados: { nome?: string; origem: Ponto; destino: Ponto }) =>
  edenJson<{ trajeto: Trajeto }>('/rotas/trajetos', { method: 'POST', body: dados });
export const apagarTrajeto = (id: number) =>
  edenJson<{ ok: boolean }>(`/rotas/trajetos/${id}`, { method: 'DELETE' });
export const temposTrajetos = (atualizar = false) =>
  edenJson<{ configurado: boolean; tempos: TempoTrajeto[] }>(`/rotas/tempos${atualizar ? '?atualizar=true' : ''}`);

// ── caminhos (alternativas) ──────────────────────────────────────────────

export interface Caminho {
  segundos: number;
  sem_transito_s?: number | null;
  atraso_s?: number;
  metros?: number | null;
  chegada?: string | null;
  vias: string[];
}

/** "28 min · +8 min de trânsito · 14,2 km · via Av. das Américas, Av. Ayrton Senna". */
export function resumoCaminho(c: Caminho): string {
  const partes = [minutos(c.segundos)];
  if (c.atraso_s && c.atraso_s >= 60) partes.push(`+${minutos(c.atraso_s)} de trânsito`);
  if (c.metros) partes.push(`${(c.metros / 1000).toFixed(1).replace('.', ',')} km`);
  if (c.vias.length) partes.push(`via ${c.vias.join(', ')}`);
  return partes.join(' · ');
}

/** Quanto o caminho é mais lento que o mais rápido ("+4 min"), ou "". */
export function diferenca(c: Caminho, maisRapido: Caminho): string {
  const extra = c.segundos - maisRapido.segundos;
  return extra >= 60 ? `+${minutos(extra)}` : '';
}

export const caminhosDoTrajeto = (id: number, atualizar = false) =>
  edenJson<{ rotas: Caminho[]; calculado_em: number }>(
    `/rotas/caminhos?trajeto=${id}${atualizar ? '&atualizar=true' : ''}`,
  );
export const caminhosEntre = (origem: string, destino: string) =>
  edenJson<{ rotas: Caminho[]; calculado_em: number }>(
    `/rotas/caminhos?origem=${encodeURIComponent(origem)}&destino=${encodeURIComponent(destino)}`,
  );

// ── localização do aparelho (opcional, só para perguntas de caminho) ─────

const CHAVE_LOCAL = 'eden.rotas.usarLocal';

export function usarLocalNaConversa(): boolean {
  try {
    return window.localStorage.getItem(CHAVE_LOCAL) === '1';
  } catch {
    return false;
  }
}

export function definirUsarLocal(ligado: boolean): void {
  try {
    if (ligado) window.localStorage.setItem(CHAVE_LOCAL, '1');
    else window.localStorage.removeItem(CHAVE_LOCAL);
  } catch {
    // sem armazenamento: fica desligado
  }
}

function semAcento(texto: string): string {
  return texto.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

// Igual ao _ASSUNTO de src/openjarvis/eden/rotas.py: a localização só vai
// quando a mensagem parece pergunta de caminho ou trânsito.
const ASSUNTO =
  /\b(transito|rota\w*|caminho\w*|engarraf\w*|congestion\w*|trajet\w*|demor\w*|chegar|chego|chegada|sair|saio|saida|distancia|estrada\w*|quanto tempo|de carro|vou pr\w*|ir pr\w*|ir para|ir ao|ir a)\b/;

export function pareceRota(texto: string): boolean {
  return ASSUNTO.test(semAcento(texto));
}

/** "lat,lon" com 4 casas (~10 m), ou null se não der (sem permissão etc.). */
export function localDoAparelho(esperaMs = 5000): Promise<string | null> {
  return new Promise((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve(null);
      return;
    }
    let feito = false;
    const fim = (valor: string | null) => {
      if (!feito) {
        feito = true;
        resolve(valor);
      }
    };
    const relogio = window.setTimeout(() => fim(null), esperaMs + 500);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        window.clearTimeout(relogio);
        fim(`${pos.coords.latitude.toFixed(4)},${pos.coords.longitude.toFixed(4)}`);
      },
      () => {
        window.clearTimeout(relogio);
        fim(null);
      },
      { enableHighAccuracy: false, timeout: esperaMs, maximumAge: 60_000 },
    );
  });
}
