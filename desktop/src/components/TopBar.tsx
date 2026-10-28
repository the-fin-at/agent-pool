import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Compass, Icon, type IconName } from '../icons';

export type Scope = 'local' | 'remote';

const OPTIONS: { value: Scope; label: string; caption: string; icon: IconName }[] = [
  { value: 'local', label: 'Lokal', caption: 'Accounts auf diesem Rechner', icon: 'laptop' },
  { value: 'remote', label: 'Remote', caption: 'Verbindungen und entfernte Accounts', icon: 'globe2' },
];

export function TopBar({ scope, remote, onSelect }: { scope: Scope; remote: string | null; onSelect: (scope: Scope) => void }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const outside = (event: MouseEvent) => {
      const node = event.target as Node;
      if (!menu.current?.contains(node) && !button.current?.contains(node)) setOpen(false);
    };
    document.addEventListener('mousedown', outside);
    return () => document.removeEventListener('mousedown', outside);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (event.key === 'Escape' || event.key === 'Tab') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      items[(index + step + items.length) % items.length]?.focus();
    }
  };

  const hint = scope === 'local' ? 'Auf diesem Rechner' : remote ?? 'Verbundene Rechner';

  return (
    <header className="topbar">
      <div className="scope">
        <button ref={button} type="button" className="scope-button" aria-haspopup="menu" aria-expanded={open}
          aria-label={`Rechner wählen, aktuell ${scope === 'local' ? 'Lokal' : 'Remote'}`}
          onClick={() => setOpen((value) => !value)}>
          <span>{scope === 'local' ? 'Lokal' : 'Remote'}</span>
          <Icon name="chevron-down" size={18} />
        </button>
        <span className="scope-hint">{hint}</span>
        {open && (
          <div ref={menu} className="scope-menu" role="menu" aria-label="Rechner" onKeyDown={onMenuKey}>
            {OPTIONS.map((option) => (
              <button key={option.value} type="button" role="menuitemradio" aria-checked={scope === option.value}
                className="scope-option" onClick={() => {
                  close();
                  onSelect(option.value);
                }}>
                <Icon name={option.icon} size={20} />
                <span className="scope-option-text">
                  <span className="scope-option-label">{option.label}</span>
                  <span className="scope-option-caption">{option.caption}</span>
                </span>
                {scope === option.value && <Icon name="check2" size={18} className="scope-check" />}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="brand">
        <Compass size={40} />
        <span>Agent Fleet</span>
      </div>
    </header>
  );
}
