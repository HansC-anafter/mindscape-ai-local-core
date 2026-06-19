import { useCallback, useEffect, useState } from 'react';

interface WorkspaceArtifact {
  id: string;
  title?: string;
  description?: string | null;
  content_preview?: string | null;
  content?: unknown;
  metadata?: Record<string, unknown>;
  execution_id?: string | null;
  task_id?: string | null;
  thread_id?: string | null;
  playbook_code?: string | null;
  artifact_type?: string | null;
  created_at?: string | null;
}

interface ArtifactResponse {
  artifacts?: WorkspaceArtifact[];
}

function normalizeApiUrl(apiUrl: string): string {
  return String(apiUrl || '').replace(/\/$/, '');
}

function artifactListUrl(apiUrl: string, workspaceId: string): string {
  const params = new URLSearchParams({
    playbook_code: 'meeting_graph_content_settlement',
    include_content: 'false',
    include_preview: 'true',
    limit: '6',
  });
  return `${normalizeApiUrl(apiUrl)}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/artifacts?${params.toString()}`;
}

function artifactDetailUrl(apiUrl: string, artifactId: string): string {
  const params = new URLSearchParams({
    include_content: 'true',
    include_preview: 'true',
  });
  return `${normalizeApiUrl(apiUrl)}/api/v1/artifacts/${encodeURIComponent(artifactId)}?${params.toString()}`;
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function listText(value: unknown): string {
  if (!Array.isArray(value)) return '';
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const match = text(record.title) || text(record.summary) || text(record.event_type) || text(record.run_id);
    if (match) return match;
  }
  return '';
}

function settlementSummary(artifact: WorkspaceArtifact): string {
  const content = artifact.content && typeof artifact.content === 'object'
    ? artifact.content as Record<string, unknown>
    : null;
  if (content) {
    const direct =
      text(content.summary)
      || text(content.settlement_summary)
      || text(content.trace_summary)
      || listText(content.runs)
      || listText(content.events)
      || listText(content.cards);
    if (direct) return direct;
  }
  return text(artifact.content_preview) || text(artifact.description) || text(artifact.title) || 'No settlement summary available.';
}

function traceLabel(artifact: WorkspaceArtifact): string {
  const metadata = artifact.metadata || {};
  return text(metadata.thread_id)
    || artifact.thread_id
    || text(metadata.run_id)
    || artifact.execution_id
    || artifact.task_id
    || 'trace pending';
}

export function HostRuntimeSettlementCards({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const [artifacts, setArtifacts] = useState<WorkspaceArtifact[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<WorkspaceArtifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(artifactListUrl(apiUrl, workspaceId), { cache: 'no-store' });
      if (!response.ok) throw new Error(`meeting_graph_content_settlement_failed:${response.status}`);
      const payload = await response.json() as ArtifactResponse;
      setArtifacts(Array.isArray(payload.artifacts) ? payload.artifacts : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'meeting_graph_content_settlement_failed');
    } finally {
      setLoading(false);
    }
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadDetail = useCallback(async (artifact: WorkspaceArtifact) => {
    setSelectedArtifact(artifact);
    try {
      const response = await fetch(artifactDetailUrl(apiUrl, artifact.id), { cache: 'no-store' });
      if (response.ok) setSelectedArtifact(await response.json() as WorkspaceArtifact);
    } catch {
      setSelectedArtifact(artifact);
    }
  }, [apiUrl]);

  return (
    <section className="space-y-2 text-xs" data-testid="host-runtime-settlement-cards">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Meeting settlement
          </div>
          <div className="text-slate-600 dark:text-slate-300">
            meeting_graph_content_settlement
          </div>
        </div>
        <button
          type="button"
          className="rounded border border-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-300"
          onClick={() => void refresh()}
        >
          {loading ? 'Loading' : 'Refresh'}
        </button>
      </div>
      {error ? (
        <div className="rounded border border-red-200 bg-red-50 p-2 text-red-700 dark:border-red-900/70 dark:bg-red-950/30 dark:text-red-200">
          {error}
        </div>
      ) : null}
      {artifacts.length ? (
        artifacts.map((artifact) => (
          <article key={artifact.id} className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950" data-testid="host-runtime-settlement-card">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate font-semibold text-slate-800 dark:text-slate-100">
                  {artifact.title || 'RUNS / TRACE settlement'}
                </div>
                <div className="truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">
                  {artifact.id}
                </div>
              </div>
              <span className="shrink-0 rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200">
                {traceLabel(artifact)}
              </span>
            </div>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-5 text-slate-700 dark:text-slate-200">
              {settlementSummary(artifact)}
            </p>
            <button type="button" className="mt-2 text-[11px] font-semibold text-blue-700 dark:text-blue-300" onClick={() => void loadDetail(artifact)}>
              Detail
            </button>
          </article>
        ))
      ) : (
        <div className="rounded border border-dashed border-slate-200 p-2 text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No meeting graph settlement artifacts found for this workspace.
        </div>
      )}
      {selectedArtifact ? (
        <div className="rounded border border-blue-200 bg-blue-50 p-2 dark:border-blue-900/70 dark:bg-blue-950/30" data-testid="host-runtime-settlement-detail">
          <div className="flex items-center justify-between gap-2">
            <div className="font-semibold uppercase tracking-[0.12em] text-blue-700 dark:text-blue-200">
              Settlement detail
            </div>
            <button type="button" className="font-semibold text-blue-700 dark:text-blue-200" onClick={() => setSelectedArtifact(null)}>
              Close
            </button>
          </div>
          <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-blue-950 dark:text-blue-100">
            {JSON.stringify(selectedArtifact, null, 2)}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
