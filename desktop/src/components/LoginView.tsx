import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { errorMessage } from '../api';
import type { Fleet } from '../fleet';
import { newKey } from '../ids';
import { providerLabel } from '../quota';
import { ACTIVE_LOGIN_STATES, type LoginSession, type Provider, type Target } from '../types';
import { profileName, redactSecret, safeLoginUrl } from '../validation';
import { Button, Field, Notice, PageHeader } from './ui';

export interface LoginSeed {
  name: string;
  provider: Provider;
}

const isActive = (session: LoginSession | null) => session !== null && ACTIVE_LOGIN_STATES.has(session.state);

/**
 * Native provider sign-in on the selected computer. One stable key per attempt makes
 * a repeated start idempotent; one poll runs at a time; responses that belong to an
 * earlier attempt are dropped. Leaving the view cancels an unfinished session.
 */
export function LoginView({ fleet, target, seed, pollMs, onBack, onDone }: {
  fleet: Fleet;
  target: Target;
  seed: LoginSeed | null;
  pollMs: number;
  onBack: () => void;
  onDone: () => void;
}) {
  const [provider, setProvider] = useState<Provider>(seed?.provider ?? 'codex');
  const [name, setName] = useState(seed?.name ?? '');
  const [code, setCode] = useState('');
  const [session, setSession] = useState<LoginSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const alive = useRef(true);
  const keyRef = useRef<string>(newKey());
  const specRef = useRef<string | null>(null);
  /** A start was sent with keyRef and no final state is known yet. */
  const pendingRef = useRef(false);
  const sessionRef = useRef<LoginSession | null>(null);
  const pollTimer = useRef<number | null>(null);
  const pollInflight = useRef(false);
  const busyRef = useRef(false);
  const deviceField = useRef<HTMLInputElement>(null);

  const stopPolling = () => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    pollTimer.current = null;
  };

  /** Fire-and-forget cancel of the current attempt, used when it is abandoned. */
  const abandon = useCallback(() => {
    stopPolling();
    const current = sessionRef.current;
    if (pendingRef.current || isActive(current)) {
      const id = current?.id ?? keyRef.current;
      fleet.authCancel(target, id).catch(() => undefined);
    }
    pendingRef.current = false;
    sessionRef.current = null;
    pollInflight.current = false;
  }, [fleet, target]);

  const markBusy = (value: boolean) => {
    busyRef.current = value;
    setBusy(value);
  };

  // These helpers read only refs plus props that are fixed for this instance
  // (the view is keyed by target), so a timer may safely call an older copy.
  function schedulePoll(key: string) {
    stopPolling();
    if (!alive.current || key !== keyRef.current || !isActive(sessionRef.current)) return;
    pollTimer.current = window.setTimeout(() => {
      pollTimer.current = null;
      const current = sessionRef.current;
      if (!alive.current || key !== keyRef.current || pollInflight.current || !current || !isActive(current)) return;
      if (busyRef.current) {
        schedulePoll(key);
        return;
      }
      pollInflight.current = true;
      fleet.authGet(target, current.id).then(
        (incoming) => {
          if (key !== keyRef.current || !alive.current) return;
          pollInflight.current = false;
          apply(key, incoming);
        },
        (err: unknown) => {
          if (key !== keyRef.current || !alive.current) return;
          pollInflight.current = false;
          setError(errorMessage(err));
          schedulePoll(key);
        },
      );
    }, pollMs);
  }

  function apply(key: string, incoming: LoginSession) {
    if (key !== keyRef.current || !alive.current) return;
    const previous = sessionRef.current;
    // An older status never replaces a newer one.
    const outdated = previous !== null && previous.id === incoming.id && incoming.updated_at !== null
      && previous.updated_at !== null && incoming.updated_at < previous.updated_at;
    if (!outdated) {
      sessionRef.current = incoming;
      pendingRef.current = isActive(incoming);
      setSession(incoming);
      setError(null);
    }
    if (isActive(sessionRef.current)) schedulePoll(key);
    else stopPolling();
  }

  useEffect(() => {
    alive.current = true;
    const onHide = () => abandon();
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      alive.current = false;
      abandon();
    };
  }, [abandon]);

  const profile = profileName(name, provider);
  const where = target ?? 'diesem Rechner';

  const start = async (event: FormEvent) => {
    event.preventDefault();
    if (busyRef.current) return;
    if (!profile) {
      setError('Gib einen Profilnamen ein.');
      return;
    }
    const spec = provider + ':' + profile;
    if (specRef.current !== null && specRef.current !== spec) {
      // A different account needs a different key; the old attempt is cancelled.
      abandon();
      keyRef.current = newKey();
    }
    specRef.current = spec;
    const key = keyRef.current;
    pendingRef.current = true;
    markBusy(true);
    setError(null);
    try {
      const started = await fleet.authStart(target, profile, provider, key);
      apply(key, started);
    } catch (err) {
      // The same key is reused on the next attempt, so a lost response cannot start twice.
      if (key === keyRef.current && alive.current) setError(errorMessage(err));
    } finally {
      if (key === keyRef.current && alive.current) markBusy(false);
    }
  };

  const submitCode = async (event: FormEvent) => {
    event.preventDefault();
    const current = sessionRef.current;
    if (busyRef.current || !current) return;
    const value = code.trim();
    if (!value) {
      setError('Füge den Code aus dem Browser ein.');
      return;
    }
    const key = keyRef.current;
    setCode('');
    markBusy(true);
    setError(null);
    try {
      await fleet.authInput(target, current.id, value);
      const next = await fleet.authGet(target, current.id);
      if (key === keyRef.current) markBusy(false);
      apply(key, next);
    } catch (err) {
      if (key === keyRef.current && alive.current) {
        markBusy(false);
        setError(redactSecret(errorMessage(err), value));
        schedulePoll(key);
      }
    } finally {
      if (key === keyRef.current && alive.current) markBusy(false);
    }
  };

  const cancel = async () => {
    const current = sessionRef.current;
    if (busyRef.current || !current) return;
    const key = keyRef.current;
    stopPolling();
    markBusy(true);
    setError(null);
    try {
      await fleet.authCancel(target, current.id);
      const next = await fleet.authGet(target, current.id);
      if (key === keyRef.current) markBusy(false);
      apply(key, next);
    } catch (err) {
      if (key === keyRef.current && alive.current) {
        markBusy(false);
        setError(errorMessage(err));
        schedulePoll(key);
      }
    } finally {
      if (key === keyRef.current && alive.current) markBusy(false);
    }
  };

  const retry = () => {
    const last = sessionRef.current;
    abandon();
    keyRef.current = newKey();
    specRef.current = null;
    if (last) {
      setName(last.profile);
      setProvider(last.provider);
    }
    setSession(null);
    setCode('');
    setError(null);
    setCopied(null);
  };

  const openUrl = async () => {
    const url = safeLoginUrl(session?.url ?? null);
    if (!url) {
      setError('Die Anmeldeseite ist keine offizielle Anbieter-Adresse und wird nicht geöffnet.');
      return;
    }
    try {
      await fleet.openLoginUrl(url.href);
    } catch (err) {
      if (alive.current) setError(errorMessage(err));
    }
  };

  const copyCode = async () => {
    const value = session?.device_code;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopied('Code kopiert.');
    } catch {
      deviceField.current?.select();
      setCopied('Code markiert. Mit ⌘C oder Strg+C kopieren.');
    }
  };

  const back = () => {
    abandon();
    onBack();
  };

  return (
    <>
      <PageHeader title="Account verbinden" subtitle={`Die Anmeldung bleibt auf ${where}.`} back={{ label: 'Zurück', onClick: back }} />
      <div className="login">
        {session === null ? (
          <form className="form" onSubmit={(e) => void start(e)} noValidate aria-busy={busy || undefined}>
            <fieldset className="choice" disabled={busy || seed !== null}>
              <legend>Anbieter</legend>
              {(['codex', 'claude'] as const).map((value) => (
                <label key={value} className="radio">
                  <input type="radio" name="login-provider" value={value} checked={provider === value}
                    onChange={() => setProvider(value)} />
                  <span>{value === 'codex' ? 'Codex · ChatGPT' : 'Claude'}</span>
                </label>
              ))}
            </fieldset>
            <Field label="Name für diesen Account" htmlFor="login-name"
              hint={profile ? `Profilname: ${profile}` : 'Zum Beispiel Privat oder Arbeit. Ein bestehender Account kann hier erneut angemeldet werden.'}>
              <input id="login-name" autoComplete="off" value={name} maxLength={64} disabled={busy || seed !== null}
                onChange={(e) => setName(e.target.value)} aria-describedby="login-name-hint" />
            </Field>
            <div className="button-row">
              <Button type="submit" variant="primary" disabled={busy}>
                {busy ? 'Anmeldung wird vorbereitet …' : 'Anmeldung starten'}
              </Button>
            </div>
          </form>
        ) : (
          <section className="login-session" aria-labelledby="login-heading" aria-busy={busy || undefined}>
            <h2 id="login-heading">{providerLabel(session.provider)} · {session.profile}</h2>
            <p className={`login-message${session.state === 'succeeded' ? ' tone-success' : ''}`} role="status" aria-live="polite">
              {session.message ?? stateText(session)}
            </p>
            {session.device_code && (
              <div className="device-code">
                <label htmlFor="device-code">Dein einmaliger Gerätecode</label>
                <input id="device-code" ref={deviceField} className="code-display" value={session.device_code} readOnly
                  onFocus={(e) => e.currentTarget.select()} />
                <div className="button-row">
                  <Button onClick={() => void copyCode()}>Code kopieren</Button>
                  {copied && <span className="small tone-muted" role="status">{copied}</span>}
                </div>
              </div>
            )}
            {session.url && isActive(session) && (
              <div className="button-row">
                <Button variant="primary" icon="box-arrow-up-right" onClick={() => void openUrl()}>Im Browser anmelden</Button>
                {safeLoginUrl(session.url) && <span className="small tone-muted">Öffnet {safeLoginUrl(session.url)?.hostname}</span>}
              </div>
            )}
            {session.provider === 'codex' && session.device_code && isActive(session) && (
              <p className="muted small">Device-Anmeldung muss gegebenenfalls in den ChatGPT- oder Workspace-Einstellungen erlaubt sein.</p>
            )}
            {session.state === 'awaiting_code' && (
              <form className="form code-form" onSubmit={(e) => void submitCode(e)} noValidate>
                <Field label="Code aus dem Browser" htmlFor="login-code" hint="Nur nötig, wenn der Browser einen Code anzeigt.">
                  <input id="login-code" type="password" autoComplete="off" spellCheck={false} value={code} disabled={busy}
                    onChange={(e) => setCode(e.target.value)} aria-describedby="login-code-hint" />
                </Field>
                <div className="button-row">
                  <Button type="submit" variant="primary" disabled={busy}>Anmeldung abschließen</Button>
                </div>
              </form>
            )}
            <div className="button-row">
              {isActive(session) && (
                <Button onClick={() => void cancel()} disabled={busy}>Anmeldung abbrechen</Button>
              )}
              {session.state === 'succeeded' && <Button variant="primary" onClick={onDone}>Zur Übersicht</Button>}
              {!isActive(session) && session.state !== 'succeeded' && (
                <Button variant="primary" onClick={retry}>Erneut versuchen</Button>
              )}
            </div>
          </section>
        )}
        {error && <Notice title="Anmeldung"><p className="plain-text">{error}</p></Notice>}
      </div>
    </>
  );
}

function stateText(session: LoginSession): string {
  switch (session.state) {
    case 'starting': return 'Anmeldung wird vorbereitet …';
    case 'awaiting_browser': return 'Bestätige die Anmeldung im Browser.';
    case 'awaiting_code': return 'Öffne die Anmeldeseite. Falls ein Code erscheint, füge ihn hier ein.';
    case 'verifying': return 'Anmeldung wird bestätigt …';
    case 'succeeded': return 'Account verbunden.';
    case 'cancelled': return 'Anmeldung abgebrochen.';
    case 'expired': return 'Die Anmeldung ist abgelaufen. Bitte neu starten.';
    default: return 'Anmeldung fehlgeschlagen.';
  }
}
