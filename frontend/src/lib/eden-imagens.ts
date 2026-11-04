// Éden: imagens na conversa (colar um print, escolher uma foto). O app reduz
// a imagem antes de mandar (até 1600 px, JPEG): fica leve no 4G e barata para
// a IA. A imagem não fica guardada: vai só na mensagem em que foi enviada.

export const MAX_IMAGENS = 3;
export const LADO_MAXIMO = 1600;
const QUALIDADE = 0.85;

/** Novo tamanho mantendo a proporção, com o lado maior até ``max``. */
export function medidasReduzidas(largura: number, altura: number, max = LADO_MAXIMO): { w: number; h: number } {
  if (largura <= 0 || altura <= 0) return { w: 0, h: 0 };
  const fator = Math.min(1, max / Math.max(largura, altura));
  return { w: Math.max(1, Math.round(largura * fator)), h: Math.max(1, Math.round(altura * fator)) };
}

/** O que fica escrito na conversa no lugar das imagens (o histórico e os
 * outros aparelhos não guardam a imagem). */
export function marcaDeImagens(n: number): string {
  if (n <= 0) return '';
  return n === 1 ? '[📷 1 imagem enviada]' : `[📷 ${n} imagens enviadas]`;
}

/** Arquivos de imagem de um colar (Ctrl+V) ou de uma escolha de arquivo. */
export function imagensDe(itens: ArrayLike<{ kind?: string; type: string; getAsFile?: () => File | null }> | null): File[] {
  if (!itens) return [];
  const saida: File[] = [];
  for (let i = 0; i < itens.length; i += 1) {
    const it = itens[i];
    if (!it.type.startsWith('image/')) continue;
    const arquivo = it.getAsFile ? it.getAsFile() : (it as unknown as File);
    if (arquivo) saida.push(arquivo);
  }
  return saida;
}

async function desenhar(arquivo: Blob): Promise<{ fonte: CanvasImageSource; w: number; h: number; fechar: () => void }> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(arquivo);
      return { fonte: bmp, w: bmp.width, h: bmp.height, fechar: () => bmp.close() };
    } catch {
      // alguns formatos (ex.: HEIC no Chrome) não abrem assim; tenta pelo <img>
    }
  }
  const url = URL.createObjectURL(arquivo);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error('Não consegui abrir essa imagem.'));
      el.src = url;
    });
    return { fonte: img, w: img.naturalWidth, h: img.naturalHeight, fechar: () => URL.revokeObjectURL(url) };
  } catch (e) {
    URL.revokeObjectURL(url);
    throw e;
  }
}

/** Reduz e converte para JPEG (``data:image/jpeg;base64,...``). */
export async function reduzirImagem(arquivo: Blob): Promise<string> {
  const { fonte, w, h, fechar } = await desenhar(arquivo);
  try {
    const m = medidasReduzidas(w, h);
    if (!m.w) throw new Error('Não consegui abrir essa imagem.');
    const canvas = document.createElement('canvas');
    canvas.width = m.w;
    canvas.height = m.h;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Não consegui preparar a imagem.');
    // Fundo branco: prints com transparência não ficam pretos no JPEG.
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, m.w, m.h);
    ctx.drawImage(fonte, 0, 0, m.w, m.h);
    return canvas.toDataURL('image/jpeg', QUALIDADE);
  } finally {
    fechar();
  }
}
