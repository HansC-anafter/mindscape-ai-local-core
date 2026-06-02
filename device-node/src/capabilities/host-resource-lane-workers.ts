interface LaneWorkerTargetArgs {
    lane_id?: unknown;
    desired_worker_count?: unknown;
    queue_shard?: unknown;
    runner_profile?: unknown;
    resource_class?: unknown;
    worker_env?: unknown;
}

function cleanString(value: unknown): string {
    return String(value || "").trim();
}

function cleanInteger(value: unknown): number {
    const parsed = Number.parseInt(String(value ?? "0"), 10);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

export async function hostResourceLaneWorkersSet(args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const payload = args as LaneWorkerTargetArgs;
    const laneId = cleanString(payload.lane_id);
    const queueShard = cleanString(payload.queue_shard);
    const desiredWorkerCount = cleanInteger(payload.desired_worker_count);

    if (!laneId) {
        return {
            accepted: false,
            reason: "lane_id_required",
        };
    }

    if (desiredWorkerCount === 0) {
        return {
            accepted: true,
            reason: "worker_target_zero_synced",
            lane_id: laneId,
            queue_shard: queueShard || null,
            desired_worker_count: 0,
            active_worker_count: 0,
        };
    }

    return {
        accepted: false,
        reason: "worker_spawn_not_configured",
        lane_id: laneId,
        queue_shard: queueShard || null,
        runner_profile: cleanString(payload.runner_profile) || null,
        resource_class: cleanString(payload.resource_class) || null,
        desired_worker_count: desiredWorkerCount,
        worker_env_keys: payload.worker_env && typeof payload.worker_env === "object"
            ? Object.keys(payload.worker_env as Record<string, unknown>).sort()
            : [],
    };
}
