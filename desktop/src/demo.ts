/**
 * Seeded browser preview. Loaded only when VITE_FLEET_DEMO=1 and the page is not
 * running inside Tauri; the UI then shows a permanent "Vorschaudaten" banner.
 * It contacts no provider and opens no URL.
 */
import { FleetError, type Transport } from './api';
import type { Target } from './types';

type Json = Record<string, unknown>;

const now = () => Date.now() / 1000;

function demoAccounts(remote: boolean): Json[] {
  const t = now();
  if (remote) {
    return [{
      name: 'server-codex', provider: 'codex', managed: true, enabled: true, connected: true, email: 'server@example.com',
      plan: 'pro', observed_at: t - 40, checked_at: t - 40, error: null, hold_reason: null, hold_until: null,
      windows: [{ key: 'codex:secondary', bucket: 'codex', minutes: 10080, used: 19, reset: t + 6 * 86400 + 14 * 3600, model: null }],
    }];
  }
  return [
    {
      name: '@codex-default', provider: 'codex', managed: false, enabled: false, connected: true, email: 'privat@example.com',
      plan: 'pro', observed_at: t - 30, checked_at: t - 30, error: null, hold_reason: null, hold_until: null,
      windows: [
        { key: 'codex:primary', bucket: 'codex', minutes: 300, used: 28, reset: t + 2 * 3600 + 1200, model: null },
        { key: 'codex:secondary', bucket: 'codex', minutes: 10080, used: 59, reset: t + 4 * 86400, model: null },
      ],
    },
    {
      name: 'arbeit', provider: 'codex', managed: true, enabled: true, connected: true, email: 'arbeit@example.com',
      plan: 'team', observed_at: t - 30, checked_at: t - 30, error: null, hold_reason: null, hold_until: null,
      windows: [
        { key: 'codex:primary', bucket: 'codex', minutes: 300, used: 8, reset: t + 4 * 3600, model: null },
        { key: 'codex:secondary', bucket: 'codex', minutes: 10080, used: 14, reset: t + 5 * 86400, model: null },
      ],
    },
    {
      name: 'team', provider: 'claude', managed: true, enabled: true, connected: true, email: 'team@example.com',
      plan: 'max', observed_at: t - 600, checked_at: t - 20, error: null, hold_reason: null, hold_until: null,
      windows: [
        { key: 'five_hour', bucket: 'claude', minutes: 300, used: 82, reset: t + 45 * 60, model: null },
        { key: 'seven_day', bucket: 'claude', minutes: 10080, used: 88, reset: t + 2 * 86400, model: null },
        { key: 'seven_day_opus', bucket: 'claude', minutes: 10080, used: null, reset: null, model: 'opus' },
      ],
    },
    {
      name: 'reserve', provider: 'claude', managed: true, enabled: false, connected: false, email: null,
      plan: null, observed_at: null, checked_at: null, error: null, hold_reason: null, hold_until: null, windows: [],
    },
  ];
}

interface DemoLogin extends Json {
  id: string; profile: string; provider: string; state: string; polls: number;
}

export function createDemoTransport(): Transport {
  const remotes: Record<string, Json> = { 'Linux Server': { host: 'demo-host', command: '/usr/local/bin/agent-fleet', home: '/srv/agent-fleet' } };
  const enabled = new Map<string, boolean>();
  const logins = new Map<string, DemoLogin>();
  const jobs: Json[] = [{
    id: '3e700bf6dd774f24a3a4ef3998b4517d', status: 'succeeded', provider: 'codex', chosen_profile: 'arbeit', model: null,
    allow_edits: false, attempts: 1, max_attempts: 6, created: now() - 3600, updated: now() - 3500, error: null,
    idempotency_key: '0123456789abcdef0123456789abcdef', result: 'Beispielbericht: Die Prüfung ist abgeschlossen.',
  }];

  const accounts = (target: Target) => demoAccounts(target !== null).map((a) =>
    enabled.has(a.name as string) ? { ...a, enabled: enabled.get(a.name as string) } : a);

  const session = (login: DemoLogin): Json => {
    const copy: Json = { ...login, updated_at: now(), expires_at: now() + 900 };
    delete copy.polls;
    return copy;
  };

  const handle = (target: Target, argv: string[]): unknown => {
    const [action, operation, arg] = argv;
    if (target !== null && !(target in remotes)) throw new FleetError('Unbekannte Verbindung: ' + target);
    switch (action) {
      case 'overview':
      case 'status':
        return { accounts: accounts(target), worker: { online: target !== null, age_seconds: 4 }, pending_jobs: 0,
          features: ['native-login-sessions', 'cached-status'], version: '0.5.2' };
      case 'remote':
        if (operation === 'discover') return { host: arg, command: '/usr/local/bin/agent-fleet', home: '/srv/agent-fleet', features: ['native-login-sessions'] };
        if (operation === 'add') {
          const value = (flag: string) => argv[argv.indexOf(flag) + 1];
          remotes[arg] = { host: value('--host'), command: value('--command'), home: value('--server-home') };
        }
        if (operation === 'remove') delete remotes[arg];
        if (operation === 'test') return { checks: [{ provider: 'codex', ok: true, version: 'codex-cli (Vorschau)' }, { provider: 'claude', ok: false, error: 'nicht installiert' }] };
        return { ...remotes };
      case 'profile':
        enabled.set(arg, operation === 'enable');
        return [];
      case 'auth': {
        if (operation === 'start') {
          const provider = argv[argv.indexOf('--provider') + 1];
          const key = argv[argv.indexOf('--key') + 1];
          const existing = logins.get(key);
          if (existing) return session(existing);
          const login: DemoLogin = provider === 'codex'
            ? { id: key, profile: arg, provider, state: 'awaiting_browser', polls: 0, url: 'https://auth.openai.com/codex/device', device_code: 'DEMO-CODE1', message: 'Bestätige die Anmeldung im Browser.' }
            : { id: key, profile: arg, provider, state: 'awaiting_code', polls: 0, url: 'https://claude.ai/oauth/authorize', device_code: null, message: 'Öffne die Anmeldeseite. Falls ein Code erscheint, füge ihn hier ein.' };
          logins.set(key, login);
          return session(login);
        }
        const login = logins.get(arg);
        if (!login) throw new FleetError('Unknown login session');
        if (operation === 'cancel') {
          const active = ['awaiting_browser', 'awaiting_code', 'verifying', 'starting'].includes(login.state);
          if (active) Object.assign(login, { state: 'cancelled', message: 'Anmeldung abgebrochen.', url: null, device_code: null });
          return { id: login.id, cancel_requested: active };
        }
        if (operation === 'input') {
          Object.assign(login, { state: 'verifying', message: 'Anmeldung wird bestätigt …' });
          return { accepted: true, id: login.id };
        }
        login.polls += 1;
        if (login.state === 'verifying' || (login.provider === 'codex' && login.state === 'awaiting_browser' && login.polls > 6)) {
          Object.assign(login, { state: 'succeeded', message: 'Account verbunden.', url: null, device_code: null });
        }
        return session(login);
      }
      case 'job':
        if (operation === 'list') {
          return jobs.map((job) => {
            const summary: Json = { ...job };
            delete summary.result;
            return summary;
          });
        }
        if (operation === 'get') {
          const job = jobs.find((j) => j.id === arg);
          if (!job) throw new FleetError('Unknown job: ' + arg);
          return job;
        }
        break;
      default:
        break;
    }
    throw new FleetError('In der Vorschau nicht verfügbar.');
  };

  return {
    demo: true,
    request: (target, argv) => new Promise((resolve, reject) => {
      setTimeout(() => {
        try {
          resolve(handle(target, argv));
        } catch (error) {
          reject(error);
        }
      }, 250);
    }),
    initialConfig: async () => ({ home: '~/.agent-fleet', target: null, version: '0.5.2' }),
    openLoginUrl: async () => undefined,
  };
}
