import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Fleet } from '../fleet';
import { parseStatus } from '../fleet';
import { accountView } from '../quota';
import { codexAccount, fakeTransport } from '../test/fake';
import { AccountCard } from './AccountCard';
import { AccountDetails } from './AccountDetails';

const NOW = 1_800_000_000;
const noop = () => {};

describe('Codex workspace limit context', () => {
  it('shows the provider reason on the card and the workspace in Details', () => {
    const account = parseStatus([codexAccount('work', {
      workspace_name: 'THE-FIN', rate_limit_reached_type: 'workspace_member_credits_depleted',
      observed_at: NOW - 5,
      windows: [{ bucket: 'codex', minutes: 300, used: 100, reset: NOW + 900 }],
    })]).accounts[0];
    const { unmount } = render(<AccountCard view={accountView(account, NOW)} compact={false} onDetails={noop} onLogin={noop} />);
    expect(screen.getByText('Mitgliedsguthaben aufgebraucht')).toBeInTheDocument();
    expect(screen.queryByText('Limit erreicht')).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: '0 % frei im 5-Stunden-Fenster' })).toBeInTheDocument();
    unmount();

    const { transport } = fakeTransport(() => null);
    render(<AccountDetails account={account} now={NOW} fleet={new Fleet(transport)} target={null} onBack={noop} onLogin={noop} onEnabledChanged={noop} />);
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('THE-FIN')).toBeInTheDocument();
    expect(screen.getByText('Meldung von Codex')).toBeInTheDocument();
    expect(screen.getByText('Codex meldet aufgebrauchtes Guthaben für dieses Workspace-Mitglied.')).toBeInTheDocument();
  });
});
