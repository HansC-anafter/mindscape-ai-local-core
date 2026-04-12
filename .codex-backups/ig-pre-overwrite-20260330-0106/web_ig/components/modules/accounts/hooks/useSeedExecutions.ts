/**
 * useSeedExecutions — Match RunInfo[] to SeedInfo[] by target_username
 *
 * Produces a Map<seed, SeedExecution> so each SeedCard knows its live status.
 */
import { useMemo } from 'react';
import type { SeedInfo } from '../insightsApi';

// Re-use RunInfo from the execution panel types (avoid duplication)
export interface RunInfo {
    id?: string;
    execution_id?: string;
    playbook_code?: string;
    status?: string;
    started_at?: string;
    created_at?: string;
    completed_at?: string;
    failure_reason?: string;
    execution_context?: {
        inputs?: {
            target_username?: string;
            [key: string]: any;
        };
        target_username?: string;
        [key: string]: any;
    };
    task?: {
        created_at?: string;
        started_at?: string;
        error?: string;
    };
    [key: string]: any;
}

export interface SeedExecution {
    /** The most relevant run (running > pending > most recent) */
    latestRun: RunInfo | null;
    /** Simplified status for the seed */
    status: 'running' | 'pending' | 'completed' | 'failed' | 'idle';
    /** 1-based queue position if pending */
    queuePosition?: number;
    /** All runs for this seed, sorted newest first */
    allRuns: RunInfo[];
}

function getTargetUsername(run: RunInfo): string | null {
    const ctx = run.execution_context;
    const v = ctx?.inputs?.target_username || ctx?.target_username || null;
    return v ? v.toString().trim().toLowerCase().replace(/^@/, '') : null;
}

function normalizeSeedExecutionStatus(status: string | null | undefined): SeedExecution['status'] {
    const lowered = (status || '').toString().trim().toLowerCase();
    if (lowered === 'running') return 'running';
    if (['pending', 'queued', 'paused'].includes(lowered)) return 'pending';
    if (['failed', 'cancelled', 'cancelled_by_user', 'expired'].includes(lowered)) return 'failed';
    if (['completed', 'succeeded'].includes(lowered)) return 'completed';
    return 'idle';
}

function statusPriority(s: string): number {
    const lower = (s || '').toLowerCase();
    if (lower === 'running') return 3;
    if (['pending', 'queued', 'paused'].includes(lower)) return 2;
    if (lower === 'failed') return 1;
    return 0;
}

function runTimestamp(r: RunInfo): number {
    const v = r.created_at || r.started_at || r.task?.created_at || null;
    if (!v) return 0;
    const d = new Date(v);
    return isNaN(d.getTime()) ? 0 : d.getTime();
}

export function useSeedExecutions(
    seeds: SeedInfo[],
    recentRuns: RunInfo[],
): Map<string, SeedExecution> {
    return useMemo(() => {
        const map = new Map<string, SeedExecution>();

        // Initialise every seed with idle
        for (const seed of seeds) {
            const seedKey = seed.seed.toLowerCase();
            const execution = seed.execution;
            if (execution?.status) {
                const authoritativeRun: RunInfo = {
                    execution_id: execution.execution_id || undefined,
                    playbook_code: 'ig_analyze_following',
                    status: execution.status || undefined,
                    created_at: execution.created_at || undefined,
                    started_at: execution.started_at || undefined,
                    completed_at: execution.completed_at || undefined,
                    failure_reason: execution.failure_reason || undefined,
                    task: {
                        error: execution.failure_reason || undefined,
                    },
                    execution_context: {
                        inputs: {
                            target_username: seed.seed,
                        },
                        target_username: seed.seed,
                        blocked_reason: execution.blocked_reason || undefined,
                    },
                };
                map.set(seedKey, {
                    latestRun: authoritativeRun,
                    status: normalizeSeedExecutionStatus(execution.status),
                    queuePosition: execution.queue_position || undefined,
                    allRuns: [authoritativeRun],
                });
                continue;
            }
            map.set(seedKey, {
                latestRun: null,
                status: 'idle',
                allRuns: [],
            });
        }

        // Filter to IG runs only
        const igRuns = (Array.isArray(recentRuns) ? recentRuns : []).filter(
            (r) => (r?.playbook_code || '').toString() === 'ig_analyze_following',
        );

        // Group runs by seed
        for (const run of igRuns) {
            const target = getTargetUsername(run);
            if (!target) continue;

            let entry = map.get(target);
            if (!entry) {
                // Seed not in the seeds list but has runs — create entry anyway
                entry = { latestRun: null, status: 'idle', allRuns: [] };
                map.set(target, entry);
            }
            entry.allRuns.push(run);
        }

        // Determine queue positions for pending runs
        const pendingRuns = igRuns
            .filter((r) => ['pending', 'queued'].includes((r.status || '').toLowerCase()))
            .sort((a, b) => runTimestamp(a) - runTimestamp(b));

        const pendingPositionMap = new Map<string, number>();
        pendingRuns.forEach((r, i) => {
            const id = (r.execution_id || r.id || '').toString();
            if (id) pendingPositionMap.set(id, i + 1);
        });

        // For each seed, pick latestRun and status
        for (const [seed, entry] of map.entries()) {
            if (entry.allRuns.length === 0) continue;

            // Sort: running > pending > failed > other, then by time desc
            entry.allRuns.sort((a, b) => {
                const pa = statusPriority(a.status || '');
                const pb = statusPriority(b.status || '');
                if (pa !== pb) return pb - pa;
                return runTimestamp(b) - runTimestamp(a);
            });

            const best = entry.allRuns[0];
            entry.latestRun = best;

            const s = (best.status || '').toLowerCase();
            if (s === 'running') {
                entry.status = 'running';
            } else if (['pending', 'queued', 'paused'].includes(s)) {
                entry.status = 'pending';
                const id = (best.execution_id || best.id || '').toString();
                entry.queuePosition = pendingPositionMap.get(id) ?? entry.queuePosition;
            } else if (s === 'failed') {
                entry.status = 'failed';
            } else if (s === 'completed') {
                entry.status = 'completed';
            }
        }

        return map;
    }, [seeds, recentRuns]);
}
