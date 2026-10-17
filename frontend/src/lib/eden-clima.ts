// Éden (Parte 4): clima, vento e ondas (dados do Open-Meteo, pelo servidor).
import { edenJson } from './eden-org';

export interface Lugar {
  id: number;
  nome: string;
  tipo: 'cidade' | 'praia';
  latitude: number;
  longitude: number;
  principal: boolean;
}

export interface HoraClima {
  hora: string; // "2026-10-17T15:00" (hora local do lugar)
  temperatura: number | null;
  chuva_prob: number | null;
  chuva_mm: number | null;
  codigo: number | null;
  vento_kmh: number | null;
  rajada_kmh: number | null;
  vento_dir: number | null;
  ondas_m?: number | null;
  ondas_s?: number | null;
  ondas_dir?: number | null;
  swell_m?: number | null;
  swell_s?: number | null;
  swell_dir?: number | null;
}

export interface DiaClima {
  dia: string;
  codigo: number | null;
  max: number | null;
  min: number | null;
  chuva_mm: number | null;
  chuva_prob: number | null;
  vento_kmh: number | null;
  rajada_kmh: number | null;
  vento_dir: number | null;
}

export interface Previsao {
  lugar: Lugar;
  horas: HoraClima[];
  dias: DiaClima[];
  mar: boolean;
  atualizado_em: number;
  fonte: string;
}

export interface ResultadoBusca {
  nome: string;
  regiao: string;
  latitude: number;
  longitude: number;
}

const RUMOS = ['N', 'NE', 'L', 'SE', 'S', 'SO', 'O', 'NO'];

/** De onde vem o vento/onda: 0° = N, 90° = L. */
export function rumo(graus: number | null | undefined): string {
  if (graus === null || graus === undefined) return '–';
  return RUMOS[Math.floor((((graus % 360) + 360) % 360 + 22.5) / 45) % 8];
}

export function nos(kmh: number | null | undefined): number | null {
  return kmh === null || kmh === undefined ? null : Math.round(kmh / 1.852);
}

export function numero(valor: number | null | undefined, casas = 0): string {
  if (valor === null || valor === undefined) return '–';
  return valor.toFixed(casas).replace('.', ',');
}

const TEMPO: Record<number, string> = {
  0: 'céu limpo', 1: 'quase limpo', 2: 'parcialmente nublado', 3: 'nublado',
  45: 'neblina', 48: 'neblina', 51: 'garoa fraca', 53: 'garoa', 55: 'garoa forte',
  56: 'garoa congelante', 57: 'garoa congelante', 61: 'chuva fraca', 63: 'chuva',
  65: 'chuva forte', 66: 'chuva congelante', 67: 'chuva congelante', 71: 'neve fraca',
  73: 'neve', 75: 'neve forte', 77: 'grãos de neve', 80: 'pancadas fracas',
  81: 'pancadas de chuva', 82: 'pancadas fortes', 85: 'neve', 86: 'neve forte',
  95: 'trovoada', 96: 'trovoada com granizo', 99: 'trovoada com granizo',
};

export function descricaoTempo(codigo: number | null | undefined): string {
  return codigo === null || codigo === undefined ? '' : TEMPO[codigo] ?? '';
}

/** "-27,5967, -48,5492" ou "-27.5967 -48.5492" (como o Google Maps copia). */
export function lerCoordenadas(texto: string): { latitude: number; longitude: number } | null {
  const numeros = texto.trim().match(/-?\d+(?:[.,]\d+)?/g);
  if (!numeros || numeros.length !== 2) return null;
  const [lat, lon] = numeros.map((n) => Number(n.replace(',', '.')));
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return null;
  }
  return { latitude: lat, longitude: lon };
}

/** "sáb 18" a partir de "2026-10-18". */
export function rotuloDia(dia: string): string {
  const [a, m, d] = dia.split('-').map(Number);
  const nomes = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
  return `${nomes[new Date(a, m - 1, d).getDay()]} ${d}`;
}

/** Cor de fundo do vento em nós (como o Windguru: mais forte, mais quente). */
export function corVento(knots: number | null): string {
  if (knots === null) return 'transparent';
  if (knots < 8) return 'transparent';
  if (knots < 12) return 'rgba(80, 200, 120, 0.25)';
  if (knots < 16) return 'rgba(240, 200, 60, 0.30)';
  if (knots < 22) return 'rgba(245, 140, 50, 0.35)';
  return 'rgba(230, 70, 70, 0.40)';
}

export const statusClima = () =>
  edenJson<{ ligado: boolean; lugares: Lugar[]; fonte: string }>('/clima/status');
export const ligarClima = (ligado: boolean) =>
  edenJson<{ ligado: boolean }>('/clima/ligar', { method: 'POST', body: { ligado } });
export const buscarLugar = (nome: string) =>
  edenJson<{ resultados: ResultadoBusca[] }>(`/clima/buscar?nome=${encodeURIComponent(nome)}`);
export const criarLugar = (dados: Omit<Lugar, 'id' | 'principal'>) =>
  edenJson<{ lugar: Lugar }>('/clima/lugares', { method: 'POST', body: dados });
export const apagarLugar = (id: number) =>
  edenJson<{ ok: boolean }>(`/clima/lugares/${id}`, { method: 'DELETE' });
export const tornarPrincipal = (id: number) =>
  edenJson<{ lugar: Lugar }>(`/clima/lugares/${id}/principal`, { method: 'POST' });
export const previsaoDoLugar = (id: number, atualizar = false) =>
  edenJson<Previsao>(`/clima/previsao/${id}${atualizar ? '?atualizar=true' : ''}`);
