import { useEffect, useMemo, useRef } from 'react';
import { Icon } from '../icons';
import { accountView, connectedAccountCount, matchesSearch, sortAccounts } from '../quota';
import type { Account, StatusData } from '../types';
import { AccountCard } from './AccountCard';
import { FILTERS, type ProviderFilter } from './Sidebar';
import { Button, IconButton, Notice, PageHeader } from './ui';

export interface AccountsState {
  data: StatusData | null;
  error: string | null;
  loading: boolean;
  refreshedAt: number | null;
}

export function connectedLabel(count: number): string {
  return `${count} ${count === 1 ? 'Account verbunden' : 'Accounts verbunden'}`;
}

export function AccountsView(props: {
  state: AccountsState;
  filter: ProviderFilter;
  search: string;
  showAll: boolean;
  now: number;
  compact: boolean;
  remote: string | null;
  onSearch: (value: string) => void;
  onShowAll: (value: boolean) => void;
  onRefresh: () => void;
  onAdd: () => void;
  onDetails: (account: Account) => void;
  onLogin: (account: Account) => void;
  onBack: (() => void) | null;
}) {
  const { state, filter, search, showAll, now, compact } = props;
  const searchField = useRef<HTMLInputElement>(null);
  const refresh = useRef(props.onRefresh);
  refresh.current = props.onRefresh;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
      const key = event.key.toLowerCase();
      if (key === 'f') {
        event.preventDefault();
        searchField.current?.focus();
      } else if (key === 'r') {
        event.preventDefault();
        refresh.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const inProvider = useMemo(
    () => (state.data?.accounts ?? []).filter((a) => filter === 'all' || a.provider === filter),
    [state.data, filter],
  );
  const visible = useMemo(
    () => {
      if (showAll) return sortAccounts(inProvider.filter((account) => matchesSearch(account, search)));

      const groups = new Map<string, Account[]>();
      for (const account of inProvider) {
        const key = `${account.provider}:${account.alias_of ?? account.name}`;
        const members = groups.get(key) ?? [];
        members.push(account);
        groups.set(key, members);
      }

      return sortAccounts([...groups.values()].flatMap((members) => {
        const connected = members.filter((account) => account.connected);
        const representative = connected.find((account) => account.auth_mode === 'native_default')
          ?? connected.find((account) => !account.alias_of)
          ?? connected[0];
        return representative && members.some((account) => matchesSearch(account, search)) ? [representative] : [];
      }));
    },
    [inProvider, showAll, search],
  );
  const connected = connectedAccountCount(inProvider);
  const title = FILTERS.find((f) => f.value === filter)?.label ?? 'Alle Accounts';
  const query = search.trim();

  return (
    <>
      <PageHeader
        title={title}
        back={props.onBack ? { label: 'Verbindungen', onClick: props.onBack } : undefined}
        subtitle={state.data ? connectedLabel(connected) : undefined}
        actions={
          <>
            <Button variant="primary" icon="plus-lg" onClick={props.onAdd}>Account hinzufügen</Button>
            <IconButton icon="arrow-clockwise" label="Aktualisieren" busy={state.loading} disabled={state.loading} onClick={props.onRefresh} />
          </>
        }
      />
      <div className="toolbar">
        <label className="check">
          <input type="checkbox" checked={showAll} onChange={(e) => props.onShowAll(e.target.checked)} />
          <span>Alle Profile anzeigen</span>
        </label>
        <div className="search">
          <Icon name="search" size={18} />
          <input ref={searchField} type="search" aria-label="Accounts durchsuchen" placeholder="Accounts durchsuchen …"
            value={search} onChange={(e) => props.onSearch(e.target.value)} />
        </div>
      </div>
      {state.error && (
        <Notice title="Abfrage fehlgeschlagen" action={{ label: 'Erneut versuchen', onClick: props.onRefresh, disabled: state.loading }}>
          <p>{state.error}</p>
          {state.data && <p>Angezeigt wird der zuletzt abgefragte Stand.</p>}
        </Notice>
      )}
      {!state.data && state.loading && <p className="loading" role="status">Accounts werden abgefragt …</p>}
      {state.data && visible.length === 0 && (
        <section className="empty">
          <h2>{query ? 'Keine passenden Accounts' : 'Noch keine verbundenen Accounts'}</h2>
          <p>{query ? 'Ändere die Suche oder lösche den Suchtext.' : 'Verbinde einen Account, um seine Kontingente hier zu sehen.'}</p>
          {!query && <Button variant="primary" onClick={props.onAdd}>Account verbinden</Button>}
        </section>
      )}
      {visible.length > 0 && (
        <ul className="card-grid" aria-label="Accounts">
          {visible.map((account) => (
            <li key={account.name}>
              <AccountCard view={accountView(account, now)} compact={compact}
                onDetails={() => props.onDetails(account)} onLogin={() => props.onLogin(account)} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
