import { useId } from 'react';
import codexLogo from '../assets/providers/codex.png';
import claudeLogo from '../assets/providers/claude.svg';
import type { Provider } from '../types';

const LOGOS: Record<Provider, string> = { codex: codexLogo, claude: claudeLogo };

/** Decorative provider mark; the adjacent text supplies the accessible name. */
export function ProviderLogo({ provider, size = 24 }: { provider: Provider; size?: number }) {
  const id = useId();
  const maskId = `${id}-mask`;
  const filterId = `${id}-ink`;
  return (
    <svg className="provider-logo" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <defs>
        {/* White background and terminal cutouts become transparent; original geometry stays in the bundled icon. */}
        {provider === 'codex' && (
          <filter id={filterId} colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -1 -1 -1 3 0" />
          </filter>
        )}
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24" style={{ maskType: 'alpha' }}>
          <image href={LOGOS[provider]} width="24" height="24" filter={provider === 'codex' ? `url(#${filterId})` : undefined} />
        </mask>
      </defs>
      <rect width="24" height="24" fill="currentColor" mask={`url(#${maskId})`} />
    </svg>
  );
}
