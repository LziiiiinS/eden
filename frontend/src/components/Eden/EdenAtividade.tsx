// Éden: atividade recente — o que foi gravado, mudado ou apagado e de qual
// aparelho veio (chave principal = notebook). Serve para conferir se um
// celular perdido fez alguma coisa.
import { useEffect, useState } from 'react';
import { edenJson } from '../../lib/eden-org';

interface Linha {
  id: number;
  quando: number;
  quem: string;
  o_que: string;
  alvo: string;
}

const NOMES: Record<string, string> = {
  'tarefa.criar': 'criou tarefa',
  'tarefa.editar': 'mudou tarefa',
  'tarefa.concluir': 'concluiu tarefa',
  'tarefa.apagar': 'apagou tarefa',
  'nota.criar': 'criou nota',
  'nota.editar': 'mudou nota',
  'nota.apagar': 'apagou nota',
  'memoria.criar': 'guardou memória',
  'memoria.editar': 'mudou memória',
  'memoria.apagar': 'apagou memória',
  'perfil.editar': 'mudou o perfil',
  'espaco.criar': 'criou espaço',
  'espaco.editar': 'mudou espaço',
  'conta.criar': 'anotou conta',
  'conta.editar': 'mudou conta',
  'conta.pagar': 'marcou conta como paga',
  'conta.reabrir': 'reabriu conta',
  'conta.apagar': 'apagou conta',
  'casa.aparelho': 'mexeu num aparelho da casa',
  'casa.rotina': 'rodou rotina da casa',
  'rotina.criar': 'criou rotina da casa',
  'rotina.editar': 'mudou rotina da casa',
  'rotina.apagar': 'apagou rotina da casa',
};

export function nomeDaAtividade(oQue: string): string {
  return NOMES[oQue] ?? oQue.replace(/[._]/g, ' ');
}

export function EdenAtividade() {
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    edenJson<{ registro: Linha[] }>('/registro?limite=12')
      .then((r) => ativo && setLinhas(r.registro))
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, []);

  if (erro) {
    return (
      <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        Não deu para carregar a atividade agora.
      </p>
    );
  }
  if (linhas === null) return null;
  if (linhas.length === 0) {
    return (
      <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
        Nada gravado ainda.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5 text-xs" aria-label="Atividade recente">
      {linhas.map((l) => (
        <li key={l.id} className="flex flex-wrap gap-x-2" style={{ color: 'var(--color-text-secondary)' }}>
          <span className="tabular-nums" style={{ color: 'var(--color-text-tertiary)' }}>
            {new Date(l.quando).toLocaleString('pt-BR', {
              day: '2-digit',
              month: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          <span style={{ color: 'var(--color-text)' }}>{nomeDaAtividade(l.o_que)}</span>
          <span className="break-all">{l.quem}</span>
        </li>
      ))}
    </ul>
  );
}
