import { useId } from 'react';
import { Icon } from '../icons';
import { providerLabel, type AccountView } from '../quota';
import type { Account } from '../types';
import { QuotaBar, QuotaRing } from './Quota';
import { Button, Chip } from './ui';
import { ProviderLogo } from './ProviderLogo';

export function missingQuotaText(account: Account): string {
  if (!account.connected && account.auth_mode === 'native_default') return 'Bitte in deiner normalen Claude-CLI anmelden und hier aktualisieren.';
  if (!account.connected) return 'Verbinde diesen Account direkt in der App.';
  return account.provider === 'claude' ? 'Noch keine Kontingentdaten aus der Claude-CLI.' : 'Für diesen Account fehlen Kontingentdaten.';
}

export function AccountCard({ view, compact, onDetails, onLogin }: {
  view: AccountView;
  compact: boolean;
  onDetails: () => void;
  onLogin: () => void;
}) {
  const id = useId();
  const { account, primary, extra } = view;
  const email = account.email ?? (account.connected ? 'Verbunden' : 'Nicht angemeldet');
  return (
    <article className={`card${compact ? ' card-compact' : ''}`} aria-labelledby={id}>
      <div className="card-summary">
        <div className="identity">
          <span className="avatar" aria-hidden="true"><ProviderLogo provider={account.provider} size={compact ? 32 : 44} /></span>
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
