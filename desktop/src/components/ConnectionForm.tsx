import { useRef, useState, type FormEvent } from 'react';
import { errorMessage, FleetError } from '../api';
import type { Fleet } from '../fleet';
import { useAlive } from '../hooks';
import type { RemoteConfig, RemoteMap, StatusData } from '../types';
import { connectionError, type ConnectionInput } from '../validation';
import { Button, Field, Notice, PageHeader } from './ui';

const UPDATE_SERVER = 'Bitte Agent Fleet auf dem Server aktualisieren, um den Login in der App zu nutzen.';

/**
 * Saves a connection only after the server answered `status` with native login
 * support; a failed check removes the entry again.
 */
export function ConnectionForm({ fleet, existing, onBack, onRemotesChanged, onSaved }: {
  fleet: Fleet;
  existing: RemoteMap | null;
  onBack: () => void;
  onRemotesChanged: (map: RemoteMap) => void;
  onSaved: (name: string, map: RemoteMap, status: StatusData) => void;
}) {
  const alive = useAlive();
  const [input, setInput] = useState<ConnectionInput>({ name: '', host: '', advanced: false, command: '', home: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);

  /**
   * Like 0.4.1, a connection that fails its check is not kept. The entry is removed
   * only while it still holds exactly the configuration saved here, so a late
   * rollback never deletes a connection that was replaced in the meantime.
   */
  const rollback = async (name: string, config: RemoteConfig): Promise<string> => {
    try {
      const list = await fleet.remotes();
      const current = list[name];
      const ours = current && current.host === config.host && current.command === config.command && current.home === config.home;
      onRemotesChanged(ours ? await fleet.removeRemote(name) : list);
      return 'Die Verbindung wurde nicht gespeichert.';
    } catch {
      fleet.remotes().then(onRemotesChanged, () => undefined);
      return 'Die Verbindung bleibt vorerst gespeichert und kann in der Übersicht entfernt werden.';
    }
  };

  const set = (key: keyof ConnectionInput) => (value: string | boolean) => setInput((current) => ({ ...current, [key]: value }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busyRef.current) return;
    const problem = connectionError(input, existing);
    if (problem) {
      setError(problem);
      return;
    }
    const name = input.name.trim();
    const host = input.host.trim();
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const config = input.advanced
        ? { host, command: input.command.trim(), home: input.home.trim() }
        : await fleet.discover(host);
      const map = await fleet.addRemote(name, config);
      let status: StatusData;
      try {
        status = await fleet.remoteStatus(name);
        if (!status.features.includes('native-login-sessions')) throw new FleetError(UPDATE_SERVER);
      } catch (checkError) {
        throw new FleetError(errorMessage(checkError) + ' ' + (await rollback(name, config)));
      }
      onSaved(name, map, status);
    } catch (err) {
      if (alive.current) setError(errorMessage(err));
    } finally {
      busyRef.current = false;
      if (alive.current) setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Rechner verbinden" subtitle="Verbinde einen Server mit deinem vorhandenen SSH-Zugang." back={{ label: 'Zurück', onClick: onBack }} />
      <form className="form" onSubmit={(e) => void submit(e)} noValidate aria-busy={busy || undefined}>
        <Field label="Name" htmlFor="connection-name" hint="Zum Beispiel Linux Server. Leerzeichen sind erlaubt.">
          <input id="connection-name" autoComplete="off" value={input.name} maxLength={64} disabled={busy}
            onChange={(e) => set('name')(e.target.value)} aria-describedby="connection-name-hint" />
        </Field>
        <Field label="SSH-Adresse oder Alias" htmlFor="connection-host" hint="Ein Eintrag aus deiner SSH-Konfiguration oder user@host.">
          <input id="connection-host" autoComplete="off" autoCapitalize="off" spellCheck={false} value={input.host} disabled={busy}
            onChange={(e) => set('host')(e.target.value)} aria-describedby="connection-host-hint" />
        </Field>
        <p className="muted">
          {input.advanced
            ? 'Für eigene Datenverzeichnisse oder eingeschränkte SSH-Schlüssel. Die Verbindung wird vor dem Speichern geprüft.'
            : 'Agent Fleet erkennt Installation und Datenverzeichnis auf dem Server automatisch und prüft die Verbindung vor dem Speichern.'}
        </p>
        <label className="check">
          <input type="checkbox" checked={input.advanced} disabled={busy} onChange={(e) => set('advanced')(e.target.checked)} />
          <span>Erweiterte Einstellungen</span>
        </label>
        {input.advanced && (
          <>
            <Field label="Agent-Fleet-Datei auf dem Server" htmlFor="connection-command" hint="Zum Beispiel /home/user/.local/bin/agent-fleet">
              <input id="connection-command" autoComplete="off" spellCheck={false} value={input.command} disabled={busy}
                onChange={(e) => set('command')(e.target.value)} aria-describedby="connection-command-hint" />
            </Field>
            <Field label="Datenverzeichnis auf dem Server" htmlFor="connection-home" hint="Absoluter Pfad, den auch der Worker verwendet.">
              <input id="connection-home" autoComplete="off" spellCheck={false} value={input.home} disabled={busy}
                onChange={(e) => set('home')(e.target.value)} aria-describedby="connection-home-hint" />
            </Field>
          </>
        )}
        {error && <Notice title="Verbindung nicht gespeichert"><p className="plain-text">{error}</p></Notice>}
        <p className="muted small">Agent Fleet verwaltet keine SSH-Passwörter und akzeptiert keine ungeprüften Host-Keys.</p>
        <div className="button-row">
          <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Verbindung wird geprüft …' : 'Verbinden'}</Button>
        </div>
      </form>
    </>
  );
}
