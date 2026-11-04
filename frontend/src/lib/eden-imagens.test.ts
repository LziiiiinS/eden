import { describe, expect, it } from 'vitest';
import { imagensDe, marcaDeImagens, medidasReduzidas } from './eden-imagens';

describe('imagens na conversa', () => {
  it('reduz mantendo a proporção', () => {
    expect(medidasReduzidas(3200, 1600)).toEqual({ w: 1600, h: 800 });
    expect(medidasReduzidas(1170, 2532)).toEqual({ w: 739, h: 1600 }); // print do iPhone
    expect(medidasReduzidas(800, 600)).toEqual({ w: 800, h: 600 }); // pequena não aumenta
    expect(medidasReduzidas(0, 10)).toEqual({ w: 0, h: 0 });
  });

  it('marca no texto da conversa', () => {
    expect(marcaDeImagens(0)).toBe('');
    expect(marcaDeImagens(1)).toBe('[📷 1 imagem enviada]');
    expect(marcaDeImagens(2)).toBe('[📷 2 imagens enviadas]');
  });

  it('pega só imagens do que foi colado', () => {
    const arquivo = { name: 'print.png' } as unknown as File;
    const itens = [
      { kind: 'string', type: 'text/plain', getAsFile: () => null },
      { kind: 'file', type: 'image/png', getAsFile: () => arquivo },
    ];
    expect(imagensDe(itens)).toEqual([arquivo]);
    expect(imagensDe(null)).toEqual([]);
  });
});
