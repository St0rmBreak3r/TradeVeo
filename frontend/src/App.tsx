import { useEffect, useState } from 'react';
import { AppShell } from './components/AppShell';
import { ChartAnalysisPage } from './components/ChartAnalysisPage';
import { SettingsPage } from './pages/SettingsPage';
import { useTheme } from './components/ThemeToggle';

export default function App() {
  const { theme, toggleTheme } = useTheme();
  const [activePath, setActivePath] = useState(window.location.pathname);

  useEffect(() => {
    const onPop = () => setActivePath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  function navigate(path: string) {
    window.history.pushState({}, '', path);
    setActivePath(path);
  }

  return (
    <AppShell onNavigate={navigate} theme={theme} onToggleTheme={toggleTheme}>
      {activePath === '/' && <ChartAnalysisPage onNavigate={navigate} />}
      {activePath === '/settings' && <SettingsPage />}
      {activePath !== '/' && activePath !== '/settings' && (
        <div className="empty-state">
          <h2>Page not found</h2>
          <button className="button button-primary" onClick={() => navigate('/')}>Back to chart analysis</button>
        </div>
      )}
    </AppShell>
  );
}
