// Éden: avisos de lembrete no aparelho (Web Push).
//
// Cada aparelho ativa os seus avisos (o navegador pede permissão). O servidor
// guarda o endereço do serviço de avisos do aparelho e, na hora do lembrete,
// manda o aviso cifrado. No iPhone, só funciona com o Éden instalado na tela
// de início (Safari → Compartilhar → Adicionar à Tela de Início).
import { edenJson } from './eden-org';

export type SituacaoPush = 'sem-suporte' | 'instalar-iphone' | 'negado' | 'desligado' | 'ligado';

export function ehIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

export function instaladoComoApp(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia?.('(display-mode: standalone)')?.matches === true ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function pushSuportado(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

export function b64urlParaBytes(texto: string): Uint8Array<ArrayBuffer> {
  const base64 = texto.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (texto.length % 4)) % 4);
  const bin = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function mesmaChave(sub: PushSubscription, chave: Uint8Array): boolean {
  const atual = sub.options?.applicationServerKey;
  if (!atual) return false;
  const a = new Uint8Array(atual);
  return a.length === chave.length && a.every((v, i) => v === chave[i]);
}

async function registro(): Promise<ServiceWorkerRegistration | null> {
  if (!pushSuportado()) return null;
  // Em desenvolvimento não há service worker: não espera para sempre.
  const pronto = navigator.serviceWorker.ready;
  const tempo = new Promise<null>((resolve) => setTimeout(() => resolve(null), 8000));
  return (await Promise.race([pronto, tempo])) as ServiceWorkerRegistration | null;
}

export async function situacaoPush(): Promise<SituacaoPush> {
  if (ehIOS() && !instaladoComoApp()) return 'instalar-iphone';
  if (!pushSuportado()) return 'sem-suporte';
  if (Notification.permission === 'denied') return 'negado';
  const reg = await registro();
  if (!reg) return 'sem-suporte';
  const sub = await reg.pushManager.getSubscription();
  return sub && Notification.permission === 'granted' ? 'ligado' : 'desligado';
}

function nomeAparelho(): string {
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  if (/iPhone/.test(ua)) return 'iPhone';
  if (/iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return 'iPad';
  if (/Android/.test(ua)) return 'Android';
  if (/Windows/.test(ua)) return 'Windows';
  if (/Mac/.test(ua)) return 'Mac';
  return 'Aparelho';
}

async function inscrever(reg: ServiceWorkerRegistration): Promise<void> {
  const { chave } = await edenJson<{ chave: string }>('/push/chave');
  const bytes = b64urlParaBytes(chave);
  let sub = await reg.pushManager.getSubscription();
  if (sub && !mesmaChave(sub, bytes)) {
    await sub.unsubscribe();
    sub = null;
  }
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes });
  }
  const json = sub.toJSON();
  await edenJson('/push/inscricoes', {
    method: 'POST',
    body: { endpoint: json.endpoint, keys: json.keys, nome: nomeAparelho() },
  });
}

/** Pede permissão (precisa ser num toque da pessoa) e ativa os avisos. */
export async function ativarPush(): Promise<void> {
  if (!pushSuportado()) throw new Error('Este navegador não aceita avisos.');
  const permissao = await Notification.requestPermission();
  if (permissao !== 'granted') {
    throw new Error('Os avisos não foram permitidos. Dá para liberar nas configurações do navegador.');
  }
  const reg = await registro();
  if (!reg) throw new Error('O app ainda não terminou de carregar. Feche, abra de novo e tente outra vez.');
  await inscrever(reg);
}

export async function desativarPush(): Promise<void> {
  const reg = await registro();
  const sub = await reg?.pushManager.getSubscription();
  if (!sub) return;
  await edenJson('/push/cancelar', { method: 'POST', body: { endpoint: sub.endpoint } }).catch(() => {});
  await sub.unsubscribe();
}

export async function testarPush(): Promise<{ enviados: number; falhas: number; removidos: number }> {
  return edenJson('/push/teste', { method: 'POST', body: {} });
}

/**
 * Ao abrir o app: se os avisos já estavam ativos, confere que o servidor
 * conhece este aparelho com a chave atual (ex.: depois de trocar de servidor
 * ou restaurar um backup). Não pede permissão.
 */
export async function sincronizarPush(): Promise<void> {
  try {
    if (!pushSuportado() || Notification.permission !== 'granted') return;
    const reg = await registro();
    if (!reg || !(await reg.pushManager.getSubscription())) return;
    await inscrever(reg);
  } catch {
    // Melhor esforço.
  }
}
