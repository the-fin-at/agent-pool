import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FleetError } from '../api';
import { App } from '../App';
import { codexAccount, deferred, fakeTransport, FAST, status } from '../test/fake';
import type { Target } from '../types';

type Remotes = Record<string, { host: string; command: string; home: string }>;

function server(initial: Remotes, remoteStatus: (name: string) => unknown) {
  const remotes: Remotes = { ...initial };
  return fakeTransport((target: Target, argv) => {
    if (target === null && argv[0] === 'overview') return status([]);
    if (target === null && argv[0] === 'remote') {
      const [, op, name] = argv;
      if (op === 'discover') return { host: name, command: '/home/u/.local/bin/agent-fleet', home: '/home/u/.agent-fleet', features: ['native-login-sessions'] };
      if (op === 'add') remotes[name] = { host: argv[4], command: argv[6], home: argv[8] };
      if (op === 'remove') delete remotes[name];
      return { ...remotes };
    }
    if (target !== null && argv[0] === 'status') return remoteStatus(target);
    throw new FleetError('unexpected ' + argv.join(' '));
  });
}

async function openRemote(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: /Rechner wählen/ }));
  await user.click(screen.getByRole('menuitemradio', { name: /Remote/ }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Verbindungen' })).toBeInTheDocument();
}

describe('remote connections', () => {
  it('discovers, verifies and opens a new server without mixing in local accounts', async () => {
    const user = userEvent.setup();
    const { transport, commands } = server({}, () => status([codexAccount('server-codex')]));
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);
    expect(await screen.findByRole('heading', { name: 'Deine Accounts. Auf jedem Rechner.' })).toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: 'Verbindung hinzufügen' })[0]);
    await user.click(screen.getByRole('button', { name: 'Verbinden' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Gib einen Namen und eine SSH-Adresse ein.');

    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'Linux Server');
    await user.type(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' }), 'pool-server');
    await user.click(screen.getByRole('button', { name: 'Verbinden' }));

    expect(await screen.findByRole('heading', { name: 'server-codex' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verbindungen' })).toBeInTheDocument();
    expect(commands(null)).toEqual(expect.arrayContaining([
      'remote discover pool-server',
      'remote add Linux Server --host pool-server --command /home/u/.local/bin/agent-fleet --server-home /home/u/.agent-fleet',
    ]));
    expect(commands('Linux Server')).toContain('status');
  });

  it('removes the saved entry again when the server lacks native sign-in', async () => {
    const user = userEvent.setup();
    const { transport, commands } = server({}, () => status([], { features: ['cached-status'] }));
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);
    await user.click(screen.getAllByRole('button', { name: 'Verbindung hinzufügen' })[0]);
    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'alt');
    await user.click(screen.getByRole('checkbox', { name: 'Erweiterte Einstellungen' }));
    await user.type(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' }), 'old-host');
    await user.type(screen.getByRole('textbox', { name: 'Agent-Fleet-Datei auf dem Server' }), '/usr/bin/agent-fleet');
    await user.type(screen.getByRole('textbox', { name: 'Datenverzeichnis auf dem Server' }), '/srv/fleet');
    await user.click(screen.getByRole('button', { name: 'Verbinden' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Bitte Agent Fleet auf dem Server aktualisieren');
    expect(commands(null)).toContain('remote remove alt');
    expect(commands(null).some((c) => c.startsWith('remote discover'))).toBe(false);
    expect(screen.getByRole('heading', { level: 1, name: 'Rechner verbinden' })).toBeInTheDocument();
  });

  it('keeps a newer connection form when an abandoned save finishes late', async () => {
    const user = userEvent.setup();
    const slowCheck = deferred();
    const { transport, commands } = server({}, (name) => (name === 'A-Server' ? slowCheck.promise : status([])));
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);

    await user.click(screen.getAllByRole('button', { name: 'Verbindung hinzufügen' })[0]);
    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'A-Server');
    await user.type(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' }), 'host-a');
    await user.click(screen.getByRole('button', { name: 'Verbinden' }));
    await waitFor(() => expect(commands('A-Server')).toContain('status'));

    // Leave form A while its check is pending and start form B.
    await user.click(screen.getByRole('button', { name: 'Zurück' }));
    await user.click(screen.getAllByRole('button', { name: 'Verbindung hinzufügen' })[0]);
    const nameB = screen.getByRole('textbox', { name: 'Name' });
    expect(nameB).toHaveValue('');
    await user.type(nameB, 'B-Server');
    await user.type(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' }), 'host-b');

    const listsBefore = commands(null).filter((c) => c === 'remote list').length;
    slowCheck.resolve(status([codexAccount('a-codex')]));

    // A was really saved: the registry is reread and lists it.
    expect(await screen.findByRole('button', { name: 'A-Server' })).toBeInTheDocument();
    expect(commands(null).filter((c) => c === 'remote list').length).toBeGreaterThan(listsBefore);
    // No stale switch to A: form B and its draft stay.
    expect(screen.getByRole('heading', { level: 1, name: 'Rechner verbinden' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('B-Server');
    expect(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' })).toHaveValue('host-b');
    expect(screen.getByText('Verbundene Rechner')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'a-codex' })).not.toBeInTheDocument();
    expect(commands(null).some((c) => c.startsWith('remote remove'))).toBe(false);
  });

  it('probes every server even when the connection list answers late', async () => {
    const user = userEvent.setup();
    const list = deferred();
    const { transport, commands } = fakeTransport((target, argv) => {
      if (target === null && argv[0] === 'overview') return status([]);
      if (argv.join(' ') === 'remote list') return list.promise;
      if (target !== null && argv[0] === 'status') return status([codexAccount('a')]);
      throw new FleetError('unexpected ' + argv.join(' '));
    });
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);
    await new Promise((r) => setTimeout(r, 20));
    list.resolve({ eins: { host: 'h1', command: 'agent-fleet', home: '/srv/a' }, zwei: { host: 'h2', command: 'agent-fleet', home: '/srv/b' } });

    const connections = await screen.findByRole('list', { name: 'Verbindungen' });
    await waitFor(() => expect(within(connections).getAllByText('1 Account verbunden · Worker aktiv')).toHaveLength(2));
    expect(within(connections).queryByText('Wird geprüft …')).not.toBeInTheDocument();
    expect(commands(null).filter((c) => c === 'remote list')).toHaveLength(1);
    expect(commands('eins')).toEqual(['status']);
    expect(commands('zwei')).toEqual(['status']);
  });

  it('does not let a late rollback delete a connection that was replaced meanwhile', async () => {
    const user = userEvent.setup();
    const { transport, commands } = fakeTransport((target, argv) => {
      if (target === null && argv[0] === 'overview') return status([]);
      if (argv.join(' ') === 'remote list') {
        // Another window replaced "neu" with a different host after this form saved it.
        return commands(null).some((c) => c.startsWith('remote add')) ? { neu: { host: 'anderer-host', command: 'agent-fleet', home: '/srv/x' } } : {};
      }
      if (argv[1] === 'add') return { neu: { host: argv[4], command: argv[6], home: argv[8] } };
      if (target === 'neu' && argv[0] === 'status') throw new FleetError('SSH timed out');
      throw new FleetError('unexpected ' + argv.join(' '));
    });
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);
    await user.click(screen.getAllByRole('button', { name: 'Verbindung hinzufügen' })[0]);
    await user.type(screen.getByRole('textbox', { name: 'Name' }), 'neu');
    await user.click(screen.getByRole('checkbox', { name: 'Erweiterte Einstellungen' }));
    await user.type(screen.getByRole('textbox', { name: 'SSH-Adresse oder Alias' }), 'erster-host');
    await user.type(screen.getByRole('textbox', { name: 'Agent-Fleet-Datei auf dem Server' }), 'agent-fleet');
    await user.type(screen.getByRole('textbox', { name: 'Datenverzeichnis auf dem Server' }), '/srv/x');
    await user.click(screen.getByRole('button', { name: 'Verbinden' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('SSH timed out');
    expect(commands(null).some((c) => c.startsWith('remote remove'))).toBe(false);
  });

  it('shows reachability per server and removes a connection only after confirmation', async () => {
    const user = userEvent.setup();
    const { transport, commands } = server({
      eins: { host: 'h1', command: 'agent-fleet', home: '/srv/a' },
      zwei: { host: 'h2', command: 'agent-fleet', home: '/srv/b' },
    }, (name) => {
      if (name === 'zwei') throw new FleetError('SSH/RPC exited 255');
      return status([codexAccount('a'), codexAccount('b')]);
    });
    render(<App transport={transport} timing={FAST} />);
    await openRemote(user);
    const list = await screen.findByRole('list', { name: 'Verbindungen' });
    await within(list).findByText('2 Accounts verbunden · Worker aktiv');
    await within(list).findByText('Nicht erreichbar');
    expect(within(list).getByText('SSH/RPC exited 255')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'zwei entfernen' }));
    expect(commands(null)).not.toContain('remote remove zwei');
    await user.click(screen.getByRole('button', { name: 'Entfernen bestätigen' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'zwei' })).not.toBeInTheDocument());
    expect(commands(null)).toContain('remote remove zwei');
    expect(screen.getByRole('heading', { name: 'eins' })).toBeInTheDocument();
  });
});
