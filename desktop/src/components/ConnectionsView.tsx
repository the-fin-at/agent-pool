import { useState } from 'react';
import { errorMessage } from '../api';
import { useAlive } from '../hooks';
import { Icon } from '../icons';
import { providerLabel } from '../quota';
import type { RemoteMap, RemoteTestResult } from '../types';
import { connectedLabel } from './AccountsView';
import { Button, IconButton, Notice, PageHeader } from './ui';

export interface RemotesState {
  map: RemoteMap | null;
  error: string | null;
  loading: boolean;
}

export type ConnectionSummary =
  | { state: 'checking' }
  | { state: 'ok'; connected: number; workerOnline: boolean | null }
  | { state: 'error'; error: string };

type TestState = { busy: true } | { busy: false; result?: RemoteTestResult; error?: string };

export function ConnectionsView({ remotes, summaries, onOpen, onAdd, onRefresh, onProbe, onRemove, onTest }: {
  remotes: RemotesState;
  summaries: Record<string, ConnectionSummary>;
  onOpen: (name: string) => void;
  onAdd: () => void;
  onRefresh: () => void;
  onProbe: (name: string) => void;
  onRemove: (name: string) => Promise<void>;
  onTest: (name: string) => Promise<RemoteTestResult>;
}) {
  const alive = useAlive();
  const [confirming, setConfirming] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, TestState>>({});
  const entries = Object.entries(remotes.map ?? {});

  const remove = async (name: string) => {
    setRemoving(name);
    setRemoveError(null);
    try {
      await onRemove(name);
      if (alive.current) setConfirming(null);
    } catch (error) {
      if (alive.current) setRemoveError(errorMessage(error));
    } finally {
      if (alive.current) setRemoving(null);
    }
  };

  const test = async (name: string) => {
    setTests((t) => ({ ...t, [name]: { busy: true } }));
    try {
      const result = await onTest(name);
      if (alive.current) setTests((t) => ({ ...t, [name]: { busy: false, result } }));
    } catch (error) {
      if (alive.current) setTests((t) => ({ ...t, [name]: { busy: false, error: errorMessage(error) } }));
    }
  };

  return (
    <>
      <PageHeader
        title="Verbindungen"
        subtitle="Deine entfernten Rechner und ihre verfügbaren Accounts."
        actions={
          <>
            <Button variant="primary" icon="plus-lg" onClick={onAdd}>Verbindung hinzufügen</Button>
            <IconButton icon="arrow-clockwise" label="Verbindungen prüfen" busy={remotes.loading} disabled={remotes.loading} onClick={onRefresh} />
          </>
        }
      />
      {remotes.error && (
        <Notice title="Verbindungen konnten nicht gelesen werden" action={{ label: 'Erneut versuchen', onClick: onRefresh, disabled: remotes.loading }}>
          <p>{remotes.error}</p>
        </Notice>
      )}
      {removeError && <Notice title="Verbindung nicht entfernt"><p>{removeError}</p></Notice>}
      {remotes.map === null && remotes.loading && <p className="loading" role="status">Verbindungen werden geladen …</p>}
      {remotes.map !== null && entries.length === 0 && (
        <section className="empty">
          <h2>Deine Accounts. Auf jedem Rechner.</h2>
          <p>Verbinde einen Linux-Server, um seine Accounts und Kontingente hier zu sehen.</p>
          <Button variant="primary" onClick={onAdd}>Verbindung hinzufügen</Button>
        </section>
      )}
      {entries.length > 0 && (
        <ul className="connection-list" aria-label="Verbindungen">
          {entries.map(([name, config]) => {
            const summary = summaries[name];
            const testState = tests[name];
            return (
              <li key={name} className="connection">
                <div className="connection-main">
                  <h2 className="connection-name"><Icon name="server" size={22} /><span>{name}</span></h2>
                  <p className="connection-host">{config.host}</p>
                  <ConnectionStatus summary={summary} onRetry={() => onProbe(name)} />
                  {testState && <TestOutcome state={testState} />}
                </div>
                <div className="connection-actions">
                  {confirming === name ? (
                    <div className="confirm" role="group" aria-label={`${name} entfernen`}>
                      <p>Entfernt nur die lokale Zuordnung. Serverdaten und Accounts bleiben erhalten.</p>
                      <div className="button-row">
                        <Button variant="primary" onClick={() => void remove(name)} disabled={removing === name}>
                          {removing === name ? 'Wird entfernt …' : 'Entfernen bestätigen'}
                        </Button>
                        <Button onClick={() => setConfirming(null)} disabled={removing === name}>Abbrechen</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="button-row">
                      <Button variant="primary" onClick={() => onOpen(name)} aria-label={`${name} öffnen`}>Öffnen</Button>
                      <Button onClick={() => void test(name)} disabled={testState?.busy} aria-label={`${name} prüfen`}>
                        {testState?.busy ? 'Wird geprüft …' : 'Prüfen'}
                      </Button>
                      <Button variant="quiet" onClick={() => setConfirming(name)} aria-label={`${name} entfernen`}>Entfernen</Button>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

function ConnectionStatus({ summary, onRetry }: { summary: ConnectionSummary | undefined; onRetry: () => void }) {
  if (!summary || summary.state === 'checking') return <p className="connection-status tone-muted">Wird geprüft …</p>;
  if (summary.state === 'error') {
    return (
      <div className="connection-status tone-warning">
        <p>Nicht erreichbar</p>
        <p className="small plain-text">{summary.error}</p>
        <Button variant="quiet" onClick={onRetry}>Erneut prüfen</Button>
      </div>
    );
  }
  const worker = summary.workerOnline === null ? '' : summary.workerOnline ? ' · Worker aktiv' : ' · Worker offline';
  return <p className="connection-status tone-success">{connectedLabel(summary.connected)}{worker}</p>;
}

function TestOutcome({ state }: { state: TestState }) {
  if (state.busy) return null;
  if (state.error) return <p className="small tone-warning plain-text" role="status">Prüfung fehlgeschlagen: {state.error}</p>;
  const checks = state.result?.checks ?? [];
  if (!checks.length) return <p className="small tone-muted" role="status">Server erreichbar. Keine CLI-Prüfung gemeldet.</p>;
  return (
    <ul className="checks" aria-label="Prüfergebnis">
      {checks.map((check, index) => (
        <li key={index} className={check.ok ? 'tone-success' : 'tone-warning'}>
          {providerLabel(check.provider)}-CLI: {check.ok ? check.version ?? 'gefunden' : check.error ?? 'nicht verfügbar'}
        </li>
      ))}
    </ul>
  );
}
