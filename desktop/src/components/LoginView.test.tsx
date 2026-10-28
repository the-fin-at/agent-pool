import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FleetError } from '../api';
import { App } from '../App';
import { codexAccount, deferred, fakeTransport, FAST, status } from '../test/fake';
import type { Target } from '../types';

const DEVICE_URL = 'https://auth.openai.com/codex/device';

function session(argv: string[], state: string, extra: Record<string, unknown> = {}) {
  return { id: argv[argv.indexOf('--key') + 1], profile: argv[2], provider: argv[argv.indexOf('--provider') + 1], state, ...extra };
}

async function openLogin(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Account hinzufügen' }));
  expect(screen.getByRole('heading', { level: 1, name: 'Account verbinden' })).toBeInTheDocument();
}

describe('native sign-in', () => {
  it('runs the Codex device flow and reports success only after the native session succeeded', async () => {
    const user = userEvent.setup();
    let polls = 0;
    let id = '';
    const { transport, calls, opened, commands } = fakeTransport((_t: Target, argv) => {
      if (argv[0] === 'overview') return status([codexAccount('arbeit')]);
      if (argv[1] === 'start') {
        const s = session(argv, 'awaiting_browser', { url: DEVICE_URL, device_code: 'ABCD-12345', message: 'Bestätige die Anmeldung im Browser.', updated_at: 1 });
        id = s.id;
        return s;
      }
      if (argv[1] === 'get') {
        polls += 1;
        return polls < 3
          ? { id, profile: 'privat', provider: 'codex', state: 'awaiting_browser', url: DEVICE_URL, device_code: 'ABCD-12345', message: 'Bestätige die Anmeldung im Browser.', updated_at: 1 + polls }
          : { id, profile: 'privat', provider: 'codex', state: 'succeeded', message: 'Account verbunden.', updated_at: 9 };
      }
      throw new FleetError('unexpected');
    });
    render(<App transport={transport} timing={FAST} />);
    await openLogin(user);

    await user.type(screen.getByRole('textbox', { name: 'Name für diesen Account' }), 'Privat');
    expect(screen.getByText('Profilname: privat')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));

    expect(await screen.findByRole('textbox', { name: 'Dein einmaliger Gerätecode' })).toHaveValue('ABCD-12345');
    const start = calls.find((c) => c.argv[1] === 'start');
    expect(start?.argv.slice(0, 5)).toEqual(['auth', 'start', 'privat', '--provider', 'codex']);
    expect(start?.argv[6]).toMatch(/^[a-f0-9]{32}$/);
    expect(screen.queryByRole('button', { name: 'Zur Übersicht' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Im Browser anmelden' }));
    expect(opened).toEqual([DEVICE_URL]);

    expect(await screen.findByText('Account verbunden.', {}, { timeout: 2000 })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Zur Übersicht' }));
    expect(screen.getByRole('checkbox', { name: 'Alle Profile anzeigen' })).toBeChecked();
    await waitFor(() => expect(commands(null).filter((c) => c === 'overview --refresh').length).toBeGreaterThanOrEqual(2));
    expect(commands(null).filter((c) => c.startsWith('auth cancel'))).toEqual([]);
  });

  it('retries a lost start with the same key, so the server cannot start twice', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    let started: unknown = null;
    const { transport, calls } = fakeTransport((_t, argv) => {
      if (argv[0] === 'overview') return status([]);
      if (argv[1] === 'start') {
        attempt += 1;
        if (attempt === 1) throw new FleetError('SSH timed out');
        started = session(argv, 'awaiting_browser', { url: DEVICE_URL, device_code: 'WXYZ-0000', updated_at: 1 });
        return started;
      }
      if (argv[1] === 'get') return started;
      throw new FleetError('unexpected');
    });
    render(<App transport={transport} timing={FAST} />);
    await openLogin(user);
    await user.type(screen.getByRole('textbox', { name: 'Name für diesen Account' }), 'arbeit');
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('SSH timed out');
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));
    await screen.findByRole('textbox', { name: 'Dein einmaliger Gerätecode' });
    const keys = calls.filter((c) => c.argv[1] === 'start').map((c) => c.argv[6]);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('cancels the native session on Zurück and ignores its late poll result', async () => {
    const user = userEvent.setup();
    const latePoll = deferred();
    let id = '';
    const { transport, commands } = fakeTransport((_t, argv) => {
      if (argv[0] === 'overview') return status([]);
      if (argv[1] === 'start') {
        const s = session(argv, 'awaiting_browser', { url: DEVICE_URL, device_code: 'ABCD-12345', updated_at: 1 });
        id = s.id;
        return s;
      }
      if (argv[1] === 'get') return latePoll.promise;
      if (argv[1] === 'cancel') return { id, cancel_requested: true };
      throw new FleetError('unexpected');
    });
    render(<App transport={transport} timing={FAST} />);
    await openLogin(user);
    await user.type(screen.getByRole('textbox', { name: 'Name für diesen Account' }), 'privat');
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));
    await screen.findByRole('textbox', { name: 'Dein einmaliger Gerätecode' });
    await waitFor(() => expect(commands(null)).toContain('auth get ' + id));

    await user.click(screen.getByRole('button', { name: 'Zurück' }));
    expect(commands(null)).toContain('auth cancel ' + id);
    latePoll.resolve({ id, profile: 'privat', provider: 'codex', state: 'succeeded', message: 'Account verbunden.', updated_at: 5 });
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.getByRole('heading', { level: 1, name: 'Alle Accounts' })).toBeInTheDocument();
    expect(screen.queryByText('Account verbunden.')).not.toBeInTheDocument();
  });

  it('cancels a running sign-in when the computer changes', async () => {
    const user = userEvent.setup();
    const { transport, calls } = fakeTransport((_t, argv) => {
      if (argv[0] === 'overview') return status([]);
      if (argv.join(' ') === 'remote list') return {};
      if (argv[1] === 'start') return session(argv, 'awaiting_browser', { url: DEVICE_URL, updated_at: 1 });
      if (argv[1] === 'get') return new Promise(() => undefined);
      return { cancel_requested: true };
    });
    render(<App transport={transport} timing={FAST} />);
    await openLogin(user);
    await user.type(screen.getByRole('textbox', { name: 'Name für diesen Account' }), 'privat');
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));
    await screen.findByRole('button', { name: 'Anmeldung abbrechen' });

    await user.click(screen.getByRole('button', { name: /Rechner wählen/ }));
    await user.click(screen.getByRole('menuitemradio', { name: /Remote/ }));
    const cancel = calls.find((c) => c.argv[1] === 'cancel');
    expect(cancel?.target).toBeNull();
    expect(await screen.findByRole('heading', { level: 1, name: 'Verbindungen' })).toBeInTheDocument();
  });

  it('accepts the Claude code in a masked field and never displays it in errors', async () => {
    const user = userEvent.setup();
    let id = '';
    const { transport, calls } = fakeTransport((_t, argv) => {
      if (argv[0] === 'overview') return status([]);
      if (argv[1] === 'start') {
        const s = session(argv, 'awaiting_code', { url: 'https://claude.ai/oauth/authorize?x=1', message: 'Öffne die Anmeldeseite.', updated_at: 1 });
        id = s.id;
        return s;
      }
      if (argv[1] === 'input') throw new FleetError('Code abgelehnt: geheim-12345');
      if (argv[1] === 'get') return { id, profile: 'team', provider: 'claude', state: 'awaiting_code', url: 'https://claude.ai/oauth/authorize?x=1', updated_at: 1 };
      throw new FleetError('unexpected');
    });
    render(<App transport={transport} timing={{ ...FAST, loginPollMs: 3_600_000 }} />);
    await openLogin(user);
    await user.click(screen.getByRole('radio', { name: 'Claude' }));
    await user.type(screen.getByRole('textbox', { name: 'Name für diesen Account' }), 'team');
    await user.click(screen.getByRole('button', { name: 'Anmeldung starten' }));

    const field = await screen.findByLabelText('Code aus dem Browser');
    expect(field).toHaveAttribute('type', 'password');
    await user.type(field, 'geheim-12345');
    await user.click(screen.getByRole('button', { name: 'Anmeldung abschließen' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Code abgelehnt: •••');
    expect(document.body.textContent).not.toContain('geheim-12345');
    expect(field).toHaveValue('');
    expect(calls.find((c) => c.argv[1] === 'input')?.argv).toEqual(['auth', 'input', id, '--code=geheim-12345']);
    expect(screen.queryByRole('button', { name: 'Zur Übersicht' })).not.toBeInTheDocument();
  });
});
