/**
 * Minimal hash router.
 *
 * A hash router keeps the app deployable as static files (no server rewrite
 * rules) and makes routes testable without a DOM. Paths are parsed into typed
 * route objects; unknown paths fall back to the project list.
 */

export type Route =
  | { name: 'projects' }
  | { name: 'project'; projectId: string }
  | { name: 'notFound'; path: string };

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, '');
  const path = raw.split('?')[0] ?? '/';
  const segments = path.split('/').filter(Boolean);
  if (segments.length === 0) return { name: 'projects' };
  if (segments[0] === 'projects' && segments[1]) {
    return { name: 'project', projectId: decodeURIComponent(segments[1]) };
  }
  return { name: 'notFound', path };
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'projects':
      return '#/';
    case 'project':
      return `#/projects/${encodeURIComponent(route.projectId)}`;
    case 'notFound':
      return `#${route.path}`;
  }
}

export function currentRoute(): Route {
  if (typeof window === 'undefined') return { name: 'projects' };
  return parseRoute(window.location.hash);
}
