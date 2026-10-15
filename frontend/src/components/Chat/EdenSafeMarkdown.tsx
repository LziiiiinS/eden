// Éden: peças seguras para mostrar o texto escrito pela IA (resposta e página).

// Éden: imagens que a IA escreve na resposta (![...](https://...)) não são
// carregadas. Carregar faria o aparelho chamar um site de fora — e um texto
// malicioso colado na conversa poderia fazer a IA esconder dados pessoais no
// endereço da imagem. Fica só o texto, com o endereço à vista.
export function SafeImage({ src, alt }: { src?: unknown; alt?: string }) {
  const endereco = typeof src === 'string' ? src : '';
  return (
    <span
      className="inline-block text-xs px-2 py-1 rounded"
      style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-tertiary)' }}
      title={endereco}
    >
      [imagem não carregada{alt ? `: ${alt}` : ''}]
    </span>
  );
}

// Éden: links escritos pela IA. Para fora do Éden, pergunta antes de abrir e
// mostra o site — um texto malicioso colado na conversa poderia fazer a IA
// montar um link que leva dados pessoais no endereço.
export function SafeLink({ href, children }: { href?: string; children?: React.ReactNode }) {
  const destino = typeof href === 'string' ? href : '';
  let externo: URL | null = null;
  try {
    const url = new URL(destino, window.location.origin);
    if (url.origin !== window.location.origin) externo = url;
  } catch {
    externo = null;
  }
  if (!externo) {
    return <a href={destino}>{children}</a>;
  }
  const site = externo.host;
  return (
    <a
      href={destino}
      rel="noopener noreferrer nofollow"
      title={site}
      onClick={(e) => {
        e.preventDefault();
        const ok = window.confirm(
          `Abrir um site fora do Éden?\n\n${site}\n\nEste link foi escrito pela IA. Só abra se você confia nele.`,
        );
        if (ok) window.open(destino, '_blank', 'noopener,noreferrer');
      }}
    >
      {children}
      <span className="text-[11px] ml-1" style={{ color: 'var(--color-text-tertiary)' }}>
        ({site})
      </span>
    </a>
  );
}
