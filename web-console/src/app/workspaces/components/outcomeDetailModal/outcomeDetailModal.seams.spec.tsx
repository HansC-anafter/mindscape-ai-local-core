import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OutcomeContent } from './contentRenderers';
import { mergeArtifactDetail } from './detail';
import type { Artifact } from './types';

const seamDir = dirname(fileURLToPath(import.meta.url));
const workspacesComponentsDir = dirname(seamDir);
const webConsoleRoot = join(seamDir, '../../../../..');
const touchedFilePaths = [
  join(workspacesComponentsDir, 'OutcomeDetailModal.tsx'),
  join(seamDir, 'types.ts'),
  join(seamDir, 'detail.ts'),
  join(seamDir, 'markdownComponents.tsx'),
  join(seamDir, 'contentRenderers.tsx'),
  join(seamDir, 'outcomeDetailModal.seams.spec.tsx'),
];
const renderOnlyFiles = [
  join(seamDir, 'detail.ts'),
  join(seamDir, 'markdownComponents.tsx'),
  join(seamDir, 'contentRenderers.tsx'),
];

function readSource(path: string): string {
  return readFileSync(path, 'utf8');
}

function readWebConsoleFile(pathFromRoot: string): string {
  return readFileSync(join(webConsoleRoot, pathFromRoot), 'utf8');
}

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: 'artifact-1',
    workspace_id: 'workspace-1',
    playbook_code: 'demo_playbook',
    artifact_type: 'draft',
    title: 'Draft outcome',
    summary: 'Summary fallback',
    content: { content: 'Draft body' },
    primary_action_type: 'copy',
    metadata: { version: 1 },
    created_at: '2026-06-21T00:00:00Z',
    updated_at: '2026-06-21T00:00:00Z',
    ...overrides,
  };
}

describe('outcome detail modal seams', () => {
  it('merges fetched detail without losing fallback fields', () => {
    const merged = mergeArtifactDetail(artifact({
      summary: 'Base summary',
      storage_ref: '/base/report.md',
      metadata: { version: 1 },
      content: { content: 'Base body' },
    }), {
      description: 'Detail description',
      file_path: '/detail/report.md',
      metadata: undefined,
      content: undefined,
    });

    expect(merged.summary).toBe('Detail description');
    expect(merged.storage_ref).toBe('/detail/report.md');
    expect(merged.primary_action_type).toBe('copy');
    expect(merged.metadata).toEqual({ version: 1 });
    expect(merged.content).toEqual({ content: 'Base body' });
  });

  it('renders draft, checklist, and default payload content', () => {
    const { rerender } = render(
      <OutcomeContent
        activeArtifact={artifact({ content: { content: '**Draft** body' } })}
        detailLoading={false}
        onOpenExternal={vi.fn()}
      />
    );
    expect(screen.getByText('Draft')).toBeInTheDocument();

    rerender(
      <OutcomeContent
        activeArtifact={artifact({
          artifact_type: 'checklist',
          content: { tasks: [{ title: 'Review task', description: 'Confirm seam', priority: 'high' }] },
        })}
        detailLoading={false}
        onOpenExternal={vi.fn()}
      />
    );
    expect(screen.getByText('Task List')).toBeInTheDocument();
    expect(screen.getByText('Review task')).toBeInTheDocument();
    expect(screen.getByText('Confirm seam')).toBeInTheDocument();

    rerender(
      <OutcomeContent
        activeArtifact={artifact({ artifact_type: 'unknown', content: { status: 'ready' } })}
        detailLoading={false}
        onOpenExternal={vi.fn()}
      />
    );
    expect(screen.getByText(/"status": "ready"/)).toBeInTheDocument();
  });

  it('renders loading and Canva action without owning URL fetches', () => {
    const openExternal = vi.fn();
    const { rerender } = render(
      <OutcomeContent
        activeArtifact={artifact({ content: null })}
        detailLoading
        onOpenExternal={openExternal}
      />
    );
    expect(screen.getByText('Loading outcome content...')).toBeInTheDocument();

    rerender(
      <OutcomeContent
        activeArtifact={artifact({
          artifact_type: 'canva',
          content: { canva_url: 'https://canva.test/design' },
        })}
        detailLoading={false}
        onOpenExternal={openExternal}
      />
    );
    expect(screen.getByRole('button', { name: 'Open in Canva' })).toBeInTheDocument();
  });

  it('keeps touched files below the line gate', () => {
    for (const path of touchedFilePaths) {
      const lineCount = readSource(path).split(/\r?\n/).length;
      expect(lineCount, path).toBeLessThanOrEqual(500);
    }
  });

  it('keeps resource owners in the public modal facade', () => {
    const modalSource = readSource(join(workspacesComponentsDir, 'OutcomeDetailModal.tsx'));
    expect(modalSource).toContain('fetch(');
    expect(modalSource).toContain('navigator.clipboard.writeText');
    expect(modalSource).toContain('window.open(data.url');

    for (const path of renderOnlyFiles) {
      const source = readSource(path);
      expect(source, path).not.toMatch(/\bfetch\s*\(/);
      expect(source, path).not.toContain('setInterval');
      expect(source, path).not.toContain('setTimeout');
      expect(source, path).not.toContain('EventSource');
      expect(source, path).not.toContain('WebSocket');
      expect(source, path).not.toMatch(/\bpoll/i);
      expect(source, path).not.toMatch(/\bworker\b/i);
      expect(source, path).not.toMatch(/\bpgbouncer\b/i);
      expect(source, path).not.toMatch(/\bdatabase\b/i);
      expect(source, path).not.toMatch(/\bredis\b/i);
      expect(source, path).not.toContain('navigator.');
      expect(source, path).not.toContain('window.open');
    }
  });

  it('preserves public default import callers', () => {
    const publicModalSource = readSource(join(workspacesComponentsDir, 'OutcomeDetailModal.tsx'));
    expect(publicModalSource).toContain('export default function OutcomeDetailModal');

    expect(readWebConsoleFile('src/app/workspaces/[workspaceId]/components/WorkspaceModals.tsx'))
      .toContain("dynamic(() => import('../../components/OutcomeDetailModal'), { ssr: false })");
  });

  it('keeps touched source files ascii only', () => {
    for (const path of touchedFilePaths) {
      expect(readSource(path), path).not.toMatch(/[^\x00-\x7F]/);
    }
  });
});
