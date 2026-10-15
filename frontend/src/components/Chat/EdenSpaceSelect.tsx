// Éden (Parte 2): em qual espaço a conversa acontece (Pessoal, LS Visuals,
// Clientes…). O Éden usa as tarefas, notas e memórias desse espaço.
import { useEffect } from 'react';
import { Layers } from 'lucide-react';
import { useEdenOrg } from '../../lib/eden-org';

interface Props {
  disabled?: boolean;
  /** Texto antes da lista (padrão: "Espaço"). */
  label?: string;
}

export function EdenSpaceSelect({ disabled = false, label = 'Espaço' }: Props) {
  const espacos = useEdenOrg((s) => s.espacos);
  const carregado = useEdenOrg((s) => s.carregado);
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const setEspacoAtivo = useEdenOrg((s) => s.setEspacoAtivo);
  const carregarEspacos = useEdenOrg((s) => s.carregarEspacos);

  useEffect(() => {
    if (!carregado) void carregarEspacos();
  }, [carregado, carregarEspacos]);

  if (espacos.length === 0) return null;

  return (
    <label
      className="inline-flex items-center gap-1.5 text-xs"
      style={{ color: 'var(--color-text-tertiary)' }}
    >
      <Layers size={12} />
      <span>{label}:</span>
      <select
        value={espacoAtivo}
        disabled={disabled}
        onChange={(e) => setEspacoAtivo(e.target.value)}
        aria-label="Espaço ativo"
        className="text-xs px-2 py-1 rounded-full outline-none cursor-pointer disabled:cursor-default disabled:opacity-60"
        style={{
          background: 'var(--color-bg-secondary)',
          color: 'var(--color-text-secondary)',
          border: '1px solid var(--color-border)',
        }}
      >
        {espacos.map((e) => (
          <option key={e.id} value={e.id}>
            {e.nome}
          </option>
        ))}
      </select>
    </label>
  );
}
