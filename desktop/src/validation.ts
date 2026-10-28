/** Client-side checks that mirror the core's rules, so mistakes surface before a round trip. */
import type { Provider, RemoteMap } from './types';

/** Same hosts as agent_pool/login_sessions.LOGIN_HOSTS; the native side checks again. */
export const LOGIN_HOSTS: ReadonlySet<string> = new Set([
  'auth.openai.com', 'chatgpt.com', 'claude.ai', 'claude.com', 'console.anthropic.com', 'platform.claude.com',
]);

export function safeLoginUrl(value: string | null): URL | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const ok = url.protocol === 'https:' && LOGIN_HOSTS.has(url.hostname) && !url.username && !url.password
      && (url.port === '' || url.port === '443');
    return ok ? url : null;
  } catch {
    return null;
  }
}

const UMLAUTS: Record<string, string> = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' };

/** Profile name as created by 0.4.1: lowercase letters, digits, hyphens, starting with a letter. */
export function profileName(input: string, provider: Provider): string {
  let name = input.trim().toLowerCase().replace(/[äöüß]/g, (c) => UMLAUTS[c])
    .replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48);
  if (name && !/^[a-z]/.test(name)) name = provider + '-' + name.slice(0, 40);
  return name;
}

const HOST_PATTERN = /^[A-Za-z0-9_][A-Za-z0-9_.@:[\]-]{0,254}$/;

export interface ConnectionInput {
  name: string;
  host: string;
  advanced: boolean;
  command: string;
  home: string;
}

export function connectionError(input: ConnectionInput, existing: RemoteMap | null): string | null {
  const name = input.name.trim();
  const host = input.host.trim();
  if (!name || !host) return 'Gib einen Namen und eine SSH-Adresse ein.';
  if (name.length > 64 || /[\u0000-\u001f\u007f]/.test(name)) return 'Verbindungsname: 1 bis 64 sichtbare Zeichen.';
  if (['lokal', 'local'].includes(name.toLowerCase())) return 'Dieser Name ist für den lokalen Rechner reserviert.';
  if (existing && name in existing) return 'Eine Verbindung mit diesem Namen besteht bereits.';
  if (!HOST_PATTERN.test(host)) return 'SSH-Adresse als Alias oder user@host angeben, ohne Optionen und Leerzeichen.';
  if (input.advanced) {
    const command = input.command.trim();
    const home = input.home.trim();
    if (!command || command.startsWith('-')) return 'Gib die Agent-Fleet-Datei auf dem Server an.';
    if (!home.startsWith('/')) return 'Das Datenverzeichnis muss ein absoluter Pfad sein, zum Beispiel /srv/agent-fleet.';
  }
  return null;
}

/** Removes a secret the user typed from any message before it is displayed. */
export function redactSecret(message: string, secret: string): string {
  const value = secret.trim();
  return value.length >= 4 ? message.split(value).join('•••') : message;
}
