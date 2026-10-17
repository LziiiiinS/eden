// Éden (Parte 4): Notion nas Configurações. A chave fica no .env do
// servidor; aqui a pessoa só escolhe a página onde o Éden salva as folhas.
import { useCallback, useEffect, useState } from 'react';
import { BookOpen, Unlink } from 'lucide-react';
import { GhostButton } from './EdenUi';
import { EdenNotionPicker } from './EdenNotionPicker';
import { escolherPaiNotion, esquecerPaiNotion, statusNotion, type StatusNotion } from '../../lib/eden-notion';

const cor2 = { color: 'var(--color-text-secondary)' };
const cor3 = { color: 'var(--color-text-tertiary)' };

export function EdenNotionSettings() {
  const [status, setStatus] = useState<StatusNotion | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [trocando, setTrocando] = useState(false);

  const carregar = useCallback(() => {
    statusNotion()
      .then((s) => {
        setStatus(s);
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  if (status === null) {
    return <p className="text-xs" style={erro ? { color: 'var(--color-error)' } : cor3}>{erro ?? 'Carregando…'}</p>;
  }

  if (!status.configurado) {
    return (
      <div className="flex flex-col gap-2 text-sm" style={cor2}>
        <p>
          <strong>Ainda não configurado.</strong> Com o Notion ligado, dá para trazer uma página do Notion para a
          conversa e salvar as folhas do Éden como páginas novas.
        </p>
        <ol className="list-decimal ml-5 flex flex-col gap-1 text-xs">
          <li>
            Em notion.so/profile/integrations, crie uma conexão <strong>interna</strong> chamada "Éden". Em
            Capacidades, deixe só <strong>Ler conteúdo</strong> e <strong>Inserir conteúdo</strong> (o Notion já vem
            com "Atualizar conteúdo" marcado: desmarque).
          </li>
          <li>
            Copie a chave secreta e cole no <code>.env</code> do Éden, na linha <code>NOTION_API_KEY=</code> (sem{' '}
            <code>#</code>, sem espaços). Rode o iniciar-eden.
          </li>
          <li>No Notion, em cada página que o Éden pode ver: ••• → Conexões → Éden.</li>
        </ol>
      </div>
    );
  }

  const escolher = async (id: string) => {
    setErro(null);
    try {
      await escolherPaiNotion(id);
      setTrocando(false);
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const esquecer = async () => {
    setErro(null);
    try {
      await esquecerPaiNotion();
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <div className="flex flex-col gap-2 text-sm" style={cor2}>
      <p className="flex items-center gap-1.5">
        <BookOpen size={14} style={{ color: 'var(--color-accent)' }} />
        Notion ligado. O Éden só vê as páginas compartilhadas com a conexão dele.
      </p>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span style={cor3}>Página onde o Éden salva:</span>
        {status.pai ? (
          <strong style={{ color: 'var(--color-text)' }}>{status.pai.titulo}</strong>
        ) : (
          <span>nenhuma (o botão "Salvar no Notion" aparece depois de escolher)</span>
        )}
        <GhostButton onClick={() => setTrocando((v) => !v)}>{status.pai ? 'Trocar' : 'Escolher'}</GhostButton>
        {status.pai && (
          <GhostButton onClick={() => void esquecer()}>
            <Unlink size={12} /> Tirar
          </GhostButton>
        )}
      </div>
      {trocando && <EdenNotionPicker acao="Usar esta" onEscolher={(p) => escolher(p.id)} />}
      <p className="text-[11px]" style={cor3}>
        O Éden cria páginas novas dentro dessa página; não muda nem apaga páginas que já existem.
      </p>
      {erro && (
        <p role="alert" className="text-xs" style={{ color: 'var(--color-error)' }}>
          {erro}
        </p>
      )}
    </div>
  );
}
