import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FleetError, type Transport } from './api';
import { App } from './App';
import { claudeAccount, codexAccount, deferred, fakeTransport, FAST, status } from './test/fake';

const cardNames = () => within(screen.getByRole('list', { name: 'Accounts' })).getAllByRole('heading', { level: 3 }).map((h) => h.textContent);

describe('account overview', () => {
  it('uses the external Claude CLI login automatically while keeping additional account sign-in separate', async () => {
    const user = userEvent.setup();
    const { transport, commands } = fakeTransport(() => status([
      claudeAccount('claude-default', { auth_mode: 'native_default', enabled: true, display_name: 'Claude CLI' }),
      claudeAccount('alias', { alias_of: 'claude-default', enabled: true }),
      claudeAccount('zusatz', { connected: false, windows: [] }),
    ]));
    render(<App transport={transport} timing={FAST} />);
    expect(await screen.findByText('1 Account verbunden')).toBeInTheDocument();
    expect(cardNames()).toEqual(['Claude CLI']);
    await user.click(await screen.findByRole('button', { name: 'Details zu Claude CLI' }));
    expect(screen.getByText(/Anmeldung wird von deiner normalen Claude-CLI verwaltet/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Erneut anmelden' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Für Aufträge deaktivieren' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Zurück' }));
    await user.click(screen.getByRole('checkbox', { name: 'Alle Profile anzeigen' }));
    expect(screen.getByRole('button', { name: 'zusatz anmelden' })).toBeInTheDocument();
    expect(commands(null).some(command => command.startsWith('auth start'))).toBe(false);
  });

  it('shows one card per verified account and reveals its individual profiles on request', async () => {
    const user = userEvent.setup();
    const { transport } = fakeTransport(() => status([
      codexAccount('@codex-default', { managed: false, enabled: false }),
      codexAccount('codex-2'),
      codexAccount('codex-3'),
      claudeAccount('claude-default', { auth_mode: 'native_default', enabled: true, display_name: 'Claude CLI', email: 'same@example.com' }),
      claudeAccount('voxbot', { alias_of: 'claude-default', enabled: true, email: 'same@example.com' }),
    ]));
    render(<App transport={transport} timing={FAST} />);

    expect(await screen.findByText('4 Accounts verbunden')).toBeInTheDocument();
    expect(cardNames()).toEqual(['Standardaccount', 'Claude CLI', 'codex-2', 'codex-3']);

    await user.click(screen.getByRole('checkbox', { name: 'Alle Profile anzeigen' }));
    expect(cardNames()).toEqual(['Standardaccount', 'Claude CLI', 'codex-2', 'codex-3', 'voxbot']);
    expect(screen.getByText('4 Accounts verbunden')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Details zu voxbot' }));
    expect(screen.getByRole('heading', { level: 1, name: 'voxbot' })).toBeInTheDocument();
  });

  it('searches all verified profile names while showing the canonical account card', async () => {
    const user = userEvent.setup();
    const { transport } = fakeTransport(() => status([
      claudeAccount('a-managed-login', { alias_of: 'claude-default', enabled: true, email: 'same@example.com' }),
      claudeAccount('claude-default', { auth_mode: 'native_default', enabled: true, display_name: 'Claude CLI', email: 'same@example.com' }),
    ]));
    render(<App transport={transport} timing={FAST} />);
    await screen.findByText('1 Account verbunden');

    await user.type(screen.getByRole('searchbox', { name: 'Accounts durchsuchen' }), 'a-managed-login');
    expect(cardNames()).toEqual(['Claude CLI']);
    await user.click(screen.getByRole('checkbox', { name: 'Alle Profile anzeigen' }));
    expect(cardNames()).toEqual(['a-managed-login']);
  });

  it('keeps profiles with equal emails separate without a verified alias relationship', async () => {
    const { transport } = fakeTransport(() => status([
      claudeAccount('first', { email: 'same@example.com' }),
      claudeAccount('second', { email: 'same@example.com' }),
    ]));
    render(<App transport={transport} timing={FAST} />);
    expect(await screen.findByText('2 Accounts verbunden')).toBeInTheDocument();
    expect(cardNames()).toEqual(['first', 'second']);
  });

  it.each(['missing', 'disconnected', 'disabled'] as const)(
    'keeps a connected account visible when the canonical profile is %s',
    async (canonicalState) => {
      const alias = claudeAccount('voxbot', { alias_of: 'claude-default', enabled: true, email: 'same@example.com' });
      const canonical = claudeAccount('claude-default', {
        auth_mode: 'native_default', display_name: 'Claude CLI', email: 'same@example.com',
        connected: canonicalState !== 'disconnected', enabled: false,
      });
      const { transport } = fakeTransport(() => status(canonicalState === 'missing' ? [alias] : [alias, canonical]));
      render(<App transport={transport} timing={FAST} />);
      expect(await screen.findByText('1 Account verbunden')).toBeInTheDocument();
      expect(cardNames()).toEqual([canonicalState === 'disabled' ? 'Claude CLI' : 'voxbot']);
    },
  );
  it('shows local accounts with 5-hour ring, weekly bar and the default Codex login', async () => {
    const local = status([
      codexAccount('@codex-default', { managed: false, enabled: false, email: 'privat@example.com' }),
      codexAccount('arbeit'),
      claudeAccount('team'),
    ]);
    const { transport, commands } = fakeTransport(() => local);
    render(<App transport={transport} timing={FAST} />);

    await screen.findByRole('heading', { name: 'arbeit' });
    expect(screen.getByRole('heading', { level: 1, name: 'Alle Accounts' })).toBeInTheDocument();
    expect(screen.getByText('3 Accounts verbunden')).toBeInTheDocument();
    expect(screen.getAllByRole('img', { name: '72 % frei im 5-Stunden-Fenster' })).toHaveLength(2);
    expect(screen.getAllByRole('meter', { name: 'Wochenkontingent' })[0]).toHaveAttribute('aria-valuetext', '41 % frei');
    expect(screen.getByText('Codex · Nur Anzeige')).toBeInTheDocument();
    // Claude reported only a weekly window: no invented 5-hour value.
    expect(screen.getByRole('img', { name: 'Kein Wert für das 5-Stunden-Fenster' })).toBeInTheDocument();
    expect(screen.getByText('Kein 5-Stunden-Limit gemeldet')).toBeInTheDocument();
    await waitFor(() => expect(commands(null)).toEqual(['overview', 'overview --refresh']));
  });

  it('filters by provider, searches and reveals unconnected profiles', async () => {
    const user = userEvent.setup();
    const { transport } = fakeTransport(() => status([
      codexAccount('arbeit'), claudeAccount('team'), claudeAccount('reserve', { connected: false, windows: [], observed_at: null }),
    ]));
    render(<App transport={transport} timing={FAST} />);
    await screen.findByRole('heading', { name: 'arbeit' });

    await user.click(screen.getByRole('button', { name: 'Claude' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Claude' })).toBeInTheDocument();
    expect(cardNames()).toEqual(['team']);

    await user.click(screen.getByRole('checkbox', { name: 'Alle Profile anzeigen' }));
    expect(cardNames()).toEqual(['team', 'reserve']);
    expect(screen.getByRole('button', { name: 'reserve anmelden' })).toBeInTheDocument();

    await user.type(screen.getByRole('searchbox', { name: 'Accounts durchsuchen' }), 'nichts');
    expect(screen.getByRole('heading', { name: 'Keine passenden Accounts' })).toBeInTheDocument();
  });

  it('keeps a failed query visible with a working retry', async () => {
    const user = userEvent.setup();
    let fail = true;
    const { transport } = fakeTransport((_t, argv) => {
      if (fail) throw new FleetError('Datenbank gesperrt');
      return argv[0] === 'overview' ? status([codexAccount('arbeit')]) : null;
    });
    render(<App transport={transport} timing={FAST} />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Datenbank gesperrt');
    fail = false;
    const retry = within(alert).getByRole('button', { name: 'Erneut versuchen' });
    await waitFor(() => expect(retry).toBeEnabled());
    await user.click(retry);
    expect(await screen.findByRole('heading', { name: 'arbeit' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('drops a late local response after switching to a remote server', async () => {
    const user = userEvent.setup();
    const slowLocal = deferred();
    const { transport, commands } = fakeTransport((target, argv) => {
      if (target === null && argv[0] === 'overview') return slowLocal.promise;
      if (argv.join(' ') === 'remote list') return { server: { host: 'srv', command: '/usr/bin/agent-fleet', home: '/srv/fleet' } };
      if (target === 'server' && argv[0] === 'status') return status([codexAccount('server-codex')]);
      throw new FleetError('unexpected ' + argv.join(' '));
    });
    render(<App transport={transport} timing={FAST} />);
    await waitFor(() => expect(commands(null)).toContain('overview'));

    await user.click(screen.getByRole('button', { name: /Rechner wählen/ }));
    await user.click(screen.getByRole('menuitemradio', { name: /Remote/ }));
    await user.click(await screen.findByRole('button', { name: 'server öffnen' }));
    await screen.findByRole('heading', { name: 'server-codex' });

    slowLocal.resolve(status([codexAccount('nur-lokal')]));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole('heading', { name: 'nur-lokal' })).not.toBeInTheDocument();
    expect(commands('server')).toEqual(expect.arrayContaining(['status']));
    expect(commands('server').some((c) => c.includes('--refresh'))).toBe(false);
  });

  it('disables a profile for jobs from its details', async () => {
    const user = userEvent.setup();
    let enabled = true;
    const { transport, commands } = fakeTransport((_t, argv) => {
      if (argv[0] === 'profile') {
        enabled = argv[1] === 'enable';
        return [];
      }
      return status([codexAccount('arbeit', { enabled })]);
    });
    render(<App transport={transport} timing={FAST} />);
    await user.click(await screen.findByRole('button', { name: 'Details zu arbeit' }));
    expect(screen.getByRole('heading', { level: 1, name: 'arbeit' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Für Aufträge deaktivieren' }));
    expect(await screen.findByRole('button', { name: 'Für Aufträge aktivieren' })).toBeInTheDocument();
    expect(commands(null)).toContain('profile disable arbeit');
    await user.click(screen.getByRole('button', { name: 'Zurück' }));
    expect(screen.getByText('Codex · Für Aufträge deaktiviert')).toBeInTheDocument();
  });

  it('shows a startup error instead of demo data when the native bridge fails', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const transport: Transport = {
      demo: false,
      request: async () => status([]),
      initialConfig: async () => {
        attempts += 1;
        if (attempts === 1) throw new FleetError('Bridge nicht verfügbar');
        return { home: '/h', target: null, version: '0.5.0' };
      },
      openLoginUrl: async () => undefined,
    };
    render(<App transport={transport} timing={FAST} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Bridge nicht verfügbar');
    expect(screen.queryByText('Vorschaudaten')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByRole('heading', { name: 'Noch keine verbundenen Accounts' })).toBeInTheDocument();
  });
});
