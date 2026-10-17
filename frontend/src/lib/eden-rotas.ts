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
