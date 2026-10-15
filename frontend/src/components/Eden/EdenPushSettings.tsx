// Éden: ativar os avisos de lembrete neste aparelho (Web Push).
import { useEffect, useState } from 'react';
import { Bell, BellOff, Send } from 'lucide-react';
import { toast } from 'sonner';
import { ativarPush, desativarPush, situacaoPush, testarPush, type SituacaoPush } from '../../lib/eden-push';
import { ErrorLine, GhostButton, PrimaryButton } from './EdenUi';

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
    </div>
  );
}
