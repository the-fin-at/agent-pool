import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage } from '../api';
import type { Fleet } from '../fleet';
import { useAlive } from '../hooks';
import { formatAbsolute, providerLabel } from '../quota';
import type { JobDetail, JobSummary, Target, WorkerState } from '../types';
import { Chip, IconButton, Notice, PageHeader } from './ui';

const STATUS: Record<string, { label: string; tone: 'neutral' | 'warning' | 'danger' | 'success' | 'muted' }> = {
  queued: { label: 'In Warteschlange', tone: 'neutral' },
  waiting: { label: 'Wartet auf Kontingent', tone: 'warning' },
  running: { label: 'Läuft', tone: 'neutral' },
  succeeded: { label: 'Abgeschlossen', tone: 'success' },
  failed: { label: 'Fehlgeschlagen', tone: 'danger' },
  needs_review: { label: 'Prüfung nötig', tone: 'warning' },
  cancelled: { label: 'Abgebrochen', tone: 'muted' },
};

export function statusLabel(status: string): string {
  return STATUS[status]?.label ?? status;
}

function StatusChip({ status }: { status: string }) {
  return <Chip tone={STATUS[status]?.tone ?? 'muted'}>{statusLabel(status)}</Chip>;
}

/** Read-only queue view. Agents submit jobs through the CLI and skills. */
export function JobsView({ fleet, target, worker }: { fleet: Fleet; target: Target; worker: WorkerState | null }) {
  const alive = useAlive();
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const loadSeq = useRef(0);
  const detailSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setLoadError(null);
    try {
      const list = await fleet.jobs(target);
      if (!alive.current || seq !== loadSeq.current) return;
      setJobs([...list].sort((a, b) => (b.created ?? 0) - (a.created ?? 0)));
    } catch (error) {
      if (alive.current && seq === loadSeq.current) setLoadError(errorMessage(error));
    } finally {
      if (alive.current && seq === loadSeq.current) setLoading(false);
    }
  }, [fleet, target, alive]);

  useEffect(() => {
    void load();
  }, [load]);

  const openJob = useCallback(async (jobId: string) => {
    const seq = ++detailSeq.current;
    setSelected(jobId);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const job = await fleet.job(target, jobId);
      if (alive.current && seq === detailSeq.current) setDetail(job);
    } catch (error) {
      if (alive.current && seq === detailSeq.current) setDetailError(errorMessage(error));
    } finally {
      if (alive.current && seq === detailSeq.current) setDetailLoading(false);
    }
  }, [fleet, target, alive]);

  const closeJob = () => {
    detailSeq.current += 1;
    setSelected(null);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(false);
    void load();
  };

  if (selected !== null) {
    return (
      <JobDetailView id={selected} detail={detail} loading={detailLoading} error={detailError}
        onBack={closeJob} onRefresh={() => void openJob(selected)} />
    );
  }

  return (
    <>
      <PageHeader title="Aufträge" subtitle={`Warteschlange auf ${target ?? 'diesem Rechner'}`}
        actions={<IconButton icon="arrow-clockwise" label="Aufträge aktualisieren" busy={loading} disabled={loading} onClick={() => void load()} />} />
      <p className="muted">Aufträge vergeben Agenten über CLI und Skill. Hier sind Status und Ergebnisse einsehbar.</p>
      {worker && !worker.online && (
        <Notice tone="info" title="Kein Worker aktiv">
          <p>Wartende Aufträge bleiben gespeichert, bis auf dem ausführenden Rechner ein Worker läuft. Die App startet keinen Worker.</p>
        </Notice>
      )}
      {loadError && (
        <Notice title="Aufträge konnten nicht geladen werden" action={{ label: 'Erneut versuchen', onClick: () => void load(), disabled: loading }}>
          <p className="plain-text">{loadError}</p>
        </Notice>
      )}
      {jobs === null && loading && <p className="loading" role="status">Aufträge werden geladen …</p>}
      {jobs && jobs.length === 0 && <p className="muted">Noch keine Aufträge.</p>}
      {jobs && jobs.length > 0 && (
        <ul className="job-list" aria-label="Aufträge">
          {jobs.map((job) => (
            <li key={job.id}>
              <button type="button" className="job-row" onClick={() => void openJob(job.id)} aria-label={`Auftrag ${job.id} öffnen`}>
                <span className="job-id">{job.id}</span>
                <StatusChip status={job.status} />
                <span className="job-meta">
                  {providerLabel(job.provider)}{job.chosen_profile ? ' · ' + job.chosen_profile : ''}
                  {job.created ? ' · ' + formatAbsolute(job.created) : ''}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function JobDetailView({ id, detail, loading, error, onBack, onRefresh }: {
  id: string;
  detail: JobDetail | null;
  loading: boolean;
  error: string | null;
  onBack: () => void;
  onRefresh: () => void;
}) {
  const job = detail && detail.id === id ? detail : null;
  const rows: [string, string][] = job ? [
    ['Status', statusLabel(job.status)],
    ['Anbieter', providerLabel(job.provider)],
    ['Profil', job.chosen_profile ?? job.profile ?? 'Wird bei der Ausführung gewählt'],
    ['Modell', job.model ?? 'Standard der CLI'],
    ['Arbeitsverzeichnis', job.cwd ?? '—'],
    ['Dateiänderungen', job.allow_edits ? 'Erlaubt' : 'Nicht erlaubt'],
    ['Versuche', job.attempts === null ? '—' : `${job.attempts}${job.max_attempts ? ' von ' + job.max_attempts : ''}`],
    ['Erstellt', job.created ? formatAbsolute(job.created) : '—'],
    ['Aktualisiert', job.updated ? formatAbsolute(job.updated) : '—'],
  ] : [];
  return (
    <>
      <PageHeader title="Auftrag" subtitle={id} back={{ label: 'Alle Aufträge', onClick: onBack }}
        actions={<IconButton icon="arrow-clockwise" label="Auftrag aktualisieren" busy={loading} disabled={loading} onClick={onRefresh} />} />
      {error && (
        <Notice title="Auftrag konnte nicht geladen werden" action={{ label: 'Erneut versuchen', onClick: onRefresh, disabled: loading }}>
          <p className="plain-text">{error}</p>
        </Notice>
      )}
      {!job && loading && <p className="loading" role="status">Auftrag wird geladen …</p>}
      {job && (
        <div className="details">
          <dl className="facts">
            {rows.map(([label, value]) => (
              <div key={label} className="fact"><dt>{label}</dt><dd>{value}</dd></div>
            ))}
          </dl>
          {job.status === 'needs_review' && (
            <Notice tone="info" title="Prüfung nötig">
              <p>Der Auftrag wurde unterbrochen. Arbeitsverzeichnis prüfen und den Auftrag bei Bedarf über die CLI erneut einreihen.</p>
            </Notice>
          )}
          {job.error && <Notice title="Fehler"><p className="plain-text">{job.error}</p></Notice>}
          <section className="details-section" aria-labelledby="result-heading">
            <h2 id="result-heading">Ergebnis</h2>
            {job.result
              ? <pre className="job-result" tabIndex={0}>{job.result}</pre>
              : <p className="muted">Noch kein Ergebnis. Mit Aktualisieren später erneut prüfen.</p>}
          </section>
        </div>
      )}
    </>
  );
}
