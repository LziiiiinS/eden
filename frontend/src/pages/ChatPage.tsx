import { ChatArea } from '../components/Chat/ChatArea';
import { SystemPanel } from '../components/Chat/SystemPanel';
import { useAppStore } from '../lib/store';

// Éden: o painel "System" (energia, GPU, economia em relação à nuvem) é do
// uso local do OpenJarvis. No Éden as IAs rodam na nuvem e, no celular, o
// painel de 280 px espremia a conversa. Fica escondido no piloto.
const SHOW_SYSTEM_PANEL: boolean = false;

export function ChatPage() {
  const systemPanelOpen = useAppStore((s) => s.systemPanelOpen);

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 min-w-0">
        <ChatArea />
      </div>
      {SHOW_SYSTEM_PANEL && systemPanelOpen && <SystemPanel />}
    </div>
  );
}
