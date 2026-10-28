/**
 * The only bridge to the native core. Components receive a Transport, so tests
 * and the explicit browser preview can replace it without touching Tauri.
 */
import { invoke } from '@tauri-apps/api/core';
import type { InitialConfig, Target } from './types';

export interface Transport {
  /** Runs one Agent Fleet command; resolves with its parsed JSON data. */
  request(target: Target, argv: string[]): Promise<unknown>;
  initialConfig(): Promise<InitialConfig>;
  /** The native side accepts only official provider https URLs. */
  openLoginUrl(url: string): Promise<void>;
  /** True only for the seeded browser preview. */
  readonly demo: boolean;
}

export class FleetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FleetError';
  }
}

const MAX_ERROR = 700;

/** Plain, bounded text for display. Never rendered as HTML. */
export function errorMessage(error: unknown): string {
  let text: string | null = null;
  if (typeof error === 'string') text = error;
  else if (error instanceof Error) text = error.message;
  else if (error && typeof error === 'object') {
    const record = error as Record<string, unknown>;
    for (const key of ['message', 'error']) {
      if (typeof record[key] === 'string') {
        text = record[key] as string;
        break;
      }
    }
  }
  const clean = (text ?? '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, ' ').trim();
  if (!clean) return 'Unbekannter Fehler.';
  return clean.length > MAX_ERROR ? clean.slice(0, MAX_ERROR - 1) + '…' : clean;
}

export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

const NOT_DESKTOP = 'Die Desktop-Schnittstelle ist nicht verfügbar. Agent Fleet bitte als Desktop-App starten.';

function nativeCall<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (!isTauri()) return Promise.reject(new FleetError(NOT_DESKTOP));
  return invoke<T>(command, args).catch((error: unknown) => {
    throw new FleetError(errorMessage(error));
  });
}

export const tauriTransport: Transport = {
  demo: false,
  request(target, argv) {
    return nativeCall<unknown>('fleet_request', { target, argv: [...argv] });
  },
  async initialConfig() {
    const raw = await nativeCall<unknown>('initial_config');
    const data = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
    return {
      home: typeof data.home === 'string' ? data.home : '',
      target: typeof data.target === 'string' && data.target ? data.target : null,
      version: typeof data.version === 'string' ? data.version : '',
    };
  },
  openLoginUrl(url) {
    return nativeCall<void>('open_login_url', { url });
  },
};

/**
 * Seeded preview data only outside Tauri and only with VITE_FLEET_DEMO=1.
 * A failing native call inside the app is always shown as an error.
 */
export async function createTransport(): Promise<Transport> {
  if (import.meta.env.VITE_FLEET_DEMO === '1' && !isTauri()) {
    const { createDemoTransport } = await import('./demo');
    return createDemoTransport();
  }
  return tauriTransport;
}
