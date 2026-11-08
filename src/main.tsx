import { StrictMode, type PropsWithChildren, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import { SpacetimeDBProvider } from 'spacetimedb/react';
import { DbConnection } from './module_bindings';
import App from './App';

// Opt in once a database is published. The frontend runs independently by default.
const enabled = import.meta.env.VITE_SPACETIMEDB_ENABLED === 'true';
const host = import.meta.env.VITE_SPACETIMEDB_HOST ?? 'ws://localhost:3000';
const database = import.meta.env.VITE_SPACETIMEDB_DB_NAME ?? 'texas-response';
const tokenKey = `${host}/${database}/auth_token`;

function ConnectedRoot({ children }: PropsWithChildren) {
  const connectionBuilder = useMemo(() => DbConnection.builder()
    .withUri(host)
    .withDatabaseName(database)
    .withToken(localStorage.getItem(tokenKey) ?? undefined)
    .withAutomaticReconnect()
    .onConnect((_connection, _identity, token) => localStorage.setItem(tokenKey, token)), []);
  return <SpacetimeDBProvider connectionBuilder={connectionBuilder}>{children}</SpacetimeDBProvider>;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>{enabled ? <ConnectedRoot><App /></ConnectedRoot> : <App />}</StrictMode>
);
