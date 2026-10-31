/**
 * App entry: routing between the project list and a project workbench.
 */
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../../../packages/ui/tokens.css';
import './styles.css';

import { AppShell } from './components/app-shell.tsx';
import { useWorkbench } from './hooks/use-workbench.ts';
import { currentRoute, routeToHash, type Route } from './lib/router.ts';
import { ProjectListPage } from './pages/project-list.tsx';
import { ProjectPage } from './pages/project-workbench.tsx';

function App() {
  const [route, setRoute] = useState<Route>(() => currentRoute());
  const scope = useWorkbench();

  useEffect(() => {
    const onChange = () => setRoute(currentRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const open = (projectId: string) => {
    const next: Route = { name: 'project', projectId };
    window.location.hash = routeToHash(next);
    setRoute(next);
  };

  const goHome = () => {
    window.location.hash = routeToHash({ name: 'projects' });
    setRoute({ name: 'projects' });
  };

  return (
    <AppShell
      actions={
        <nav className="crumbs" aria-label="导航">
          <button className="link" onClick={goHome}>
            全部项目
          </button>
          {route.name === 'project' && <span className="meta">/ {route.projectId.slice(0, 8)}</span>}
        </nav>
      }
    >
      {route.name === 'projects' && <ProjectListPage scope={scope} onOpen={open} />}
      {route.name === 'project' && <ProjectPage scope={scope} projectId={route.projectId} />}
      {route.name === 'notFound' && (
        <main className="page single">
          <p className="hint">找不到页面：{route.path}</p>
        </main>
      )}
    </AppShell>
  );
}

const container = document.getElementById('root');
if (container) createRoot(container).render(<App />);
