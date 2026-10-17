// Éden (Parte 2): resumo do dia — atrasadas, hoje, próximos dias, feitas e
// notas fixadas. Montado pelo servidor, sem usar IA (não gasta nada). O botão
// "Pedir um plano ao Éden" leva o pedido para a conversa.
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { CalendarCheck, CalendarDays, CloudSun, MessageSquare, Pin } from 'lucide-react';
import { ondasDoDia, previsaoDoLugar, resumoDoDia, statusClima } from '../lib/eden-clima';
import { EdenSpaceSelect } from '../components/Chat/EdenSpaceSelect';
import { Badge, EdenPage, EdenSection, Empty, ErrorLine, PrimaryButton } from '../components/Eden/EdenUi';
import { LinhaTarefa } from './EdenTasksPage';
import { edenJson, nomeEspaco, useEdenOrg, type ResumoHoje } from '../lib/eden-org';
import { eventosDoDia, horarioEvento, type EventoAgenda } from '../lib/eden-agenda';

function saudacao(agora: Date): string {
  const h = agora.getHours();
  if (h < 12) return 'Bom dia';
  if (h < 18) return 'Boa tarde';
  return 'Boa noite';
}

// Éden (Parte 4): uma linha de clima do lugar principal e das praias (só se
// o clima estiver ligado; usa a previsão guardada no servidor).
function ClimaDoDia() {
  const [linhas, setLinhas] = useState<{ nome: string; texto: string }[]>([]);

  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const s = await statusClima();
        if (!s.ligado || s.lugares.length === 0) return;
        const principal = s.lugares.find((l) => l.principal) ?? s.lugares[0];
        const praias = s.lugares.filter((l) => l.tipo === 'praia' && l.id !== principal.id).slice(0, 2);
        const saida: { nome: string; texto: string }[] = [];
        for (const lugar of [principal, ...praias]) {
          const p = await previsaoDoLugar(lugar.id);
          const dia = p.dias[0];
          if (!dia) continue;
          const ondas = ondasDoDia(p);
          saida.push({
            nome: lugar.nome,
            texto: lugar.tipo === 'praia' && ondas ? `${ondas} · ${resumoDoDia(dia)}` : resumoDoDia(dia),
          });
        }
        if (ativo) setLinhas(saida);
      } catch {
        // Sem clima agora: a página Hoje segue sem essa linha.
      }
    })();
    return () => {
      ativo = false;
    };
  }, []);

  if (linhas.length === 0) return null;
  return (
    <ul className="flex flex-col gap-0.5 text-xs -mt-1" aria-label="Clima de hoje">
      {linhas.map((l) => (
        <li key={l.nome} style={{ color: 'var(--color-text-secondary)' }}>
          <CloudSun size={12} className="inline mr-1 -mt-0.5" />
          <span style={{ color: 'var(--color-text)' }}>{l.nome}:</span> {l.texto}
        </li>
      ))}
    </ul>
  );
}

export const PEDIDO_PLANO =
  'Monte um plano simples para o meu dia com base nas minhas tarefas: o que fazer primeiro, o que pode esperar e o que está atrasado.';

export function EdenTodayPage() {
  const navigate = useNavigate();
  const espacos = useEdenOrg((s) => s.espacos);
  const espacoAtivo = useEdenOrg((s) => s.espacoAtivo);
  const [soAtivo, setSoAtivo] = useState(false);
  const [resumo, setResumo] = useState<ResumoHoje | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  // Éden (Parte 3): eventos de hoje da Google Agenda (se estiver ligada).
  const [agenda, setAgenda] = useState<EventoAgenda[] | null>(null);

  const carregarAgenda = useCallback(() => {
    eventosDoDia()
      .then((r) => setAgenda(r.conectado ? r.eventos : null))
      .catch(() => setAgenda(null));
  }, []);

  useEffect(() => {
    carregarAgenda();
    window.addEventListener('focus', carregarAgenda);
    return () => window.removeEventListener('focus', carregarAgenda);
  }, [carregarAgenda]);

  const carregar = useCallback(() => {
    const q = soAtivo ? `?espaco=${encodeURIComponent(espacoAtivo)}` : '';
    edenJson<ResumoHoje>(`/hoje${q}`)
      .then((r) => {
        setResumo(r);
        setErro(null);
      })
      .catch((e) => setErro((e as Error).message));
  }, [soAtivo, espacoAtivo]);

  useEffect(() => {
    carregar();
    const onFocus = () => carregar();
    window.addEventListener('eden-org-mudou', carregar);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('eden-org-mudou', carregar);
      window.removeEventListener('focus', onFocus);
    };
  }, [carregar]);

  const agora = new Date();
  const dataLonga = agora.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });
  const mostrarEspaco = !soAtivo;
  const total = resumo ? resumo.atrasadas.length + resumo.hoje.length : 0;

  return (
    <EdenPage
      title={`${saudacao(agora)}!`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {soAtivo && <EdenSpaceSelect />}
          <label className="inline-flex items-center gap-1.5 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
            <input type="checkbox" checked={soAtivo} onChange={(e) => setSoAtivo(e.target.checked)} />
            Só um espaço
          </label>
        </div>
      }
    >
      <p className="text-sm -mt-2" style={{ color: 'var(--color-text-secondary)' }}>
        <CalendarCheck size={14} className="inline mr-1 -mt-0.5" />
        {dataLonga.charAt(0).toUpperCase() + dataLonga.slice(1)}
        {resumo && (
          <>
            {' · '}
            {total === 0 ? 'nada pendente para hoje' : `${total} ${total === 1 ? 'tarefa' : 'tarefas'} para hoje`}
            {resumo.feitas_hoje.length > 0 && ` · ${resumo.feitas_hoje.length} feita${resumo.feitas_hoje.length === 1 ? '' : 's'}`}
          </>
        )}
      </p>
      <ClimaDoDia />
      <ErrorLine message={erro} />

      {resumo === null ? (
        <Empty>Carregando…</Empty>
      ) : (
        <>
          {resumo.atrasadas.length > 0 && (
            <EdenSection title={`Atrasadas (${resumo.atrasadas.length})`}>
              <ul>
                {resumo.atrasadas.map((t) => (
                  <LinhaTarefa key={t.id} tarefa={t} mostrarEspaco={mostrarEspaco} onMudou={carregar} />
                ))}
              </ul>
            </EdenSection>
          )}
          {agenda !== null && (
            <EdenSection title="Agenda do Google">
              {agenda.length === 0 ? (
                <Empty>Nenhum evento hoje.</Empty>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {agenda.map((e) => (
                    <li key={e.id} className="text-sm flex items-baseline gap-2">
                      <CalendarDays size={12} className="shrink-0 translate-y-0.5" style={{ color: 'var(--color-accent)' }} />
                      <span className="tabular-nums shrink-0" style={{ color: 'var(--color-text-secondary)' }}>
                        {horarioEvento(e)}
                      </span>
                      <span style={{ color: 'var(--color-text)' }}>
                        {e.titulo}
                        {e.local && (
                          <span className="text-xs ml-1" style={{ color: 'var(--color-text-tertiary)' }}>
                            · {e.local}
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </EdenSection>
          )}
          <EdenSection title="Hoje">
            {resumo.hoje.length === 0 ? (
              <Empty>Nenhuma tarefa marcada para hoje.</Empty>
            ) : (
              <ul>
                {resumo.hoje.map((t) => (
                  <LinhaTarefa key={t.id} tarefa={t} mostrarEspaco={mostrarEspaco} onMudou={carregar} />
                ))}
              </ul>
            )}
          </EdenSection>
          {resumo.proximas.length > 0 && (
            <EdenSection title="Próximos 7 dias">
              <ul>
                {resumo.proximas.map((t) => (
                  <LinhaTarefa key={t.id} tarefa={t} mostrarEspaco={mostrarEspaco} onMudou={carregar} />
                ))}
              </ul>
            </EdenSection>
          )}
          {resumo.notas_fixadas.length > 0 && (
            <EdenSection title="Notas fixadas">
              <ul className="flex flex-col gap-2">
                {resumo.notas_fixadas.map((n) => (
                  <li key={n.id} className="text-sm">
                    <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-text)' }}>
                      <Pin size={12} /> {n.titulo || n.texto.slice(0, 120)}
                    </span>
                    {mostrarEspaco && (
                      <span className="ml-2">
                        <Badge>{nomeEspaco(espacos, n.espaco)}</Badge>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </EdenSection>
          )}
          <EdenSection title="Plano do dia">
            <p className="text-xs mb-2" style={{ color: 'var(--color-text-tertiary)' }}>
              O Éden olha as tarefas do espaço escolhido na conversa ({nomeEspaco(espacos, espacoAtivo)}) e
              sugere uma ordem. Usa a IA (custa alguns centavos).
            </p>
            <PrimaryButton onClick={() => navigate(`/?pedir=${encodeURIComponent(PEDIDO_PLANO)}`)}>
              <MessageSquare size={14} /> Pedir um plano ao Éden
            </PrimaryButton>
          </EdenSection>
        </>
      )}
    </EdenPage>
  );
}
