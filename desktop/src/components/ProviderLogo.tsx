import codexLogo from '../assets/providers/codex.png';
import claudeLogo from '../assets/providers/claude.svg';
import type { Provider } from '../types';

const LOGOS: Record<Provider, string> = { codex: codexLogo, claude: claudeLogo };

/** Decorative provider mark; the adjacent text supplies the accessible name. */
export function ProviderLogo({ provider, size = 24 }: { provider: Provider; size?: number }) {
  return <img className="provider-logo" src={LOGOS[provider]} width={size} height={size} alt="" aria-hidden="true" />;
}
