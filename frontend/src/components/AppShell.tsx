import { ScanLine, Settings2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { ThemeToggle, type Theme } from './ThemeToggle';

const navigation = [
  { href: '/', label: 'Analyze chart', icon: ScanLine },
  { href: '/settings', label: 'Settings', icon: Settings2 },
];

export function AppShell({ children, onNavigate, theme, onToggleTheme }: { children: ReactNode; onNavigate: (path: string) => void; theme: Theme; onToggleTheme: () => void }) {
  const activePath = window.location.pathname === '/' ? '/' : window.location.pathname;
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <a className="brand" href="/" onClick={(event) => { event.preventDefault(); onNavigate('/'); }}>
          <span className="brand-mark" aria-hidden="true">T</span>
          <span>TradeVeo<span className="brand-caption">ENTRY SETUPS</span></span>
        </a>
        <p className="nav-label">WORKSPACE</p>
        <nav>
          {navigation.map(({ href, label, icon: Icon }) => (
            <a key={href} href={href} className={`nav-link ${activePath === href ? 'active' : ''}`} aria-current={activePath === href ? 'page' : undefined}
              onClick={(event) => { event.preventDefault(); onNavigate(href); }}>
              <Icon size={18} strokeWidth={1.8} aria-hidden="true" /> {label}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="local-dot" /> PRIVATE · ON THIS DEVICE</div>
      </aside>
      <div className="main-column">
        <header className="topbar"><span>CHART DESK</span><div className="topbar-tools"><span className="local-badge"><span className="local-dot" /> LOCAL DATA</span><ThemeToggle theme={theme} onToggle={onToggleTheme} /></div></header>
        <main className="content" id="main-content">{children}</main>
      </div>
    </div>
  );
}
