import { formatPercent, quotaLevel, type WindowView } from '../quota';

/**
 * Remaining share of the 5-hour window. The arc encodes the reported balance only;
 * unknown or expired values draw no arc and show a dash, never 0 % or 100 %.
 */
export function QuotaRing({ window, size }: { window: WindowView | null; size: 'large' | 'small' }) {
  const diameter = size === 'large' ? 224 : 148;
  const stroke = size === 'large' ? 17 : 12;
  const radius = (diameter - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const remaining = window?.remaining ?? null;
  const caption = window?.expired ? 'Reset-Zeit erreicht. Bitte aktualisieren.'
    : remaining === null ? 'Kein Wert für das 5-Stunden-Fenster' : 'frei im 5-Stunden-Fenster';
  const share = remaining === null ? 0 : Math.min(100, Math.max(0, remaining)) / 100;
  const label = remaining === null ? caption : `${formatPercent(remaining)} ${caption}`;
  return (
    <figure className={`ring ring-${size} level-${quotaLevel(remaining)}`} role="img" aria-label={label}>
      <svg width={diameter} height={diameter} viewBox={`0 0 ${diameter} ${diameter}`} aria-hidden="true" focusable="false">
        <circle className="ring-track" cx={diameter / 2} cy={diameter / 2} r={radius} strokeWidth={stroke} fill="none" />
        {share > 0 && (
          <circle className="ring-value" cx={diameter / 2} cy={diameter / 2} r={radius} strokeWidth={stroke} fill="none"
            strokeLinecap="round" strokeDasharray={`${circumference * share} ${circumference}`}
            transform={`rotate(-90 ${diameter / 2} ${diameter / 2})`} />
        )}
      </svg>
      <div className="ring-text" aria-hidden="true">
        <span className="ring-number">{formatPercent(remaining)}</span>
        <span className="ring-caption">{caption}</span>
      </div>
    </figure>
  );
}

export function QuotaBar({ window }: { window: WindowView }) {
  const remaining = window.remaining;
  const value = window.expired ? 'Nicht aktuell' : remaining === null ? 'Kein Wert' : `${formatPercent(remaining)} frei`;
  const share = remaining === null ? 0 : Math.min(100, Math.max(0, remaining));
  return (
    <div className="limit">
      <div className="limit-head">
        <span className="limit-title">{window.label}</span>
        <span className="limit-value">{value}</span>
      </div>
      <div className={`bar level-${quotaLevel(remaining)}`} role="meter" aria-label={window.label} aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={remaining ?? undefined} aria-valuetext={value}>
        {share > 0 && <span className="bar-fill" style={{ width: `${share}%` }} />}
      </div>
      <p className="limit-reset" title={window.resetAbsolute || undefined}>{window.resetLabel}</p>
    </div>
  );
}
