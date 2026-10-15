// Éden (Parte 2): espaços (Pessoal, LS Visuals, Clientes…) nas Configurações.
// Criar, renomear e arquivar. Arquivar esconde o espaço, sem apagar nada.
import { useEffect, useState } from 'react';
import { Archive, ArchiveRestore, Plus, Save } from 'lucide-react';
import { edenJson, useEdenOrg, type Espaco } from '../../lib/eden-org';
import { ErrorLine, GhostButton, IconButton, PrimaryButton, inputStyle } from './EdenUi';

function LinhaEspaco({ espaco, onMudou }: { espaco: Espaco; onMudou: () => void }) {
  const [nome, setNome] = useState(espaco.nome);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => setNome(espaco.nome), [espaco.nome]);

  const salvar = async (campos: Record<string, unknown>) => {
    setErro(null);
    try {
      await edenJson(`/espacos/${encodeURIComponent(espaco.id)}`, { method: 'PATCH', body: campos });
      onMudou();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  return (
    <li className="py-2" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-center gap-2">
        <input
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          maxLength={40}
          aria-label={`Nome do espaço ${espaco.nome}`}
          disabled={espaco.arquivado}
          className="flex-1 min-w-0 text-sm px-3 py-1.5 rounded-lg outline-none disabled:opacity-60"
          style={inputStyle}
        />
        {nome.trim() !== espaco.nome && !espaco.arquivado && (
          <IconButton label="Salvar nome" onClick={() => salvar({ nome })}>
            <Save size={15} />
          </IconButton>
        )}
        <IconButton
          label={espaco.arquivado ? 'Voltar a usar o espaço' : 'Arquivar o espaço'}
          onClick={() => {
            if (
              !espaco.arquivado &&
              !window.confirm(
                `Arquivar "${espaco.nome}"? Ele some das listas, mas nada é apagado (dá para voltar aqui).`,
              )
            ) {
              return;
            }
            void salvar({ arquivado: !espaco.arquivado });
          }}
        >
          {espaco.arquivado ? <ArchiveRestore size={15} /> : <Archive size={15} />}
        </IconButton>
      </div>
      <ErrorLine message={erro} />
    </li>
  );
}

export function EdenSpacesSettings() {
  const carregarEspacos = useEdenOrg((s) => s.carregarEspacos);
  const [todos, setTodos] = useState<Espaco[]>([]);
  const [novo, setNovo] = useState('');
  const [mostrarArquivados, setMostrarArquivados] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = async () => {
    try {
      const { espacos } = await edenJson<{ espacos: Espaco[] }>('/espacos?arquivados=true');
      setTodos(espacos);
      void carregarEspacos();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  useEffect(() => {
    void carregar();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const criar = async () => {
    setErro(null);
    try {
      await edenJson('/espacos', { method: 'POST', body: { nome: novo } });
      setNovo('');
      void carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  const visiveis = todos.filter((e) => mostrarArquivados || !e.arquivado);
  const temArquivados = todos.some((e) => e.arquivado);

  return (
    <div>
      <p className="text-xs mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
        Cada espaço tem suas tarefas, notas e memórias. Na conversa, o Éden usa só o espaço escolhido
        acima da caixa de mensagem.
      </p>
      <ul>
        {visiveis.map((e) => (
          <LinhaEspaco key={e.id} espaco={e} onMudou={() => void carregar()} />
        ))}
      </ul>
      {temArquivados && (
        <button
          type="button"
          onClick={() => setMostrarArquivados((v) => !v)}
          className="mt-2 text-xs underline cursor-pointer"
          style={{ color: 'var(--color-text-tertiary)' }}
        >
          {mostrarArquivados ? 'Esconder arquivados' : 'Mostrar arquivados'}
        </button>
      )}
      <div className="mt-3 flex items-center gap-2">
        <input
          value={novo}
          onChange={(e) => setNovo(e.target.value)}
          maxLength={40}
          placeholder="Novo espaço (ex.: Estudos)"
          aria-label="Nome do novo espaço"
          className="flex-1 min-w-0 text-sm px-3 py-1.5 rounded-lg outline-none"
          style={inputStyle}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && novo.trim()) void criar();
          }}
        />
        {novo.trim() ? (
          <PrimaryButton onClick={criar}>
            <Plus size={14} /> Criar
          </PrimaryButton>
        ) : (
          <GhostButton disabled>
            <Plus size={14} /> Criar
          </GhostButton>
        )}
      </div>
      <ErrorLine message={erro} />
    </div>
  );
}
