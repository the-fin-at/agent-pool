/**
 * Display model for accounts, ported from agent_pool/monitor.py (0.4.1).
 * Missing or expired values stay unknown; they are never shown as 0 % or 100 %.
 */
import type { Account, QuotaWindow } from './types';

export const FIVE_HOURS = 300;
export const WEEK = 10080;
/** Seconds after which an observation counts as not current. */
export const STALE_AFTER = 150;

export type Tone = 'success' | 'warning' | 'muted' | 'danger';

export interface WindowView {
  raw: QuotaWindow;
  /** Short title, e.g. "5 Stunden · Opus" or "Woche". */
  title: string;
  /** Title for a limit row; the weekly window reads "Wochenkontingent". */
  label: string;
  used: number | null;
  remaining: number | null;
  expired: boolean;
  resetLabel: string;
  resetAbsolute: string;
}

export interface AccountView {
  account: Account;
  displayName: string;
  windows: WindowView[];
  primary: WindowView | null;
  extra: WindowView[];
  statusLabel: string;
  tone: Tone;
  planLabel: string;
  roleLabel: string;
  stale: boolean;
  held: boolean;
  updatedLabel: string;
}

export function relativeTime(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  if (s < 60) return 'unter 1 Min.';
  let minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} Min.`;
  let hours = Math.floor(minutes / 60);
  minutes %= 60;
  if (hours < 24) return `${hours} Std.` + (minutes ? ` ${minutes} Min.` : '');
  const days = Math.floor(hours / 24);
  hours %= 24;
  return `${days} ${days === 1 ? 'Tag' : 'Tage'}` + (hours ? ` ${hours} Std.` : '');
}

const clockFormat = new Intl.DateTimeFormat('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const absoluteFormat = new Intl.DateTimeFormat('de-DE', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZoneName: 'short',
});
const percentFormat = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 1 });

export function formatClock(epochSeconds: number): string {
  return clockFormat.format(new Date(epochSeconds * 1000));
}

export function formatAbsolute(epochSeconds: number): string {
  return absoluteFormat.format(new Date(epochSeconds * 1000));
}

/** "72 %" with German decimals; null stays a dash. */
export function formatPercent(value: number | null): string {
  return value === null ? '—' : `${percentFormat.format(value)} %`;
}

/** Python str.title(): first letter of every alphabetic run upper case. */
function titleCase(value: string): string {
  return value.toLowerCase().replace(/(^|[^\p{L}])(\p{L})/gu, (_, before: string, letter: string) => before + letter.toUpperCase());
}

export function windowView(window: QuotaWindow, now: number): WindowView {
  const minutes = window.minutes;
  let title = minutes === FIVE_HOURS ? '5 Stunden' : minutes === WEEK ? 'Woche' : minutes ? `${minutes} Minuten` : 'Weiteres Limit';
  if (window.model) title += ' · ' + titleCase(window.model);
  if (window.bucket && !['codex', 'claude'].includes(window.bucket)) title += ' · ' + window.bucket;
  const { used, reset } = window;
  const expired = reset !== null && reset <= now;
  const valid = used !== null && used >= 0 && used <= 100;
  // Passing a predicted reset is not proof of a replenished balance.
  return {
    raw: window,
    title,
    label: minutes === WEEK ? title.replace('Woche', 'Wochenkontingent') : title,
    used: valid && !expired ? used : null,
    remaining: valid && !expired ? 100 - used : null,
    expired,
    resetLabel: expired ? 'Reset-Zeit erreicht. Bitte aktualisieren.'
      : reset === null ? 'Reset-Zeit unbekannt' : 'Reset in ' + relativeTime(reset - now),
    resetAbsolute: reset !== null ? formatAbsolute(reset) : '',
  };
}

/** All applicable windows must allow work; mirrors agent_pool/quota.availability. */
export function availability(windows: QuotaWindow[], now: number, bucket: string | null): { ready: boolean } {
  let blocked = false;
  for (const w of windows) {
    if (bucket && w.bucket !== bucket) continue;
    if (w.reset !== null && w.reset <= now) continue;
    if (w.used !== null && w.used >= 100) blocked = true;
  }
  return { ready: !blocked };
}

/** The 5-hour window drawn in the ring; a weekly or model window is never relabelled as 5 hours. */
export function quotaSections(provider: string, views: WindowView[]): { primary: WindowView | null; extra: WindowView[] } {
  const candidates = views.filter((v) => v.raw.minutes === FIVE_HOURS);
  const primary = candidates.find((v) => !v.raw.model && (v.raw.bucket === null || v.raw.bucket === provider))
    ?? candidates[0] ?? null;
  return { primary, extra: views.filter((v) => v !== primary) };
}

const PLANS: Record<string, string> = {
  team: 'Business', prolite: 'Pro', pro: 'Pro', plus: 'Plus', enterprise: 'Enterprise', free: 'Free', max: 'Max',
};

/** Drawing colour of a remaining share: brand, warning at 25 % or less, danger at 5 % or less. */
export function quotaLevel(remaining: number | null): 'unknown' | 'normal' | 'low' | 'critical' {
  if (remaining === null) return 'unknown';
  return remaining <= 5 ? 'critical' : remaining <= 25 ? 'low' : 'normal';
}

export function holdLabel(reason: string | null): string {
  if (reason === 'quota') return 'Kontingent ausgeschöpft';
  if (reason === 'quota_reset_unknown') return 'Ausgeschöpft, Reset-Zeit unbekannt';
  return reason ?? '';
}

export function accountView(account: Account, now: number): AccountView {
  const observed = account.observed_at;
  const windows = account.windows.map((w) => windowView(w, now));
  const stale = Boolean(account.error) || Boolean(observed && now - observed > STALE_AFTER) || windows.some((w) => w.expired);
  const state = availability(account.windows, now, account.provider === 'codex' ? 'codex' : null);
  const held = Boolean(account.hold_reason) && (account.hold_until === null || account.hold_until > now);
  const { primary, extra } = quotaSections(account.provider, windows);
  let statusLabel: string;
  let tone: Tone;
  if (!account.connected) {
    [statusLabel, tone] = account.error ? ['Verbindung prüfen', 'warning'] : ['Nicht verbunden', 'muted'];
  } else if (stale) {
    [statusLabel, tone] = ['Daten nicht aktuell', 'warning'];
  } else if (held || !state.ready) {
    [statusLabel, tone] = ['Limit erreicht', 'warning'];
  } else if (!windows.length || windows.every((w) => w.used === null)) {
    [statusLabel, tone] = ['Kontingent unbekannt', 'muted'];
  } else if (primary && primary.remaining !== null && primary.remaining <= 25) {
    [statusLabel, tone] = ['Wenig frei', 'warning'];
  } else {
    [statusLabel, tone] = ['Verbunden', 'success'];
  }
  return {
    account,
    displayName: account.display_name ?? (account.managed ? account.name : 'Standardaccount'),
    windows,
    primary,
    extra,
    statusLabel,
    tone,
    planLabel: account.plan ? PLANS[account.plan] ?? account.plan : 'Tarif unbekannt',
    roleLabel: !account.managed ? 'Nur Anzeige' : account.enabled ? 'Für Aufträge aktiv' : 'Für Aufträge deaktiviert',
    stale,
    held,
    updatedLabel: observed ? 'Stand ' + formatClock(observed) : 'Noch keine Kontingentdaten',
  };
}

export function providerLabel(provider: string): string {
  return provider === 'codex' ? 'Codex' : provider === 'claude' ? 'Claude' : provider;
}

/** Same ordering as 0.4.1: connected first, the monitor-only default before profiles, then name. */
export function sortAccounts(accounts: Account[]): Account[] {
  return [...accounts].sort((a, b) =>
    Number(!a.connected) - Number(!b.connected) || Number(a.managed) - Number(b.managed) || a.name.localeCompare(b.name));
}

export function matchesSearch(account: Account, query: string): boolean {
  const q = query.trim().toLocaleLowerCase('de-DE');
  if (!q) return true;
  return [account.name, account.display_name, account.email, account.provider, account.plan]
    .filter(Boolean).join(' ').toLocaleLowerCase('de-DE').includes(q);
}

/** Earliest moment at which a label changes (stale threshold or reset), for re-rendering. */
export function nextDeadline(accounts: Account[], now: number): number | null {
  const times: number[] = [];
  for (const a of accounts) {
    if (a.observed_at && a.observed_at + STALE_AFTER > now) times.push(a.observed_at + STALE_AFTER);
    for (const w of a.windows) if (w.reset !== null && w.reset > now) times.push(w.reset);
  }
  return times.length ? Math.min(...times) : null;
}
