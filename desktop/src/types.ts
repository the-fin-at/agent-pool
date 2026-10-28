/** Shapes returned by the native Agent Fleet core. Timestamps are Unix seconds. */

export type Provider = 'codex' | 'claude';
export const PROVIDERS: readonly Provider[] = ['codex', 'claude'];

/** null is this computer; a string is the name of a configured SSH connection. */
export type Target = string | null;

export interface InitialConfig {
  home: string;
  target: Target;
  version: string;
}

export interface QuotaWindow {
  key: string | null;
  bucket: string | null;
  minutes: number | null;
  /** Used percentage 0..100 as reported; never a remaining value. */
  used: number | null;
  reset: number | null;
  model: string | null;
}

export type HoldReason = 'quota' | 'quota_reset_unknown' | string;

export interface Account {
  name: string;
  provider: Provider;
  /** false for the native default Codex login shown for monitoring only. */
  managed: boolean;
  enabled: boolean;
  connected: boolean;
  email: string | null;
  plan: string | null;
  display_name: string | null;
  windows: QuotaWindow[];
  observed_at: number | null;
  checked_at: number | null;
  error: string | null;
  hold_reason: HoldReason | null;
  hold_until: number | null;
}

export interface WorkerState {
  online: boolean;
  age_seconds: number | null;
  started_at: number | null;
}

export interface StatusData {
  accounts: Account[];
  worker: WorkerState | null;
  pending_jobs: number | null;
  features: string[];
  version: string | null;
}

export interface RemoteConfig {
  host: string;
  command: string;
  home: string;
}

export type RemoteMap = Record<string, RemoteConfig>;

export interface DoctorCheck {
  provider: string;
  ok: boolean;
  version: string | null;
  error: string | null;
}

export interface RemoteTestResult {
  checks: DoctorCheck[];
}

export type LoginStateName =
  | 'starting'
  | 'awaiting_browser'
  | 'awaiting_code'
  | 'verifying'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'expired';

export const ACTIVE_LOGIN_STATES: ReadonlySet<string> = new Set(['starting', 'awaiting_browser', 'awaiting_code', 'verifying']);

export interface LoginSession {
  id: string;
  profile: string;
  provider: Provider;
  state: LoginStateName;
  url: string | null;
  device_code: string | null;
  message: string | null;
  updated_at: number | null;
  expires_at: number | null;
}

export type JobStatus = 'queued' | 'waiting' | 'running' | 'succeeded' | 'failed' | 'needs_review' | 'cancelled';

export interface JobSummary {
  id: string;
  status: JobStatus | string;
  provider: string;
  profile: string | null;
  chosen_profile: string | null;
  model: string | null;
  cwd: string | null;
  allow_edits: boolean;
  attempts: number | null;
  max_attempts: number | null;
  idempotency_key: string | null;
  created: number | null;
  updated: number | null;
  error: string | null;
}

export interface JobDetail extends JobSummary {
  result: string | null;
}
