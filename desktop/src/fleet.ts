/**
 * Typed Agent Fleet commands over the fixed transport. Responses are validated
 * here so views never trust arbitrary JSON shapes.
 */
import { FleetError, type Transport } from './api';
import { KEY_PATTERN } from './ids';
import type {
  Account, DoctorCheck, JobDetail, JobSummary, LoginSession, LoginStateName, Provider, QuotaWindow,
  RemoteConfig, RemoteMap, RemoteTestResult, StatusData, Target, WorkerState,
} from './types';

type Json = Record<string, unknown>;

const LOGIN_STATES: ReadonlySet<string> = new Set([
  'starting', 'awaiting_browser', 'awaiting_code', 'verifying', 'succeeded', 'failed', 'cancelled', 'expired',
]);

function record(value: unknown): Json | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Json) : null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Unix seconds; tolerates milliseconds and ISO strings from other producers. */
export function seconds(value: unknown): number | null {
  if (typeof value === 'string' && value.trim()) {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed / 1000;
  }
  const n = finite(value);
  if (n === null) return null;
  return n > 1e11 ? n / 1000 : n;
}

function provider(value: unknown): Provider | null {
  return value === 'codex' || value === 'claude' ? value : null;
}

function invalid(what: string): never {
  throw new FleetError(`Unerwartete Antwort des Agent-Fleet-Kerns (${what}).`);
}

export function parseWindow(value: unknown): QuotaWindow | null {
  const w = record(value);
  if (!w) return null;
  return {
    key: text(w.key),
    bucket: text(w.bucket),
    minutes: finite(w.minutes),
    used: finite(w.used),
    reset: seconds(w.reset),
    model: text(w.model),
  };
}

export function parseAccount(value: unknown): Account | null {
  const a = record(value);
  const name = a && text(a.name);
  const kind = a && provider(a.provider);
  if (!a || !name || !kind) return null;
  return {
    name,
    provider: kind,
    managed: a.managed !== false,
    enabled: Boolean(a.enabled),
    connected: Boolean(a.connected),
    email: text(a.email),
    plan: text(a.plan),
    display_name: text(a.display_name),
    windows: Array.isArray(a.windows) ? a.windows.map(parseWindow).filter((w): w is QuotaWindow => w !== null) : [],
    observed_at: seconds(a.observed_at),
    checked_at: seconds(a.checked_at),
    error: text(a.error),
    hold_reason: text(a.hold_reason),
    hold_until: seconds(a.hold_until),
  };
}

function parseWorker(value: unknown): WorkerState | null {
  const w = record(value);
  if (!w) return null;
  return { online: w.online === true, age_seconds: finite(w.age_seconds), started_at: seconds(w.started_at) };
}

/** `status` and `overview` share one shape; a bare account list is accepted too. */
export function parseStatus(value: unknown): StatusData {
  const list = Array.isArray(value) ? value : record(value)?.accounts;
  if (!Array.isArray(list)) invalid('Accounts');
  const data = record(value) ?? {};
  return {
    accounts: list.map(parseAccount).filter((a): a is Account => a !== null),
    worker: parseWorker(data.worker),
    pending_jobs: finite(data.pending_jobs),
    features: Array.isArray(data.features) ? data.features.filter((f): f is string => typeof f === 'string') : [],
    version: text(data.version),
  };
}

function parseRemoteConfig(value: unknown): RemoteConfig | null {
  const c = record(value);
  const host = c && text(c.host);
  const command = c && text(c.command);
  const home = c && (text(c.home) ?? text(c.server_home));
  return host && command && home ? { host, command, home } : null;
}

export function parseRemotes(value: unknown): RemoteMap {
  const map = record(value);
  if (!map) invalid('Verbindungen');
  const result: RemoteMap = {};
  for (const [name, config] of Object.entries(map)) {
    const parsed = parseRemoteConfig(config);
    if (parsed) result[name] = parsed;
  }
  return result;
}

export function parseLogin(value: unknown): LoginSession {
  const s = record(value);
  const id = s && text(s.id);
  const kind = s && provider(s.provider);
  const state = s && text(s.state);
  if (!s || !id || !kind || !state || !LOGIN_STATES.has(state)) invalid('Anmeldung');
  return {
    id,
    profile: text(s.profile) ?? '',
    provider: kind,
    state: state as LoginStateName,
    url: text(s.url),
    device_code: text(s.device_code),
    message: text(s.message),
    updated_at: seconds(s.updated_at),
    expires_at: seconds(s.expires_at),
  };
}

function parseJob(value: unknown): JobDetail | null {
  const j = record(value);
  const id = j && text(j.id);
  if (!j || !id) return null;
  return {
    id,
    status: text(j.status) ?? 'unknown',
    provider: text(j.provider) ?? '',
    profile: text(j.profile),
    chosen_profile: text(j.chosen_profile),
    model: text(j.model),
    cwd: text(j.cwd),
    allow_edits: j.allow_edits === true || j.allow_edits === 1,
    attempts: finite(j.attempts),
    max_attempts: finite(j.max_attempts),
    idempotency_key: text(j.idempotency_key),
    created: seconds(j.created),
    updated: seconds(j.updated),
    error: text(j.error),
    result: typeof j.result === 'string' ? j.result : null,
  };
}

export class Fleet {
  constructor(private readonly transport: Transport) {}

  get demo(): boolean {
    return this.transport.demo;
  }

  openLoginUrl(url: string): Promise<void> {
    return this.transport.openLoginUrl(url);
  }

  /** Local includes the native default Codex login; remote reads the server's cached status. */
  async accounts(target: Target, refresh: boolean): Promise<StatusData> {
    if (target === null) return parseStatus(await this.transport.request(null, refresh ? ['overview', '--refresh'] : ['overview']));
    return parseStatus(await this.transport.request(target, ['status']));
  }

  async remoteStatus(name: string): Promise<StatusData> {
    return parseStatus(await this.transport.request(name, ['status']));
  }

  async remotes(): Promise<RemoteMap> {
    return parseRemotes(await this.transport.request(null, ['remote', 'list']));
  }

  async discover(host: string): Promise<RemoteConfig> {
    const data = record(await this.transport.request(null, ['remote', 'discover', host]));
    const config = parseRemoteConfig({ host, ...(record(data?.config) ?? data ?? {}) });
    if (!config) invalid('Erkennung');
    return config;
  }

  async addRemote(name: string, config: RemoteConfig): Promise<RemoteMap> {
    return parseRemotes(await this.transport.request(null, [
      'remote', 'add', name, '--host', config.host, '--command', config.command, '--server-home', config.home,
    ]));
  }

  async removeRemote(name: string): Promise<RemoteMap> {
    return parseRemotes(await this.transport.request(null, ['remote', 'remove', name]));
  }

  async testRemote(name: string): Promise<RemoteTestResult> {
    const raw = record(await this.transport.request(null, ['remote', 'test', name]))?.checks;
    const checks: DoctorCheck[] = Array.isArray(raw)
      ? raw.map(record).filter((c): c is Json => c !== null).map((c) => ({
          provider: text(c.provider) ?? '',
          ok: c.ok === true,
          version: text(c.version),
          error: text(c.error),
        }))
      : [];
    return { checks };
  }

  async authStart(target: Target, name: string, kind: Provider, key: string): Promise<LoginSession> {
    if (!KEY_PATTERN.test(key)) throw new FleetError('Ungültiger Anmeldeschlüssel.');
    return parseLogin(await this.transport.request(target, ['auth', 'start', name, '--provider', kind, '--key', key]));
  }

  async authGet(target: Target, id: string): Promise<LoginSession> {
    return parseLogin(await this.transport.request(target, ['auth', 'get', id]));
  }

  async authInput(target: Target, id: string, code: string): Promise<void> {
    await this.transport.request(target, ['auth', 'input', id, '--code=' + code]);
  }

  async authCancel(target: Target, id: string): Promise<void> {
    await this.transport.request(target, ['auth', 'cancel', id]);
  }

  async setProfileEnabled(target: Target, name: string, enabled: boolean): Promise<void> {
    await this.transport.request(target, ['profile', enabled ? 'enable' : 'disable', name]);
  }

  async jobs(target: Target): Promise<JobSummary[]> {
    const data = await this.transport.request(target, ['job', 'list']);
    if (!Array.isArray(data)) invalid('Aufträge');
    return data.map(parseJob).filter((j): j is JobDetail => j !== null);
  }

  async job(target: Target, id: string): Promise<JobDetail> {
    const job = parseJob(await this.transport.request(target, ['job', 'get', id]));
    if (!job) invalid('Auftrag');
    return job;
  }
}
