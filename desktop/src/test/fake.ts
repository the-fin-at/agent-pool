import type { Transport } from '../api';
import type { InitialConfig, Target } from '../types';

export interface Call {
  target: Target;
  argv: string[];
}

export type Handler = (target: Target, argv: string[]) => unknown;

/** Records every bridge call; the handler may return a value, a promise or throw. */
export function fakeTransport(handler: Handler, config: Partial<InitialConfig> = {}) {
  const calls: Call[] = [];
  const opened: string[] = [];
  const transport: Transport = {
    demo: false,
    request: async (target, argv) => {
      calls.push({ target, argv: [...argv] });
      return handler(target, argv);
    },
    initialConfig: async () => ({ home: '/home/test/.agent-fleet', target: null, version: '0.5.0', ...config }),
    openLoginUrl: async (url) => {
      opened.push(url);
    },
  };
  const commands = (target?: Target) => calls.filter((c) => target === undefined || c.target === target).map((c) => c.argv.join(' '));
  return { transport, calls, opened, commands };
}

export function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const now = () => Date.now() / 1000;

export function codexAccount(name: string, extra: Record<string, unknown> = {}) {
  return {
    name, provider: 'codex', managed: true, enabled: true, connected: true, email: `${name}@example.com`, plan: 'pro',
    observed_at: now() - 10, checked_at: now() - 10, error: null, hold_reason: null, hold_until: null,
    windows: [
      { key: 'codex:primary', bucket: 'codex', minutes: 300, used: 28, reset: now() + 7200, model: null },
      { key: 'codex:secondary', bucket: 'codex', minutes: 10080, used: 59, reset: now() + 4 * 86400, model: null },
    ],
    ...extra,
  };
}

export function claudeAccount(name: string, extra: Record<string, unknown> = {}) {
  return {
    name, provider: 'claude', managed: true, enabled: false, connected: true, email: `${name}@example.com`, plan: 'max',
    observed_at: now() - 10, checked_at: now() - 10, error: null, hold_reason: null, hold_until: null,
    windows: [{ key: 'seven_day', bucket: 'claude', minutes: 10080, used: 19, reset: now() + 86400, model: null }],
    ...extra,
  };
}

export function status(accounts: unknown[], extra: Record<string, unknown> = {}) {
  return { accounts, worker: { online: true, age_seconds: 3 }, pending_jobs: 0, features: ['native-login-sessions', 'cached-status'], version: '0.5.0', ...extra };
}

export const FAST = { autoRefreshMs: 3_600_000, loginPollMs: 15, clockMs: 3_600_000 };
