// Éden (Parte 2): avisos de lembrete com o app aberto.
// Confere os lembretes no servidor a cada minuto (e quando o app volta para a
// frente) e mostra um aviso na tela na hora certa. Com o app fechado, quem
// avisa é a notificação do aparelho (quando ativada nas Configurações).
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router';
import { useAppStore } from '../../lib/store';
import { isEdenModel } from '../../lib/eden-ai';
import { edenJson, type Tarefa } from '../../lib/eden-org';
import { avisarMudanca } from '../Chat/EdenActionCards';
import { sincronizarPush } from '../../lib/eden-push';

const AVISADOS_KEY = 'eden-lembretes-avisados';
const INTERVALO_MS = 60_000;

function lerAvisados(): Record<string, number> {
  try {
    const raw = JSON.parse(localStorage.getItem(AVISADOS_KEY) || '{}');
    return raw && typeof raw === 'object' ? raw : {};
  } catch {
    return {};
  }
}

function salvarAvisados(avisados: Record<string, number>): void {
  // Guarda só os últimos 2 dias.
  const limite = Date.now() - 2 * 24 * 3600 * 1000;
  const limpos = Object.fromEntries(Object.entries(avisados).filter(([, quando]) => quando > limite));
  try {
    localStorage.setItem(AVISADOS_KEY, JSON.stringify(limpos));
  } catch {
    // Melhor esforço.
  }
}

export function EdenReminders() {
  const navigate = useNavigate();
  const edenServer = useAppStore((s) => s.models.some((m) => isEdenModel(m.id)));
  const apiKey = useAppStore((s) => s.settings.apiKey);
  const proximo = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!edenServer || !apiKey) return;
    let cancelado = false;

    const avisar = (t: Tarefa) => {
      toast(`Lembrete: ${t.titulo}`, {
        duration: 60_000,
        action: {
          label: 'Feito',
          onClick: () => {
            edenJson(`/tarefas/${t.id}`, { method: 'PATCH', body: { feita: true } })
              .then(() => avisarMudanca())
              .catch((e) => toast.error((e as Error).message));
          },
        },
        cancel: { label: 'Ver', onClick: () => navigate('/tarefas') },
      });
    };

    const conferir = async () => {
      try {
        const { agora, lembretes } = await edenJson<{ agora: number; lembretes: Tarefa[] }>('/lembretes');
        if (cancelado) return;
        const avisados = lerAvisados();
        const diferenca = Date.now() - agora; // relógio do aparelho x servidor
        for (const t of lembretes) {
          if (t.lembrete_em === null) continue;
          const chave = `${t.id}:${t.lembrete_em}`;
          if (t.lembrete_em <= agora && !avisados[chave]) {
            avisados[chave] = Date.now();
            avisar(t);
          }
        }
        salvarAvisados(avisados);
        // Programa o próximo lembrete das próximas horas com precisão.
        const futuros = lembretes
          .map((t) => t.lembrete_em ?? 0)
          .filter((ms) => ms > agora)
          .sort((a, b) => a - b);
        if (proximo.current) clearTimeout(proximo.current);
        if (futuros.length > 0) {
          const espera = futuros[0] + diferenca - Date.now() + 1000;
          if (espera < INTERVALO_MS) proximo.current = setTimeout(conferir, Math.max(espera, 1000));
        }
      } catch {
        // Sem conexão: tenta de novo no próximo minuto.
      }
    };

    void conferir();
    void sincronizarPush();
    const intervalo = setInterval(conferir, INTERVALO_MS);
    const aoVoltar = () => {
      if (document.visibilityState === 'visible') void conferir();
    };
    document.addEventListener('visibilitychange', aoVoltar);
    window.addEventListener('eden-org-mudou', conferir);
    return () => {
      cancelado = true;
      clearInterval(intervalo);
      if (proximo.current) clearTimeout(proximo.current);
      document.removeEventListener('visibilitychange', aoVoltar);
      window.removeEventListener('eden-org-mudou', conferir);
    };
  }, [edenServer, apiKey, navigate]);

  return null;
}
