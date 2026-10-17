// Éden: testes dos textos e conferências dos documentos.
import { describe, expect, it } from 'vitest';
import { detalhesDocumento, problemaDoArquivo, tamanhoTexto, vaiCortado } from './eden-documentos';

describe('problemaDoArquivo', () => {
  it('accepts PDF, Word, txt and md up to 10 MB', () => {
    expect(problemaDoArquivo('Contrato.PDF', 1000)).toBeNull();
    expect(problemaDoArquivo('notas.md', 10)).toBeNull();
    expect(problemaDoArquivo('foto.jpg', 10)).toMatch(/PDF/);
    expect(problemaDoArquivo('sem-extensao', 10)).toMatch(/PDF/);
    expect(problemaDoArquivo('grande.pdf', 11 * 1024 * 1024)).toMatch(/10 MB/);
    expect(problemaDoArquivo('vazio.txt', 0)).toMatch(/vazio/);
  });
});

describe('tamanhoTexto', () => {
  it('says the size in simple words', () => {
    expect(tamanhoTexto(850)).toBe('850 caracteres');
    expect(tamanhoTexto(1500)).toBe('1,5 mil caracteres');
    expect(tamanhoTexto(2000)).toBe('2 mil caracteres');
    expect(tamanhoTexto(48213)).toBe('48 mil caracteres');
  });
});

describe('detalhesDocumento', () => {
  it('shows type, pages and size', () => {
    expect(detalhesDocumento({ tipo: 'pdf', paginas: 12, caracteres: 30000, cortado: false })).toBe(
      'PDF · 12 páginas · 30 mil caracteres',
    );
    expect(detalhesDocumento({ tipo: 'docx', paginas: null, caracteres: 900, cortado: true })).toBe(
      'Word · 900 caracteres · guardado só o começo',
    );
  });
});

describe('vaiCortado', () => {
  it('splits the context budget between attached documents', () => {
    expect(vaiCortado(20000, 1)).toBe(false);
    expect(vaiCortado(20000, 2)).toBe(true);
    expect(vaiCortado(5000, 3, 30000)).toBe(false);
  });
});
