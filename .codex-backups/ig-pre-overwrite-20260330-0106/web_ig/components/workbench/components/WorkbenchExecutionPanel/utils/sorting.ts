/**
 * Sorting utilities for run logs
 */
import { parseTimestamp } from './formatters';

export const ACTIVE_RUN_STATUSES = ['running', 'queued', 'pending', 'paused'] as const;

/**
 * Get priority for sorting (running > pending/queued > other)
 */
export function getRunPriority(run: any): number {
    const s = (run?.status || '').toString().toLowerCase();
    if (s === 'running') return 2;
    if (['pending', 'queued', 'paused'].includes(s)) return 1;
    return 0;
}

/**
 * Get timestamp for sorting runs
 */
export function getRunTimestamp(run: any): number {
    const v =
        run?.created_at ||
        run?.started_at ||
        run?.task?.created_at ||
        run?.task?.started_at ||
        null;
    const d = parseTimestamp(v);
    return d ? d.getTime() : 0;
}

/**
 * Sort runs by priority (running first) then by timestamp (newest first)
 */
export function sortRuns<T extends Record<string, any>>(runs: T[]): T[] {
    return [...runs].sort((a, b) => {
        const pa = getRunPriority(a);
        const pb = getRunPriority(b);
        if (pa !== pb) return pb - pa;
        return getRunTimestamp(b) - getRunTimestamp(a);
    });
}

export function isActiveRunStatus(status: any): boolean {
    return ACTIVE_RUN_STATUSES.includes((status || '').toString().toLowerCase() as typeof ACTIVE_RUN_STATUSES[number]);
}

export function getRunExecutionId(run: any): string {
    return (run?.execution_id || run?.id || '').toString();
}

export function getRunPlaybookCode(run: any): string {
    return (run?.playbook_code || '').toString().trim();
}

export function getRunInputs(run: any): Record<string, any> {
    const params = run?.params && typeof run.params === 'object' ? run.params : {};
    const executionInputs =
        run?.execution_context?.inputs && typeof run.execution_context.inputs === 'object'
            ? run.execution_context.inputs
            : {};
    const directInputs = run?.inputs && typeof run.inputs === 'object' ? run.inputs : {};

    return {
        ...params,
        ...executionInputs,
        ...directInputs,
    };
}

export function supportsIGAnalyzerDebug(playbookCode: string | null | undefined): boolean {
    return (playbookCode || '').toString() === 'ig_analyze_following';
}

export function selectRepresentativeActiveRuns<T extends Record<string, any>>(runs: T[], maxCards = 3): T[] {
    const activeRuns = sortRuns(
        (Array.isArray(runs) ? runs : []).filter(
            (run) => isActiveRunStatus(run?.status) && getRunExecutionId(run)
        )
    );

    const byPlaybook = new Map<string, T>();
    for (const run of activeRuns) {
        const playbookCode = getRunPlaybookCode(run) || '__unknown__';
        if (!byPlaybook.has(playbookCode)) {
            byPlaybook.set(playbookCode, run);
        }
    }

    return Array.from(byPlaybook.values()).slice(0, maxCards);
}

export function getRunPrimarySubject(run: any): { label: string; value: string } | null {
    const inputs = getRunInputs(run);

    const candidates: Array<{ label: string; value: any; format?: 'handle' | 'plain' }> = [
        { label: 'Target', value: inputs.target_username ?? run?.execution_context?.target_username ?? run?.target_username, format: 'handle' },
        { label: 'Target', value: inputs.target_handle ?? run?.target_handle, format: 'handle' },
        { label: 'Source', value: inputs.source_handle ?? run?.source_handle, format: 'handle' },
        { label: 'Seed', value: inputs.seed ?? run?.seed, format: 'plain' },
        { label: 'Reference', value: inputs.reference_id ?? run?.reference_id, format: 'plain' },
        { label: 'Post', value: inputs.post_path ?? run?.post_path, format: 'plain' },
    ];

    for (const candidate of candidates) {
        const rawValue = (candidate.value || '').toString().trim();
        if (!rawValue) continue;
        return {
            label: candidate.label,
            value: candidate.format === 'handle' && !rawValue.startsWith('@') ? `@${rawValue}` : rawValue,
        };
    }

    return null;
}

export function getRunDetailItems(run: any): Array<{ label: string; value: string }> {
    const inputs = getRunInputs(run);
    const items: Array<{ label: string; value: string }> = [];
    const seen = new Set<string>();

    const pushItem = (label: string, value: any, format: 'handle' | 'plain' = 'plain') => {
        const raw = (value || '').toString().trim();
        if (!raw) return;
        const normalized = format === 'handle' && !raw.startsWith('@') ? `@${raw}` : raw;
        const dedupeKey = `${label}:${normalized}`;
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        items.push({ label, value: normalized });
    };

    pushItem('Target', inputs.target_username ?? run?.execution_context?.target_username ?? run?.target_username, 'handle');
    pushItem('Target', inputs.target_handle ?? run?.target_handle, 'handle');
    pushItem('Source', inputs.source_handle ?? run?.source_handle, 'handle');
    pushItem('Seed', inputs.seed ?? run?.seed);
    pushItem('Reference', inputs.reference_id ?? run?.reference_id);
    pushItem('Post', inputs.post_path ?? run?.post_path);
    pushItem('Trigger', run?.execution_context?.trigger ?? inputs.trigger);

    if ((run?.execution_context?.runner_skip_reason || '').toString().trim()) {
        const reason = (run.execution_context.runner_skip_reason || '').toString().trim();
        const owner = (run.execution_context.runner_skip_owner || '').toString().trim();
        pushItem('Wait', owner ? `${reason} via ${owner.slice(0, 8)}` : reason);
    }

    return items;
}

/**
 * Filter runs by playbook code
 */
export function filterByPlaybook(runs: any[], playbookCode: string): any[] {
    return runs.filter(
        (r) => (r?.playbook_code || '').toString() === playbookCode && (r?.execution_id || r?.id)
    );
}
