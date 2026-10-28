import { useState } from 'react';
import { errorMessage } from '../api';
import type { Fleet } from '../fleet';
import { useAlive } from '../hooks';
import { accountView, formatAbsolute, holdLabel, providerLabel } from '../quota';
import type { Account, Target } from '../types';
import { missingQuotaText } from './AccountCard';
import { QuotaBar } from './Quota';
import { Button, Notice, PageHeader } from './ui';

export function AccountDetails({ account, now, fleet, target, onBack, onLogin, onEnabledChanged }: {
  account: Account | null;
  now: number;
  fleet: Fleet;
  target: Target;
  onBack: () => void;
  onLogin: (account: Account) => void;
  onEnabledChanged: (name: string, enabled: boolean) => void;
}) {
  const alive = useAlive();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!account) {
    return (
      <>
        <PageHeader title="Account nicht gefunden" back={{ label: 'Zurück', onClick: onBack }} />
        <p className="lead">Dieser Account ist in der letzten Abfrage nicht mehr enthalten.</p>
      </>
    );
  }

  const view = accountView(account, now);
  const toggle = async () => {
    const next = !account.enabled;
    setBusy(true);
    setError(null);
    try {
      await fleet.setProfileEnabled(target, account.name, next);
      if (alive.current) onEnabledChanged(account.name, next);
    } catch (err) {
      if (alive.current) setError(errorMessage(err));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const rows: [string, string][] = [
    ['Profil', account.managed ? account.name : 'Codex-Standardanmeldung'],
    ['Anbieter', providerLabel(account.provider)],
    ['Rolle', view.roleLabel],
    ['Tarif', view.planLabel],
    ['Status', view.statusLabel],
    ['Datenstand', account.observed_at ? formatAbsolute(account.observed_at) : 'Noch keine Kontingentdaten'],
    ['Zuletzt geprüft', account.checked_at ? formatAbsolute(account.checked_at) : 'Noch nicht geprüft'],
  ];
  if (view.held) {
    rows.push(['Sperre', holdLabel(account.hold_reason) + (account.hold_until ? ' bis ' + formatAbsolute(account.hold_until) : '')]);
  }

  return (
    <>
      <PageHeader title={view.displayName} subtitle={account.email ?? 'Account-Details'} back={{ label: 'Zurück', onClick: onBack }} />
      <div className="details">
        <dl className="facts">
          {rows.map(([label, value]) => (
            <div key={label} className="fact">
              <dt>{label}</dt>
              <dd className={label === 'Status' && view.tone === 'warning' ? 'tone-warning' : undefined}>{value}</dd>
            </div>
          ))}
        </dl>
        <section className="details-section" aria-labelledby="limits-heading">
          <h2 id="limits-heading">Gemeldete Limits</h2>
          {view.windows.length === 0 && <p className="muted">{missingQuotaText(account)}</p>}
          {view.windows.map((window) => (
            <div key={(window.raw.key ?? '') + window.title} className="details-limit">
              <QuotaBar window={window} />
              {window.resetAbsolute && !window.expired && <p className="muted small">Reset am {window.resetAbsolute}</p>}
            </div>
          ))}
          {view.stale && view.windows.length > 0 && (
            <p className="muted small">Die Werte sind älter als 150 Sekunden oder eine Reset-Zeit ist erreicht. Erst eine neue Abfrage liefert aktuelle Werte.</p>
          )}
        </section>
        {account.error && (
          <Notice title="Letzte Abfrage fehlgeschlagen">
            <p className="plain-text">{account.error.slice(0, 600)}</p>
          </Notice>
        )}
        <section className="details-section" aria-labelledby="usage-heading">
          <h2 id="usage-heading">Aufträge</h2>
          {account.managed ? (
            <>
              <p className="muted">
                {account.enabled ? 'Agent Fleet kann diesem Profil Aufträge zuweisen.' : 'Dieses Profil erhält derzeit keine Aufträge.'}
              </p>
              <div className="button-row">
                <Button variant={account.enabled ? 'soft' : 'primary'} onClick={() => void toggle()} disabled={busy} aria-busy={busy || undefined}>
                  {busy ? 'Wird gespeichert …' : account.enabled ? 'Für Aufträge deaktivieren' : 'Für Aufträge aktivieren'}
                </Button>
                <Button onClick={() => onLogin(account)}>Erneut anmelden</Button>
              </div>
            </>
          ) : (
            <p className="muted">Codex-Standardanmeldung. Dieses Konto erhält keine Aufträge über Agent Fleet.</p>
          )}
          {error && <Notice title="Änderung nicht gespeichert"><p>{error}</p></Notice>}
        </section>
      </div>
    </>
  );
}
