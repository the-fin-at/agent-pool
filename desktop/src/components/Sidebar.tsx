import { Icon, type IconName } from '../icons';
import type { Provider, WorkerState } from '../types';
import { Toggle } from './ui';

export type ProviderFilter = 'all' | Provider;

export const FILTERS: { value: ProviderFilter; label: string; icon: IconName }[] = [
  { value: 'all', label: 'Alle Accounts', icon: 'people' },
  { value: 'codex', label: 'Codex', icon: 'hdd-stack' },
  { value: 'claude', label: 'Claude', icon: 'diagram-3' },
];

export const AUTO_REFRESH_LABEL = 'Alle 60 Sekunden aktualisieren';

export interface NavProps {
  scope: 'local' | 'remote';
  remote: string | null;
  remotes: string[];
  filter: ProviderFilter;
  /** Which entry is current: a provider filter, the jobs page or a connection page. */
  section: 'accounts' | 'jobs' | 'connections' | 'other';
  autoRefresh: boolean;
  worker: WorkerState | null;
  version: string;
  onFilter: (value: ProviderFilter) => void;
  onJobs: () => void;
  onConnections: () => void;
  onRemote: (name: string) => void;
  onAutoRefresh: (value: boolean) => void;
}

function workerText(scope: NavProps['scope'], remote: string | null, worker: WorkerState | null): { text: string; tone: string } {
  if (scope === 'remote' && !remote) return { text: 'Remote-Verbindungen', tone: 'muted' };
  if (worker === null) return { text: scope === 'local' ? 'Auf diesem Rechner' : 'Worker-Status unbekannt', tone: 'muted' };
  if (worker.online) return { text: 'Worker aktiv', tone: 'success' };
  return { text: scope === 'remote' ? 'Worker nicht erreichbar' : 'Kein Worker aktiv', tone: scope === 'remote' ? 'warning' : 'muted' };
}

export function Sidebar(props: NavProps) {
  const { scope, remote, remotes, filter, section } = props;
  const jobsDisabled = scope === 'remote' && !remote;
  const worker = workerText(scope, remote, props.worker);
  return (
    <aside className="sidebar" aria-label="Navigation">
      <nav className="side-nav">
        <h2 className="side-heading">Übersicht</h2>
        <ul>
          {FILTERS.map((item) => (
            <li key={item.value}>
              <button type="button" className="nav-item" aria-current={section === 'accounts' && filter === item.value ? 'page' : undefined}
                onClick={() => props.onFilter(item.value)}>
                <Icon name={item.icon} size={24} />
                <span>{item.label}</span>
              </button>
            </li>
          ))}
          <li>
            <button type="button" className="nav-item" aria-current={section === 'jobs' ? 'page' : undefined}
              disabled={jobsDisabled} title={jobsDisabled ? 'Zuerst eine Verbindung öffnen' : undefined} onClick={props.onJobs}>
              <Icon name="list-task" size={24} />
              <span>Aufträge</span>
            </button>
          </li>
        </ul>
        {scope === 'remote' && (
          <>
            <h2 className="side-heading">Verbindungen</h2>
            <ul>
              <li>
                <button type="button" className="nav-item nav-small" aria-current={section === 'connections' ? 'page' : undefined}
                  onClick={props.onConnections}>
                  <Icon name="globe2" size={20} />
                  <span>Alle Verbindungen</span>
                </button>
              </li>
              {remotes.map((name) => (
                <li key={name}>
                  <button type="button" className="nav-item nav-small" aria-current={remote === name ? 'true' : undefined}
                    onClick={() => props.onRemote(name)}>
                    <Icon name="server" size={20} />
                    <span>{name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>
      <div className="side-bottom">
        <Toggle checked={props.autoRefresh} onChange={props.onAutoRefresh} label={AUTO_REFRESH_LABEL} />
        <p className={`side-status tone-${worker.tone}`}>{worker.text}</p>
        {props.version && <p className="side-version">Version {props.version}</p>}
      </div>
    </aside>
  );
}

/** Below 880 px: one labelled row instead of the sidebar. */
export function CompactNav(props: NavProps) {
  const { scope, remote, filter, section } = props;
  return (
    <nav className="compact-nav" aria-label="Navigation">
      <div className="compact-row">
        {FILTERS.map((item) => (
          <button key={item.value} type="button" className="tab" aria-current={section === 'accounts' && filter === item.value ? 'page' : undefined}
            onClick={() => props.onFilter(item.value)}>{item.label}</button>
        ))}
        <button type="button" className="tab" aria-current={section === 'jobs' ? 'page' : undefined}
          disabled={scope === 'remote' && !remote} onClick={props.onJobs}>Aufträge</button>
        {scope === 'remote' && (
          <button type="button" className="tab" aria-current={section === 'connections' ? 'page' : undefined}
            onClick={props.onConnections}>Verbindungen</button>
        )}
      </div>
      <div className="compact-row compact-meta">
        <Toggle checked={props.autoRefresh} onChange={props.onAutoRefresh} label={AUTO_REFRESH_LABEL} />
        {scope === 'remote' && remote && <span className="compact-remote"><Icon name="server" size={16} /> {remote}</span>}
      </div>
    </nav>
  );
}
