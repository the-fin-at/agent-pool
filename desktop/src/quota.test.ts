import { describe, expect, it } from 'vitest';
import { parseStatus } from './fleet';
import { accountView, relativeTime, windowView } from './quota';
import { codexAccount } from './test/fake';
import type { QuotaWindow } from './types';

const NOW = 1_800_000_000;
const win = (w: Partial<QuotaWindow>): QuotaWindow => ({ key: null, bucket: 'codex', minutes: 300, used: null, reset: null, model: null, ...w });

describe('quota display model', () => {
  it('keeps missing and expired values unknown instead of 0 % or 100 %', () => {
    expect(windowView(win({ used: null, reset: NOW + 60 }), NOW).remaining).toBeNull();
    const expired = windowView(win({ used: 10, reset: NOW - 1 }), NOW);
    expect(expired.remaining).toBeNull();
    expect(expired.resetLabel).toBe('Reset-Zeit erreicht. Bitte aktualisieren.');
    expect(windowView(win({ used: 140 }), NOW).remaining).toBeNull();
    expect(windowView(win({ used: 28, reset: NOW + 3600 }), NOW).remaining).toBe(72);
  });

  it('never presents a weekly or model window as the 5-hour ring', () => {
    const parsed = parseStatus({ accounts: [{ ...codexAccount('a'), windows: [
      { minutes: 10080, used: 50, reset: NOW + 9000, bucket: 'codex' },
      { minutes: 300, used: 10, reset: NOW + 900, bucket: 'claude', model: 'opus' },
    ] }] });
    const view = accountView(parsed.accounts[0], NOW);
    // The only 5-hour window is model-specific; its title says so instead of posing as the general limit.
    expect(view.primary?.title).toBe('5 Stunden · Opus');
    expect(view.extra.map((w) => w.label)).toEqual(['Wochenkontingent']);
  });

  it('labels low remaining quota and the monitor-only default account', () => {
    const low = parseStatus([codexAccount('a', { windows: [{ minutes: 300, used: 80, reset: NOW + 900, bucket: 'codex' }], observed_at: NOW - 5 })]).accounts[0];
    expect(accountView(low, NOW).statusLabel).toBe('Wenig frei');
    const fallback = parseStatus([codexAccount('@codex-default', { managed: false, enabled: false })]).accounts[0];
    const view = accountView(fallback, NOW);
    expect(view.roleLabel).toBe('Nur Anzeige');
    expect(view.displayName).toBe('Standardaccount');
  });

  it('formats German relative times', () => {
    expect(relativeTime(30)).toBe('unter 1 Min.');
    expect(relativeTime(2 * 3600 + 20 * 60)).toBe('2 Std. 20 Min.');
    expect(relativeTime(6 * 86400 + 14 * 3600)).toBe('6 Tage 14 Std.');
  });

  it('distinguishes the provider-reported workspace member credit block from a time limit', () => {
    const account = parseStatus([codexAccount('work', {
      workspace_name: 'THE-FIN', rate_limit_reached_type: 'workspace_member_credits_depleted',
      observed_at: NOW - 5,
      windows: [{ bucket: 'codex', minutes: 300, used: 100, reset: NOW + 900 }],
    })]).accounts[0];
    expect(accountView(account, NOW).statusLabel).toBe('Mitgliedsguthaben aufgebraucht');
    expect(accountView(account, NOW).primary?.remaining).toBe(0);
  });

  it.each([
    ['workspace_owner_credits_depleted', 'Workspace-Guthaben aufgebraucht'],
    ['workspace_member_credits_depleted', 'Mitgliedsguthaben aufgebraucht'],
    ['workspace_owner_usage_limit_reached', 'Workspace-Limit erreicht'],
    ['workspace_member_usage_limit_reached', 'Mitgliedslimit erreicht'],
    ['rate_limit_reached', 'Limit erreicht'],
  ])('shows the explicit provider block %s even when a reported window still has capacity', (reason, label) => {
    const account = parseStatus([codexAccount('work', { rate_limit_reached_type: reason, observed_at: NOW - 5,
      windows: [{ bucket: 'codex', minutes: 300, used: 28, reset: NOW + 900 }],
    })]).accounts[0];
    expect(accountView(account, NOW).statusLabel).toBe(label);
  });

  it('keeps old and unknown provider metadata compatible and does not call stale credit reports current', () => {
    const current = (extra: Record<string, unknown>) => parseStatus([codexAccount('work', { observed_at: NOW - 5,
      windows: [{ bucket: 'codex', minutes: 300, used: 28, reset: NOW + 900 }], ...extra,
    })]).accounts[0];
    expect(accountView(current({}), NOW).statusLabel).toBe('Verbunden');
    expect(accountView(current({ rate_limit_reached_type: 'future_reason' }), NOW).statusLabel).toBe('Verbunden');
    expect(accountView(current({ rate_limit_reached_type: 'constructor' }), NOW).statusLabel).toBe('Verbunden');
    expect(accountView(current({ rate_limit_reached_type: null }), NOW).statusLabel).toBe('Verbunden');
    expect(accountView(current({ rate_limit_reached_type: 'workspace_member_credits_depleted', observed_at: NOW - 200 }), NOW).statusLabel).toBe('Daten nicht aktuell');
  });
});
