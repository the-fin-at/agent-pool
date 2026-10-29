import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { errorMessage, type Transport } from './api';
import { AccountDetails } from './components/AccountDetails';
import { AccountsView, type AccountsState } from './components/AccountsView';
import { ConnectionForm } from './components/ConnectionForm';
import { ConnectionsView, type ConnectionSummary, type RemotesState } from './components/ConnectionsView';
import { JobsView } from './components/JobsView';
import { LoginView, type LoginSeed } from './components/LoginView';
import { CompactNav, Sidebar, type NavProps, type ProviderFilter } from './components/Sidebar';
import { TopBar, type Scope } from './components/TopBar';
import { Button } from './components/ui';
import { Fleet } from './fleet';
import { useMediaQuery, useNow } from './hooks';
import { connectedAccountCount, formatClock } from './quota';
import type { Account, RemoteMap, StatusData, Target } from './types';

export interface Timing {
  autoRefreshMs: number;
  loginPollMs: number;
  clockMs: number;
}

const DEFAULT_TIMING: Timing = { autoRefreshMs: 60_000, loginPollMs: 1_200, clockMs: 10_000 };

type Page = 'accounts' | 'details' | 'login' | 'connections' | 'connect' | 'jobs';

const NO_ACCOUNTS: AccountsState = { data: null, error: null, loading: false, refreshedAt: null };

async function limited<T>(items: T[], limit: number, run: (item: T) => Promise<void>): Promise<void> {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length) await run(queue.shift() as T);
  });
  await Promise.all(workers);
}

export function App({ transport, timing: override }: { transport: Transport; timing?: Partial<Timing> }) {
  const timing = useMemo(() => ({ ...DEFAULT_TIMING, ...override }), [override]);
  const fleet = useMemo(() => new Fleet(transport), [transport]);
  const compact = useMediaQuery('(max-width: 879px)');

  const [boot, setBoot] = useState<'loading' | 'ready' | 'error'>('loading');
  const [bootError, setBootError] = useState<string | null>(null);
  const [version, setVersion] = useState('');
  const [scope, setScope] = useState<Scope>('local');
  const [remote, setRemote] = useState<string | null>(null);
  const [page, setPage] = useState<Page>('accounts');
  const [filter, setFilter] = useState<ProviderFilter>('all');
  const [search, setSearch] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [accounts, setAccounts] = useState<AccountsState>(NO_ACCOUNTS);
  const [nextRefreshAt, setNextRefreshAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [detailName, setDetailName] = useState<string | null>(null);
  const [loginSeed, setLoginSeed] = useState<LoginSeed | null>(null);
  const [loginInstance, setLoginInstance] = useState(0);
  const [remotes, setRemotes] = useState<RemotesState>({ map: null, error: null, loading: false });
  const [summaries, setSummaries] = useState<Record<string, ConnectionSummary>>({});

  const target: Target = scope === 'local' ? null : remote;
  const hasTarget = scope === 'local' || remote !== null;

  /** Incremented on every computer switch; responses of an older context are dropped. */
  const contextRef = useRef(0);
  const inflightRef = useRef<number | null>(null);
  const pageRef = useRef(page);
  pageRef.current = page;
  const remotesGen = useRef(0);
  const remotesLoad = useRef<Promise<RemoteMap | null> | null>(null);
  const remotesMap = useRef<RemoteMap | null>(null);
  const probeTokens = useRef<Record<string, number>>({});
  const probeSeq = useRef(0);
  const probing = useRef(false);
  /** Identifies the currently open connection form; older forms may not navigate. */
  const formRef = useRef(0);
  const [formId, setFormId] = useState(0);

  const startBoot = useCallback(() => {
    setBoot('loading');
    setBootError(null);
    transport.initialConfig().then(
      (config) => {
        setVersion(config.version);
        if (config.target) {
          contextRef.current += 1;
          setScope('remote');
          setRemote(config.target);
        }
        setBoot('ready');
      },
      (error: unknown) => {
        setBootError(errorMessage(error));
        setBoot('error');
      },
    );
  }, [transport]);

  useEffect(() => startBoot(), [startBoot]);

  const switchContext = useCallback((nextScope: Scope, nextRemote: string | null) => {
    contextRef.current += 1;
    inflightRef.current = null;
    setScope(nextScope);
    setRemote(nextRemote);
    setAccounts(NO_ACCOUNTS);
    setDetailName(null);
    setSearch('');
    setFilter('all');
    setNextRefreshAt(null);
    setPage(nextScope === 'remote' && nextRemote === null ? 'connections' : 'accounts');
  }, []);

  const loadAccounts = useCallback(async (requestTarget: Target, refresh: boolean): Promise<void> => {
    const epoch = contextRef.current;
    if (inflightRef.current === epoch) return;
    inflightRef.current = epoch;
    setAccounts((s) => ({ ...s, loading: true }));
    try {
      const data: StatusData = await fleet.accounts(requestTarget, refresh);
      if (epoch !== contextRef.current) return;
      setAccounts({ data, error: null, loading: false, refreshedAt: Date.now() / 1000 });
      setNow(Date.now() / 1000);
    } catch (error) {
      if (epoch !== contextRef.current) return;
      setAccounts((s) => ({ ...s, error: errorMessage(error), loading: false }));
    } finally {
      if (inflightRef.current === epoch) inflightRef.current = null;
      if (epoch === contextRef.current) setNextRefreshAt(Date.now() + timing.autoRefreshMs);
    }
  }, [fleet, timing.autoRefreshMs]);

  // A new computer shows its cached state first; locally a provider refresh follows.
  useEffect(() => {
    if (boot !== 'ready' || !hasTarget) return;
    const epoch = contextRef.current;
    void loadAccounts(target, false).then(() => {
      if (target === null && epoch === contextRef.current) void loadAccounts(null, true);
    });
  }, [boot, hasTarget, target, loadAccounts]);

  /** A map from add/remove is authoritative; list reads started before it are discarded. */
  const applyRemotes = useCallback((map: RemoteMap) => {
    remotesGen.current += 1;
    remotesLoad.current = null;
    remotesMap.current = map;
    setRemotes({ map, error: null, loading: false });
  }, []);

  /** Concurrent callers share one `remote list` read instead of superseding each other. */
  const loadRemotes = useCallback((): Promise<RemoteMap | null> => {
    if (remotesLoad.current) return remotesLoad.current;
    const gen = ++remotesGen.current;
    setRemotes((s) => ({ ...s, loading: true, error: null }));
    const load: Promise<RemoteMap | null> = (async () => {
      try {
        const map = await fleet.remotes();
        if (gen !== remotesGen.current) return null;
        remotesMap.current = map;
        setRemotes({ map, error: null, loading: false });
        return map;
      } catch (error) {
        if (gen === remotesGen.current) setRemotes((s) => ({ ...s, error: errorMessage(error), loading: false }));
        return null;
      } finally {
        if (gen === remotesGen.current) remotesLoad.current = null;
      }
    })();
    remotesLoad.current = load;
    return load;
  }, [fleet]);

  /** Fresh read after a change elsewhere; any older read or snapshot loses to it. */
  const reloadRemotes = useCallback((): Promise<RemoteMap | null> => {
    remotesGen.current += 1;
    remotesLoad.current = null;
    return loadRemotes();
  }, [loadRemotes]);

  const probe = useCallback(async (names: string[]) => {
    await limited(names, 3, async (name) => {
      const token = ++probeSeq.current;
      probeTokens.current[name] = token;
      setSummaries((s) => ({ ...s, [name]: { state: 'checking' } }));
      let summary: ConnectionSummary;
      try {
        const data = await fleet.remoteStatus(name);
        summary = { state: 'ok', connected: connectedAccountCount(data.accounts), workerOnline: data.worker?.online ?? null };
      } catch (error) {
        summary = { state: 'error', error: errorMessage(error) };
      }
      if (probeTokens.current[name] === token) setSummaries((s) => ({ ...s, [name]: summary }));
    });
  }, [fleet]);

  const probeAll = useCallback(async () => {
    if (probing.current) return;
    probing.current = true;
    try {
      // A superseded read yields null; the newer authoritative map is then probed.
      const map = (await loadRemotes()) ?? remotesMap.current;
      if (map) await probe(Object.keys(map));
    } finally {
      probing.current = false;
      setNextRefreshAt(Date.now() + timing.autoRefreshMs);
    }
  }, [loadRemotes, probe, timing.autoRefreshMs]);

  useEffect(() => {
    if (boot === 'ready' && scope === 'remote' && page === 'connections') void probeAll();
  }, [boot, scope, page, probeAll]);

  // Sidebar list for a directly opened server; the connections page loads it via probeAll.
  useEffect(() => {
    if (boot === 'ready' && scope === 'remote' && page !== 'connections' && remotes.map === null && !remotes.loading && !remotes.error) {
      void loadRemotes();
    }
  }, [boot, scope, page, remotes, loadRemotes]);

  // Auto refresh: accounts reread, connections reprobed; other pages only reschedule.
  const autoRun = useRef<() => void>(() => undefined);
  autoRun.current = () => {
    const current = pageRef.current;
    if ((current === 'accounts' || current === 'details') && hasTarget) void loadAccounts(target, true);
    else if (current === 'connections') void probeAll();
    else setNextRefreshAt(Date.now() + timing.autoRefreshMs);
  };
  useEffect(() => {
    if (!autoRefresh || nextRefreshAt === null) return;
    const id = window.setTimeout(() => autoRun.current(), Math.max(0, nextRefreshAt - Date.now()));
    return () => window.clearTimeout(id);
  }, [autoRefresh, nextRefreshAt]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), timing.clockMs);
    return () => window.clearInterval(id);
  }, [timing.clockMs]);

  const refreshAccounts = () => {
    if (hasTarget) void loadAccounts(target, true);
  };

  const selectFilter = (value: ProviderFilter) => {
    setFilter(value);
    setDetailName(null);
    if (hasTarget) setPage('accounts');
  };

  const showLogin = (account?: Account) => {
    if (!hasTarget) return;
    setLoginSeed(account && account.managed ? { name: account.name, provider: account.provider } : null);
    setLoginInstance((n) => n + 1);
    setPage('login');
  };

  const addConnection = () => {
    formRef.current += 1;
    setFormId(formRef.current);
    switchContext('remote', null);
    setPage('connect');
  };

  const removeConnection = async (name: string) => {
    applyRemotes(await fleet.removeRemote(name));
    delete probeTokens.current[name];
    setSummaries((s) => {
      const next = { ...s };
      delete next[name];
      return next;
    });
    if (remote === name) switchContext('remote', null);
  };

  /**
   * Any form's completion reconciles the registry with a fresh read, never with a map
   * captured before its delayed check. Only the form that is still open navigates.
   */
  const onConnectionSaved = (origin: number, name: string, status: StatusData) => {
    void reloadRemotes();
    probeTokens.current[name] = ++probeSeq.current;
    setSummaries((s) => ({ ...s, [name]: { state: 'ok', connected: connectedAccountCount(status.accounts), workerOnline: status.worker?.online ?? null } }));
    if (pageRef.current === 'connect' && formRef.current === origin) switchContext('remote', name);
  };

  const finishLogin = () => {
    setShowAll(true);
    setPage('accounts');
    refreshAccounts();
  };

  const onEnabledChanged = (name: string, enabled: boolean) => {
    setAccounts((s) => (s.data
      ? { ...s, data: { ...s.data, accounts: s.data.accounts.map((a) => (a.name === name ? { ...a, enabled } : a)) } }
      : s));
    if (hasTarget) void loadAccounts(target, false);
  };

  if (boot !== 'ready') {
    return (
      <div className="boot">
        {transport.demo && <DemoBanner />}
        {boot === 'loading' ? (
          <p className="loading" role="status">Agent Fleet wird gestartet …</p>
        ) : (
          <div className="boot-error" role="alert">
            <h1>Agent Fleet konnte nicht starten</h1>
            <p className="plain-text">{bootError}</p>
            <Button variant="primary" onClick={startBoot}>Erneut versuchen</Button>
          </div>
        )}
      </div>
    );
  }

  const section: NavProps['section'] = page === 'accounts' || page === 'details' ? 'accounts'
    : page === 'jobs' ? 'jobs' : page === 'connections' ? 'connections' : 'other';
  const navProps: NavProps = {
    scope, remote, filter, section, autoRefresh, version,
    remotes: Object.keys(remotes.map ?? {}),
    worker: hasTarget ? accounts.data?.worker ?? null : null,
    onFilter: selectFilter,
    onJobs: () => {
      if (hasTarget) setPage('jobs');
    },
    onConnections: () => switchContext('remote', null),
    onRemote: (name) => switchContext('remote', name),
    onAutoRefresh: (value) => {
      setAutoRefresh(value);
      if (value) setNextRefreshAt((at) => at ?? Date.now() + timing.autoRefreshMs);
    },
  };
  const contextKey = `${scope}:${remote ?? ''}`;
  const detailAccount = accounts.data?.accounts.find((a) => a.name === detailName) ?? null;

  let content: ReactNode;
  switch (page) {
    case 'connections':
      content = (
        <ConnectionsView remotes={remotes} summaries={summaries} onOpen={(name) => switchContext('remote', name)}
          onAdd={addConnection} onRefresh={() => void probeAll()} onProbe={(name) => void probe([name])}
          onRemove={removeConnection} onTest={(name) => fleet.testRemote(name)} />
      );
      break;
    case 'connect':
      content = (
        <ConnectionForm key={formId} fleet={fleet} existing={remotes.map} onBack={() => setPage('connections')}
          onRegistryChanged={() => void reloadRemotes()}
          onSaved={(name, status) => onConnectionSaved(formId, name, status)} />
      );
      break;
    case 'login':
      content = (
        <LoginView key={`${contextKey}:${loginInstance}`} fleet={fleet} target={target} seed={loginSeed}
          pollMs={timing.loginPollMs} onBack={() => setPage('accounts')} onDone={finishLogin} />
      );
      break;
    case 'details':
      content = (
        <AccountDetails key={contextKey} account={detailAccount} now={now} fleet={fleet} target={target}
          onBack={() => setPage('accounts')} onLogin={showLogin} onEnabledChanged={onEnabledChanged} />
      );
      break;
    case 'jobs':
      content = <JobsView key={contextKey} fleet={fleet} target={target} worker={accounts.data?.worker ?? null} />;
      break;
    default:
      content = (
        <AccountsView state={accounts} filter={filter} search={search} showAll={showAll} now={now} compact={compact}
          remote={remote} onSearch={setSearch} onShowAll={setShowAll} onRefresh={refreshAccounts} onAdd={() => showLogin()}
          onDetails={(account) => { setDetailName(account.name); setPage('details'); }}
          onLogin={showLogin} onBack={scope === 'remote' ? () => switchContext('remote', null) : null} />
      );
  }

  return (
    <div className={`app${compact ? ' is-compact' : ''}`}>
      {transport.demo && <DemoBanner />}
      <TopBar scope={scope} remote={remote} onSelect={(value) => switchContext(value, null)} />
      <div className="frame">
        {!compact && <Sidebar {...navProps} />}
        <main className="main" id="main">
          {compact && <CompactNav {...navProps} />}
          <div className="content">{content}</div>
          <Footer page={page} accounts={accounts} remote={remote} autoRefresh={autoRefresh} nextRefreshAt={nextRefreshAt} />
        </main>
      </div>
    </div>
  );
}

function DemoBanner() {
  return (
    <p className="demo-banner" role="note">
      <strong>Vorschaudaten</strong> · Keine Verbindung zur Desktop-App. Alle Werte sind Beispiele.
    </p>
  );
}

const CAPTIONS: Partial<Record<Page, string>> = {
  connections: 'Verbindungen über SSH',
  connect: 'Verbindung mit einem entfernten Rechner',
  login: 'Anmeldung auf dem gewählten Rechner',
  jobs: 'Aufträge werden über CLI und Skill vergeben',
};

function Footer({ page, accounts, remote, autoRefresh, nextRefreshAt }: {
  page: Page;
  accounts: AccountsState;
  remote: string | null;
  autoRefresh: boolean;
  nextRefreshAt: number | null;
}) {
  const live = page === 'accounts' || page === 'details';
  const now = useNow(1000, live && autoRefresh);
  let text = CAPTIONS[page] ?? '';
  if (live) {
    if (accounts.loading) text = accounts.data ? 'Kontingente abrufen …' : 'Verbindung wird abgefragt …';
    else if (accounts.error) text = 'Abfrage fehlgeschlagen: ' + accounts.error.slice(0, 160);
    else if (accounts.refreshedAt && accounts.data) {
      const errors = accounts.data.accounts.filter((a) => a.error).length;
      text = 'Abgefragt ' + formatClock(accounts.refreshedAt);
      if (errors) text += errors === 1 ? ' · 1 Abfrage fehlgeschlagen' : ` · ${errors} Abfragen fehlgeschlagen`;
      if (remote) text += ' · ' + remote + (accounts.data.worker?.online ? ' · Worker aktiv' : ' · Worker offline');
      if (autoRefresh && nextRefreshAt) text += ` · Nächste Abfrage in ${Math.max(0, Math.ceil((nextRefreshAt - now) / 1000))} s`;
    } else text = 'Noch keine Kontingentdaten';
  }
  return <footer className="status-line" aria-live="off">{text}</footer>;
}
