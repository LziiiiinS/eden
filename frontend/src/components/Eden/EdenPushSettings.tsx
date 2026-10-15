// Éden: ativar os avisos de lembrete neste aparelho (Web Push).
import { useEffect, useState } from 'react';
import { Bell, BellOff, Send, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { ativarPush, desativarPush, situacaoPush, testarPush, type SituacaoPush } from '../../lib/eden-push';
import { edenJson } from '../../lib/eden-org';
import { ErrorLine, GhostButton, IconButton, PrimaryButton } from './EdenUi';

interface Inscricao {
  id: number;
  nome: string;
  servico: string | null;
  criado_em: number;
  usado_em: number | null;
}

const SERVICO: Record<string, string> = {
  'web.push.apple.com': 'Apple',
  'fcm.googleapis.com': 'Google',
  'updates.push.services.mozilla.com': 'Firefox',
};

function nomeServico(host: string | null): string {
  if (!host) return '';
  if (SERVICO[host]) return SERVICO[host];
  if (host.endsWith('.notify.windows.com')) return 'Microsoft';
  if (host.endsWith('.push.apple.com')) return 'Apple';
  return host;
}

// Éden: todos os aparelhos que recebem os avisos, para conferir e tirar os
// que não são seus (ou que você não usa mais).
function Aparelhos({ versao }: { versao: number }) {
  const [lista, setLista] = useState<Inscricao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = () => {
    edenJson<{ inscricoes: Inscricao[] }>('/push/inscricoes')
      .then(({ inscricoes }) => setLista(inscricoes))
      .catch((e) => setErro((e as Error).message));
  };

  useEffect(carregar, [versao]);

  const remover = async (insc: Inscricao) => {
    if (!window.confirm(`Parar de mandar avisos para "${insc.nome || 'Aparelho'}"?`)) return;
    try {
      await edenJson(`/push/inscricoes/${insc.id}`, { method: 'DELETE' });
      carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  if (!lista || lista.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
        Aparelhos que recebem os avisos (se aparecer algum que não é seu, tire):
      </p>
      <ul>
        {lista.map((insc) => (
          <li
            key={insc.id}
            className="flex items-center gap-2 py-1.5 text-sm"
            style={{ borderBottom: '1px solid var(--color-border-subtle)', color: 'var(--color-text)' }}
          >
            <span className="flex-1 min-w-0 truncate">
              {insc.nome || 'Aparelho'}
              <span className="text-xs ml-2" style={{ color: 'var(--color-text-tertiary)' }}>
                {nomeServico(insc.servico)} · desde {new Date(insc.criado_em).toLocaleDateString('pt-BR')}
              </span>
            </span>
            <IconButton label="Parar avisos neste aparelho" onClick={() => void remover(insc)}>
              <Trash2 size={15} />
            </IconButton>
          </li>
        ))}
      </ul>
      <ErrorLine message={erro} />
    </div>
  );
}

const TEXTO: Record<SituacaoPush, string> = {
  'sem-suporte': 'Este navegador não aceita avisos. Os lembretes aparecem só com o Éden aberto.',
  'instalar-iphone':
    'No iPhone, os avisos só funcionam com o Éden instalado: no Safari, toque em Compartilhar → "Adicionar à Tela de Início", abra o Éden pelo ícone e volte aqui.',
  negado:
    'Os avisos estão bloqueados para o Éden neste aparelho. Libere nas configurações do navegador (ou do celular) e volte aqui.',
  desligado: 'Desligado neste aparelho. Com o Éden fechado, os lembretes não avisam.',
  ligado: 'Ligado neste aparelho: os lembretes avisam mesmo com o Éden fechado.',
};

export function EdenPushSettings() {
  const [situacao, setSituacao] = useState<SituacaoPush | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [versao, setVersao] = useState(0);

  const atualizar = () => {
    situacaoPush()
      .then(setSituacao)
      .catch(() => setSituacao('sem-suporte'));
  };

  useEffect(atualizar, []);

  const rodar = async (acao: () => Promise<void>) => {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setOcupado(false);
      atualizar();
      setVersao((v) => v + 1);
    }
  };

  return (
    <div>
      <p className="text-xs mb-3" style={{ color: 'var(--color-text-secondary)' }}>
        {situacao ? TEXTO[situacao] : 'Conferindo…'}
      </p>
      <div className="flex flex-wrap gap-2">
        {situacao === 'desligado' && (
          <PrimaryButton
            disabled={ocupado}
            onClick={() =>
              rodar(async () => {
                await ativarPush();
                toast.success('Avisos ligados neste aparelho');
              })
            }
          >
            <Bell size={14} /> Ativar avisos
          </PrimaryButton>
        )}
        {situacao === 'ligado' && (
          <>
            <PrimaryButton
              disabled={ocupado}
              onClick={() =>
                rodar(async () => {
                  const r = await testarPush();
                  if (r.enviados > 0) toast.success('Aviso de teste enviado. Deve chegar em alguns segundos.');
                  else toast.error('Nenhum aviso saiu. Desative e ative de novo.');
                })
              }
            >
              <Send size={14} /> Testar
            </PrimaryButton>
            <GhostButton disabled={ocupado} onClick={() => rodar(desativarPush)}>
              <BellOff size={14} /> Desativar
            </GhostButton>
          </>
        )}
      </div>
      <ErrorLine message={erro} />
      <Aparelhos versao={versao} />
    </div>
  );
}
