import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router';
import {
  MessageSquare,
  Plus,
  Search,
  PanelLeftClose,
  PanelLeft,
  Cpu,
  Sun,
  Moon,
  Monitor,
  Loader2,
  ListTodo,
  CalendarCheck,
  StickyNote,
  CloudSun,
  Car,
  Mail,
  Wallet,
  Users,
  House,
  ChevronRight,
  LayoutList,
  Compass,
} from 'lucide-react';
import { ConversationList } from './ConversationList';
import { EdenSyncStatus } from './EdenSyncStatus';
import { EdenSpending } from './EdenSpending';
import { friendlyModelName, isEdenModel } from '../../lib/eden-ai';
import { useAppStore } from '../../lib/store';
import { useNucleoStore } from '../../lib/eden-nucleo';

// Éden: o menu em grupos que abrem e fecham (pedido do Levi, 19/10: a lista
// estava comprida demais). Perfil e Configurações ficam no canto de cima,
// ao lado do sino (EdenAtalhosTopo).
type ItemMenu = { path: string; icon: typeof MessageSquare; label: string };
type GrupoMenu = { id: string; icon: typeof MessageSquare; label: string; itens: ItemMenu[] };

export const EDEN_GRUPOS: GrupoMenu[] = [
  {
    id: 'organizacao',
    icon: LayoutList,
    label: 'Organização',
    itens: [
      { path: '/hoje', icon: CalendarCheck, label: 'Hoje' },
      { path: '/tarefas', icon: ListTodo, label: 'Tarefas' },
      { path: '/notas', icon: StickyNote, label: 'Notas e ideias' },
      { path: '/reuniao', icon: Users, label: 'Modo reunião' },
    ],
  },
  {
    id: 'casa',
    icon: House,
    label: 'Casa e contas',
    itens: [
      { path: '/casa', icon: House, label: 'Casa' },
      { path: '/contas', icon: Wallet, label: 'Contas e impostos' },
    ],
  },
  {
    id: 'servicos',
    icon: Compass,
    label: 'Serviços',
    itens: [
      { path: '/email', icon: Mail, label: 'E-mail' },
      { path: '/clima', icon: CloudSun, label: 'Clima e ondas' },
      { path: '/rotas', icon: Car, label: 'Rotas e trânsito' },
    ],
  },
];

const CHAVE_GRUPOS = 'eden-menu-grupos';

function lerGruposAbertos(): Record<string, boolean> {
  try {
    const bruto = localStorage.getItem(CHAVE_GRUPOS);
    const dados = bruto ? JSON.parse(bruto) : {};
    return dados && typeof dados === 'object' ? dados : {};
  } catch {
    return {};
  }
}

function guardarGruposAbertos(abertos: Record<string, boolean>): void {
  try {
    localStorage.setItem(CHAVE_GRUPOS, JSON.stringify(abertos));
  } catch {
    // Sem armazenamento (janela anônima): só não lembra.
  }
}

// Éden: menu lateral em português. Nomes dos temas mostrados ao usuário.
const THEME_LABEL: Record<string, string> = {
  light: 'claro',
  dark: 'escuro',
  system: 'automático',
};

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchQuery, setSearchQuery] = useState('');
  const [abertos, setAbertos] = useState<Record<string, boolean>>(lerGruposAbertos);
  // O grupo da página aberta abre sozinho (ex.: chegar em /tarefas por um link).
  useEffect(() => {
    const grupo = EDEN_GRUPOS.find((g) => g.itens.some((i) => i.path === location.pathname));
    if (grupo && !abertos[grupo.id]) {
      setAbertos((a) => {
        const novo = { ...a, [grupo.id]: true };
        guardarGruposAbertos(novo);
        return novo;
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);
  const alternarGrupo = (id: string) =>
    setAbertos((a) => {
      const novo = { ...a, [id]: !a[id] };
      guardarGruposAbertos(novo);
      return novo;
    });

  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const visual3d = useNucleoStore((s) => s.ativo);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const createConversation = useAppStore((s) => s.createConversation);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const serverInfo = useAppStore((s) => s.serverInfo);
  const setCommandPaletteOpen = useAppStore((s) => s.setCommandPaletteOpen);
  const modelLoading = useAppStore((s) => s.modelLoading);
  const deepResearch = useAppStore((s) => s.deepResearch);
  // Éden: quem responde é escolhido na caixa de mensagem (Automático / Dia a
  // dia / Missão). O seletor de modelos do OpenJarvis (em inglês, com
  // download de modelos locais) fica escondido no servidor do Éden.
  const edenServer = useAppStore((s) => s.models.some((m) => isEdenModel(m.id)));

  const settings = useAppStore((s) => s.settings);
  const updateSettings = useAppStore((s) => s.updateSettings);

  const ThemeIcon = settings.theme === 'light' ? Sun : settings.theme === 'dark' ? Moon : Monitor;
  const nextTheme = settings.theme === 'light' ? 'dark' : settings.theme === 'dark' ? 'system' : 'light';

  const messages = useAppStore((s) => s.messages);
  const handleNewChat = () => {
    // Don't create a new chat if the current one is empty
    if (messages.length === 0) {
      navigate('/');
      return;
    }
    createConversation(selectedModel);
    navigate('/');
  };

  // Éden: as outras páginas do OpenJarvis (em inglês, para uso local)
  // continuam no código, fora do menu.
  const abrir = (path: string) => {
    navigate(path);
    // Éden: no celular, o menu fecha ao abrir uma página.
    if (window.matchMedia?.('(max-width: 767px)').matches) {
      useAppStore.getState().setSidebarOpen(false);
    }
  };

  return (
    <>
      {/* Collapse button when sidebar is closed */}
      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          aria-label="Abrir menu"
          className="fixed top-3 left-3 z-30 p-2 rounded-lg transition-colors cursor-pointer"
          style={{ color: 'var(--color-text-secondary)', background: 'var(--color-bg-secondary)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
        >
          <PanelLeft size={18} />
        </button>
      )}

      <aside
        className={`
          flex flex-col h-full shrink-0 transition-all duration-200 ease-in-out overflow-hidden
          fixed md:relative z-30
          ${sidebarOpen ? 'w-[260px]' : 'w-0'}
        `}
        style={{
          // Éden: com o fundo 3D, a barra fica quase opaca e sem desfoque
          // (desfocar o fundo animado gastaria bateria a cada quadro).
          background: visual3d ? 'var(--eden-barra)' : 'var(--color-sidebar)',
          backdropFilter: visual3d ? 'none' : 'blur(20px)',
          WebkitBackdropFilter: visual3d ? 'none' : 'blur(20px)',
          borderRight: sidebarOpen ? '1px solid var(--color-border)' : 'none',
        }}
      >
        <div className="flex flex-col h-full w-[260px]">
          {/* Header */}
          <div className="flex items-center justify-between px-3 pt-3 pb-2">
            <button
              onClick={toggleSidebar}
              aria-label="Fechar menu"
              className="p-2 rounded-lg transition-colors cursor-pointer"
              style={{ color: 'var(--color-text-secondary)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <PanelLeftClose size={18} />
            </button>
            <div className="flex items-center gap-1">
              <button
                onClick={() => updateSettings({ theme: nextTheme })}
                className="p-2 rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                title={`Tema: ${THEME_LABEL[settings.theme] ?? settings.theme} (clique para ${THEME_LABEL[nextTheme] ?? nextTheme})`}
                aria-label={`Trocar tema para ${THEME_LABEL[nextTheme] ?? nextTheme}`}
              >
                <ThemeIcon size={16} />
              </button>
              <button
                onClick={handleNewChat}
                className="p-2 rounded-lg transition-colors cursor-pointer"
                style={{ color: 'var(--color-text-secondary)' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                title="Nova conversa"
                aria-label="Nova conversa"
              >
                <Plus size={18} />
              </button>
            </div>
          </div>

          {/* Model badge */}
          {!edenServer && (
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="mx-3 mb-2 flex items-center gap-2 px-3 py-2 rounded-lg text-xs transition-colors cursor-pointer"
              style={{
                background: 'var(--color-bg-secondary)',
                color: 'var(--color-text-secondary)',
                border: '1px solid var(--color-border)',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-bg-tertiary)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-bg-secondary)')}
            >
              {modelLoading ? (
                <Loader2 size={14} className="animate-spin" style={{ color: 'var(--color-accent)' }} />
              ) : (
                <Cpu size={14} />
              )}
              <div className="flex-1 min-w-0">
                <span
                  className="truncate block text-left"
                  style={{ color: deepResearch ? 'var(--color-accent)' : 'var(--color-text)' }}
                >
                  {deepResearch
                    ? 'Pesquisa aprofundada'
                    : selectedModel
                      ? friendlyModelName(selectedModel)
                      : serverInfo?.model || 'Escolher modelo'}
                </span>
                {modelLoading && (
                  <span className="text-[10px] block text-left" style={{ color: 'var(--color-accent)' }}>
                    Carregando modelo…
                  </span>
                )}
              </div>
              {!modelLoading && (
                <kbd
                  className="text-[10px] px-1.5 py-0.5 rounded font-mono [@media(hover:none)]:hidden"
                  style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-tertiary)' }}
                >
                  ⌘K
                </kbd>
              )}
            </button>
          )}

          {/* Search */}
          <div className="px-3 mb-2">
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
            >
              <Search size={14} style={{ color: 'var(--color-text-tertiary)' }} />
              <input
                type="text"
                placeholder="Buscar conversas…"
                aria-label="Buscar conversas"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-transparent outline-none text-sm"
                style={{ color: 'var(--color-text)' }}
              />
            </div>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-2">
            <ConversationList searchQuery={searchQuery} />
          </div>

          {/* Éden: situação da sincronização das conversas e gastos do mês */}
          <EdenSyncStatus />
          <EdenSpending />

          {/* Bottom nav — Éden: Conversa + grupos que abrem e fecham. */}
          <nav
            className="px-2 pb-3 pt-2 flex flex-col gap-0.5 overflow-y-auto max-h-[55%]"
            style={{ borderTop: '1px solid var(--color-border)' }}
            aria-label="Menu"
          >
            <ItemDoMenu item={{ path: '/', icon: MessageSquare, label: 'Conversa' }} ativo={location.pathname === '/'} aoAbrir={abrir} />
            {EDEN_GRUPOS.map((g) => {
              const aberto = !!abertos[g.id];
              const temAtivo = g.itens.some((i) => i.path === location.pathname);
              return (
                <div key={g.id} className="flex flex-col">
                  <button
                    type="button"
                    onClick={() => alternarGrupo(g.id)}
                    aria-expanded={aberto}
                    aria-controls={`menu-grupo-${g.id}`}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors w-full text-left cursor-pointer"
                    style={{
                      color: temAtivo && !aberto ? 'var(--color-text)' : 'var(--color-text-secondary)',
                      background: temAtivo && !aberto ? 'var(--color-accent-subtle)' : 'transparent',
                    }}
                    onMouseEnter={(e) => {
                      if (!(temAtivo && !aberto)) e.currentTarget.style.background = 'var(--color-bg-secondary)';
                    }}
                    onMouseLeave={(e) => {
                      if (!(temAtivo && !aberto)) e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <g.icon size={16} style={temAtivo ? { color: 'var(--color-accent)' } : undefined} />
                    <span className="flex-1">{g.label}</span>
                    <ChevronRight
                      size={14}
                      aria-hidden="true"
                      className="transition-transform duration-200"
                      style={{ transform: aberto ? 'rotate(90deg)' : 'none', color: 'var(--color-text-tertiary)' }}
                    />
                  </button>
                  {aberto && (
                    <div
                      id={`menu-grupo-${g.id}`}
                      className="ml-[1.35rem] pl-2 flex flex-col gap-0.5 eden-menu-grupo"
                      style={{ borderLeft: '1px solid var(--color-border)' }}
                    >
                      {g.itens.map((item) => (
                        <ItemDoMenu key={item.path} item={item} ativo={location.pathname === item.path} aoAbrir={abrir} compacto />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </div>
      </aside>
    </>
  );
}

function ItemDoMenu({
  item,
  ativo,
  aoAbrir,
  compacto = false,
}: {
  item: ItemMenu;
  ativo: boolean;
  aoAbrir: (path: string) => void;
  compacto?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => aoAbrir(item.path)}
      aria-current={ativo ? 'page' : undefined}
      className={`relative flex items-center gap-3 px-3 rounded-lg text-sm transition-colors w-full text-left cursor-pointer ${compacto ? 'py-1.5' : 'py-2'}`}
      style={{
        background: ativo ? 'var(--color-accent-subtle)' : 'transparent',
        color: ativo ? 'var(--color-text)' : 'var(--color-text-secondary)',
        fontWeight: ativo ? 500 : 400,
      }}
      onMouseEnter={(e) => {
        if (!ativo) e.currentTarget.style.background = 'var(--color-bg-secondary)';
      }}
      onMouseLeave={(e) => {
        if (!ativo) e.currentTarget.style.background = 'transparent';
      }}
    >
      {ativo && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full"
          style={{ background: 'var(--color-accent)', boxShadow: '0 0 8px var(--color-accent-glow)' }}
        />
      )}
      <item.icon size={compacto ? 15 : 16} style={ativo ? { color: 'var(--color-accent)' } : undefined} />
      {item.label}
    </button>
  );
}
