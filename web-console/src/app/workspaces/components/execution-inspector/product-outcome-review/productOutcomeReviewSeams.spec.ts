import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(
  process.cwd(),
  'src/app/workspaces/components/execution-inspector',
);
const reviewRoot = join(root, 'product-outcome-review');

function source(name: string): string {
  return readFileSync(join(reviewRoot, name), 'utf8');
}

describe('product outcome review source seam', () => {
  it('keeps the complete surface unmounted and pack-neutral', () => {
    const governance = readFileSync(join(root, 'GovernanceTab.tsx'), 'utf8');
    const combined = readdirSync(reviewRoot)
      .filter((name) => /\.(ts|tsx)$/.test(name) && !name.endsWith('.spec.ts'))
      .map(source)
      .join('\n');
    expect(governance).not.toContain('product-outcome-review');
    expect(combined).not.toContain('capabilities/ig');
    expect(combined).not.toContain("capability_code ===");
    expect(combined).not.toContain('new EventSource');
    expect(combined).not.toContain('setInterval');
    expect(combined).not.toContain('useExecutionPolling');
  });

  it('renders gates before the projection-only experience summary', () => {
    const composer = source('ProductOutcomeReview.tsx');
    expect(composer.indexOf('<OutcomeGateMatrix')).toBeGreaterThan(-1);
    expect(composer.indexOf('<ExperienceSummary')).toBeGreaterThan(
      composer.indexOf('<OutcomeGateMatrix'),
    );
  });

  it('uses one active summary read and explicit bounded details', () => {
    const hook = source('useProductOutcomeReview.ts');
    const api = source('api.ts');
    expect(hook).toContain('if (!active)');
    expect(hook).toContain('fetchProductIterationSummary');
    expect(hook).toContain('subscribeEventStream');
    expect(api).toContain("limit: '50'");
    expect(api).toContain('SUMMARY_BUDGET_BYTES = 150 * 1024');
    expect(api).toContain('/observations?');
    expect(api).toContain('/evaluations?');
  });

  it('keeps lower replay and upper commands semantically distinct', () => {
    const controls = source('OutcomeTimeTravelControls.tsx');
    expect(controls).toContain('View outcome as-of');
    expect(controls).toContain('Re-evaluate evidence');
    expect(controls).toContain('Fork iteration');
    expect(controls).not.toContain('Replay execution');
    expect(controls).toContain('never reruns lower tasks or effects');
  });
});
