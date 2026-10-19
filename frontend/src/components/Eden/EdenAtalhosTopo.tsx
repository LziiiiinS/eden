// Éden: canto de cima, à direita — Perfil e memória, Configurações e o sino,
// sempre à mão (antes ficavam no fim da lista do menu lateral).
import { Brain, Settings } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router';
import { ApprovalBell } from '../ApprovalBell';

const ATALHOS = [
  { path: '/memoria', icon: Brain, label: 'Perfil e memória' },
  { path: '/settings', icon: Settings, label: 'Configurações' },
];

export function EdenAtalhosTopo() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div className="fixed top-2 right-3 z-40 flex items-center gap-0.5">
      {ATALHOS.map(({ path, icon: Icone, label }) => {
        const ativo = location.pathname === path;
        return (
          <button
            key={path}
            type="button"
            onClick={() => navigate(path)}
            title={label}
            aria-label={label}
            aria-current={ativo ? 'page' : undefined}
            className="p-2 rounded-lg transition-colors cursor-pointer"
            style={{
              color: ativo ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              background: ativo ? 'var(--color-accent-subtle)' : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (!ativo) e.currentTarget.style.background = 'var(--color-bg-tertiary)';
            }}
            onMouseLeave={(e) => {
              if (!ativo) e.currentTarget.style.background = 'transparent';
            }}
          >
            <Icone size={17} />
          </button>
        );
      })}
      <ApprovalBell />
    </div>
  );
}
