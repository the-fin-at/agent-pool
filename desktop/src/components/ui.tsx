import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Icon, type IconName } from '../icons';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'soft' | 'quiet';
  icon?: IconName;
};

export function Button({ variant = 'soft', icon, className, children, type = 'button', ...rest }: ButtonProps) {
  return (
    <button type={type} className={`btn btn-${variant}${className ? ' ' + className : ''}`} {...rest}>
      {icon && <Icon name={icon} size={18} />}
      {children !== undefined && <span>{children}</span>}
    </button>
  );
}

export function IconButton({ icon, label, busy, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: IconName; label: string; busy?: boolean;
}) {
  return (
    <button type="button" className={`btn btn-soft btn-icon${busy ? ' is-busy' : ''}`} aria-label={label} title={label}
      aria-busy={busy || undefined} {...rest}>
      <Icon name={icon} size={20} />
    </button>
  );
}

export function PageHeader({ title, subtitle, back, actions }: {
  title: string;
  subtitle?: ReactNode;
  back?: { label: string; onClick: () => void };
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      {back && (
        <Button className="back" icon="arrow-left" onClick={back.onClick}>{back.label}</Button>
      )}
      <div className="title-row">
        <h1>{title}</h1>
        {actions && <div className="actions">{actions}</div>}
      </div>
      {subtitle && <p className="subtitle">{subtitle}</p>}
    </header>
  );
}

/** Errors and model text are rendered as plain React text, never as HTML. */
export function Notice({ tone = 'warning', title, children, action }: {
  tone?: 'warning' | 'success' | 'info';
  title?: string;
  children?: ReactNode;
  action?: { label: string; onClick: () => void; disabled?: boolean };
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'warning' ? 'alert' : 'status'}>
      <Icon name={tone === 'success' ? 'check2' : 'exclamation-circle'} size={20} />
      <div className="notice-body">
        {title && <strong>{title}</strong>}
        {children && <div className="notice-text">{children}</div>}
      </div>
      {action && <Button onClick={action.onClick} disabled={action.disabled}>{action.label}</Button>}
    </div>
  );
}

export function Chip({ tone = 'neutral', children }: { tone?: 'neutral' | 'warning' | 'danger' | 'success' | 'muted'; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: ReactNode; htmlFor: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="field-hint" id={htmlFor + '-hint'}>{hint}</p>}
    </div>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} className="toggle" onClick={() => onChange(!checked)}>
      <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
      <span className="toggle-label">{label}</span>
    </button>
  );
}
