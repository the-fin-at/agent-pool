import { useId, useRef, useState } from 'react';
import { Icon } from '../icons';
import { providerLabel, type AccountView } from '../quota';
import type { Account } from '../types';
import { QuotaBar, QuotaRing } from './Quota';
import { Button, Chip, Field, Notice } from './ui';

export function missingQuotaText(account: Account): string {
  if (!account.connected && account.auth_mode === 'native_default') return 'Bitte in deiner normalen Claude-CLI anmelden und hier aktualisieren.';
  if (!account.connected) return 'Verbinde diesen Account direkt in der App.';
  return account.provider === 'claude' ? 'Noch keine Kontingentdaten aus der Claude-CLI.' : 'Für diesen Account fehlen Kontingentdaten.';
}

export function AccountCard({ view, compact, onDetails, onLogin, onRename, onRemove }: {
  view: AccountView;
  compact: boolean;
  onDetails: () => void;
  onLogin: () => void;
  onRename?: (name: string, displayName: string) => Promise<void>;
  onRemove?: (name: string) => Promise<void>;
}) {
  const id = useId();
  const renameButton = useRef<HTMLButtonElement>(null);
  const removeButton = useRef<HTMLButtonElement>(null);
  const [action, setAction] = useState<'rename' | 'remove' | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const displayName = draft.trim();

  function closeAction() {
    setAction(null);
    setError('');
    (action === 'rename' ? renameButton : removeButton).current?.focus();
  }

  async function changeAccount(change: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await change();
      closeAction();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  const { account, primary, extra } = view;
  const email = account.email ?? (account.connected ? 'Verbunden' : 'Nicht angemeldet');
  return (
    <article className={`card${compact ? ' card-compact' : ''}`} aria-labelledby={id}>
      <div className="card-summary">
        <div className="identity">
          <span className="avatar" aria-hidden="true"><Icon name="person" size={compact ? 24 : 30} /></span>
          <div className="identity-text">
            <h3 id={id} className="account-name">{view.displayName}</h3>
            <p className="account-email" title={email}>{email}</p>
            <div className="account-meta">
              <Chip>{view.planLabel}</Chip>
              {view.statusLabel !== 'Verbunden' && (
                <Chip tone={view.tone === 'warning' ? 'warning' : 'muted'}>
                  {view.tone === 'warning' && <Icon name="exclamation-circle" size={14} />}
                  {view.statusLabel}
                </Chip>
              )}
            </div>
            <p className="account-role">{providerLabel(account.provider)} · {view.roleLabel}</p>
            {(onRename || onRemove) && (
              <div className="account-management">
                {onRename && <Button ref={renameButton} variant="quiet" aria-label={`${view.displayName} umbenennen`}
                  aria-expanded={action === 'rename'} disabled={busy}
                  onClick={() => { setDraft(view.displayName); setError(''); setAction('rename'); }}>Umbenennen</Button>}
                {onRemove && <Button ref={removeButton} variant="quiet" aria-label={`${view.displayName} entfernen`}
                  aria-expanded={action === 'remove'} disabled={busy}
                  onClick={() => { setError(''); setAction('remove'); }}>Entfernen</Button>}
              </div>
            )}
          </div>
        </div>
        <div className="primary-quota">
          {primary && primary.title !== '5 Stunden' && <p className="primary-title">{primary.title}</p>}
          <QuotaRing window={primary} size={compact ? 'small' : 'large'} />
          <p className="primary-reset" title={primary?.resetAbsolute || undefined}>
            {primary ? primary.resetLabel : 'Kein 5-Stunden-Limit gemeldet'}
          </p>
        </div>
      </div>
      {action === 'rename' && onRename && (
        <form className="account-edit" onSubmit={(event) => {
          event.preventDefault();
          if (!busy && displayName && [...displayName].length <= 80) {
            void changeAccount(() => onRename(account.name, displayName));
          }
        }}>
          <Field label="Anzeigename" htmlFor={id + '-name'}>
            <input id={id + '-name'} value={draft} onChange={(event) => setDraft(event.target.value)}
              required autoFocus disabled={busy} />
          </Field>
          {error && <Notice title="Name nicht gespeichert">{error}</Notice>}
          <div className="button-row">
            <Button type="submit" variant="primary"
              disabled={busy || !displayName || [...displayName].length > 80 || displayName === view.displayName}>
              {busy ? 'Wird gespeichert …' : 'Speichern'}
            </Button>
            <Button onClick={closeAction} disabled={busy}>Abbrechen</Button>
          </div>
        </form>
      )}
      {action === 'remove' && onRemove && (
        <section className="account-edit" aria-label="Account entfernen">
          <p><strong>{view.displayName} entfernen?</strong></p>
          <p>{account.managed
            ? 'Der Account verschwindet aus der Übersicht und erhält keine neuen Aufträge. Die Anmeldung bleibt erhalten.'
            : 'Die Karte wird ausgeblendet. Deine Codex-Anmeldung bleibt erhalten.'}</p>
          {error && <Notice title="Account nicht entfernt">{error}</Notice>}
          <div className="button-row">
            <Button onClick={closeAction} autoFocus disabled={busy}>Abbrechen</Button>
            <Button variant="primary" onClick={() => void changeAccount(() => onRemove(account.name))} disabled={busy}>
              {busy ? 'Wird entfernt …' : 'Account entfernen'}
            </Button>
          </div>
        </section>
      )}
      {extra.map((window) => <QuotaBar key={(window.raw.key ?? '') + window.title} window={window} />)}
      {!account.windows.length && <p className="card-note">{missingQuotaText(account)}</p>}
      {account.alias_of && <p className="card-note">Dasselbe Konto wie die CLI-Standardanmeldung. Gemeinsames Kontingent.</p>}
      {account.error && (
        <p className="card-note tone-warning">
          {account.observed_at ? 'Abfrage fehlgeschlagen. Letzter gespeicherter Stand.' : 'Abfrage fehlgeschlagen. Noch keine Kontingentdaten.'}
        </p>
      )}
      <div className="card-foot">
        <span className={view.stale ? 'tone-warning' : 'tone-muted'}>{view.updatedLabel}</span>
        <div className="card-actions">
          {account.managed && !account.connected && account.auth_mode !== 'native_default' && (
            <Button variant="primary" onClick={onLogin} aria-label={`${view.displayName} anmelden`}>Anmelden</Button>
          )}
          <Button onClick={onDetails} aria-label={`Details zu ${view.displayName}`}>Details</Button>
        </div>
      </div>
    </article>
  );
}
