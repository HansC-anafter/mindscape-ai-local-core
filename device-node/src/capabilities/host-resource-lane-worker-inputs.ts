export interface LaneWorkerTargetArgs {
    lane_id?: unknown;
    desired_worker_count?: unknown;
    queue_shard?: unknown;
    runner_profile?: unknown;
    resource_class?: unknown;
    worker_env?: unknown;
}

export function cleanString(value: unknown): string {
    return String(value || "").trim();
}

export function cleanInteger(value: unknown): number {
    const parsed = Number.parseInt(String(value ?? "0"), 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

export function cleanWorkerEnv(value: unknown): Record<string, string> {
    if (!value || typeof value !== "object") {
        return {};
    }
    const env: Record<string, string> = {};
    for (const [key, rawValue] of Object.entries(value as Record<string, unknown>)) {
        const normalizedKey = cleanString(key);
        if (!normalizedKey || rawValue === undefined || rawValue === null) {
            continue;
        }
        env[normalizedKey] = String(rawValue);
    }
    return env;
}
