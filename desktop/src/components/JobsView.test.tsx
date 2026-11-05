import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { FleetError } from '../api';
import { App } from '../App';
import { fakeTransport, FAST, status } from '../test/fake';

const ID = '3e700bf6dd774f24a3a4ef3998b4517d';
const RESULT = '<img src=x onerror=alert(1)>\nBericht fertig';

describe('jobs (read-only)', () => {
  it('lists jobs, shows a result as plain text and offers no task composer', async () => {
    const user = userEvent.setup();
    let failDetail = true;
    const { transport, commands } = fakeTransport((_t, argv) => {
      if (argv[0] === 'overview') return status([], { worker: { online: false } });
      if (argv.join(' ') === 'job list') return [{ id: ID, status: 'succeeded', provider: 'codex', chosen_profile: 'arbeit', created: 1_800_000_000 }];
      if (argv.join(' ') === `job get ${ID}`) {
        if (failDetail) throw new FleetError('SSH timed out');
        return { id: ID, status: 'succeeded', provider: 'codex', chosen_profile: 'arbeit', result: RESULT, cwd: '/srv/repo' };
      }
      throw new FleetError('unexpected ' + argv.join(' '));
    });
    render(<App transport={transport} timing={FAST} />);
    await screen.findByText('Noch keine verbundenen Accounts');
    await user.click(screen.getByRole('button', { name: 'Aufträge' }));

    expect(await screen.findByText('Abgeschlossen')).toBeInTheDocument();
    expect(screen.getByText(/Die App startet keinen Worker/)).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Übermitteln/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: `Auftrag ${ID} öffnen` }));
    expect(await screen.findByRole('alert')).toHaveTextContent('SSH timed out');
    failDetail = false;
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));

    const result = await screen.findByText(/Bericht fertig/);
    expect(result.tagName).toBe('PRE');
    expect(result.textContent).toBe(RESULT);
    expect(result.querySelector('img')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Alle Aufträge' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Aufträge' })).toBeInTheDocument();
    expect(commands(null).filter((c) => c.startsWith('job submit'))).toEqual([]);
  });
});
