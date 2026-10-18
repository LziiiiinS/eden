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
  const abrir = () => {
    // O endereço inteiro aparece (sem cortar): um link pode levar dados
    // escondidos depois do "?" (ex.: texto de um documento que enganou a IA).
    // Mostra o endereço já interpretado pelo navegador (o que vai abrir de
    // verdade), não o texto que a IA escreveu.
    const real = externo.href;
    const ok = window.confirm(
      `Abrir um site fora do Éden?\n\n${site}\n\nEndereço completo:\n${real}\n\nEste link foi escrito pela IA. Só abra se você confia nele e se o endereço não leva informações suas.`,
    );
    if (ok) window.open(real, '_blank', 'noopener,noreferrer');
  };
  // Sem href: botão do meio, "abrir em nova aba" e o toque longo do celular
  // não conseguem pular a pergunta (revisão do Codex, 18/10).
  return (
    <a
      role="link"
      tabIndex={0}
      title={site}
      style={{ cursor: 'pointer', textDecoration: 'underline' }}
      onClick={(e) => {
        e.preventDefault();
        abrir();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          abrir();
        }
      }}
    >
      {children}
      <span className="text-[11px] ml-1" style={{ color: 'var(--color-text-tertiary)' }}>
        ({site})
      </span>
    </a>
  );
}
