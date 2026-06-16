import {
    cleanInteger,
    cleanString,
    cleanWorkerEnv,
    type LaneWorkerTargetArgs,
} from "./host-resource-lane-worker-inputs.js";
import {
    resolveManagedWorker,
    spawnMlxWorker,
    stopLaneWorker,
    WORKER_START_GRACE_SECONDS,
} from "./host-resource-lane-worker-lifecycle.js";
import { mlxLauncherPath } from "./host-resource-lane-worker-paths.js";
import {
    isPortListening,
    listPortOwners,
    workerAgeSeconds,
} from "./host-resource-lane-worker-processes.js";

export async function hostResourceLaneWorkersSet(args: Record<string, unknown>): Promise<Record<string, unknown>> {
    const payload = args as LaneWorkerTargetArgs;
    const laneId = cleanString(payload.lane_id);
    const queueShard = cleanString(payload.queue_shard);
    const runnerProfile = cleanString(payload.runner_profile);
    const resourceClass = cleanString(payload.resource_class);
    const desiredWorkerCount = cleanInteger(payload.desired_worker_count);
    const workerEnv = cleanWorkerEnv(payload.worker_env);
    const port = cleanInteger(workerEnv.MLX_PORT);

    if (!laneId) {
        return {
            accepted: false,
            reason: "lane_id_required",
        };
    }
    if (desiredWorkerCount === 0) {
        return {
            ...(await stopLaneWorker(laneId, port)),
            queue_shard: queueShard || null,
        };
    }
    if (desiredWorkerCount > 1) {
        return {
            accepted: false,
            reason: "desired_worker_count_exceeds_device_node_limit",
            lane_id: laneId,
            desired_worker_count: desiredWorkerCount,
            max_worker_count: 1,
        };
    }
    if (cleanString(workerEnv.LOCAL_CORE_RUNTIME_ADAPTER_ID) !== "apple_mlx_vlm") {
        return {
            accepted: false,
            reason: "unsupported_worker_runtime_adapter",
            lane_id: laneId,
            runtime_adapter_id: cleanString(workerEnv.LOCAL_CORE_RUNTIME_ADAPTER_ID) || null,
        };
    }
    if (port <= 0) {
        return {
            accepted: false,
            reason: "mlx_port_required",
            lane_id: laneId,
        };
    }
    if (!cleanString(workerEnv.MLX_MODEL)) {
        return {
            accepted: false,
            reason: "mlx_model_required",
            lane_id: laneId,
            port,
        };
    }

    const launcher = mlxLauncherPath();
    if (!launcher) {
        return {
            accepted: false,
            reason: "mlx_launcher_missing",
            lane_id: laneId,
        };
    }
    const current = resolveManagedWorker(launcher.root, laneId);
    if (current) {
        if (await isPortListening(current.port)) {
            return {
                accepted: true,
                reason: "worker_target_already_running",
                lane_id: laneId,
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                active_worker_count: 1,
                pid: current.pid,
                port: current.port,
                worker_env_keys: Object.keys(workerEnv).sort(),
            };
        }
        const ageSeconds = workerAgeSeconds(current);
        if (ageSeconds < WORKER_START_GRACE_SECONDS) {
            return {
                accepted: true,
                reason: "worker_target_starting",
                lane_id: laneId,
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                active_worker_count: 0,
                pid: current.pid,
                port: current.port,
                started_at: current.startedAt,
                worker_age_seconds: ageSeconds,
                startup_grace_seconds: WORKER_START_GRACE_SECONDS,
                worker_env_keys: Object.keys(workerEnv).sort(),
            };
        }
        const stopResult = await stopLaneWorker(laneId, current.port, launcher.root);
        if (stopResult.accepted !== true) {
            return {
                ...stopResult,
                reason: "worker_target_restart_blocked",
                queue_shard: queueShard || null,
                runner_profile: runnerProfile || null,
                resource_class: resourceClass || null,
                desired_worker_count: desiredWorkerCount,
                blocked_worker_pid: current.pid,
                blocked_worker_port: current.port,
            };
        }
    }
    if (await isPortListening(port)) {
        const portOwners = await listPortOwners(port);
        return {
            accepted: false,
            reason: "worker_target_port_conflict_unmanaged",
            lane_id: laneId,
            queue_shard: queueShard || null,
            runner_profile: runnerProfile || null,
            resource_class: resourceClass || null,
            desired_worker_count: desiredWorkerCount,
            active_worker_count: 1,
            port,
            port_owners: portOwners,
            worker_env_keys: Object.keys(workerEnv).sort(),
        };
    }

    try {
        const worker = spawnMlxWorker(laneId, workerEnv, launcher, port);
        return {
            accepted: true,
            reason: "worker_target_started",
            lane_id: laneId,
            queue_shard: queueShard || null,
            runner_profile: runnerProfile || null,
            resource_class: resourceClass || null,
            desired_worker_count: desiredWorkerCount,
            active_worker_count: 1,
            pid: worker.pid,
            port: worker.port,
            log_dir: worker.logDir,
            watchdog_state_file: worker.watchdogStateFile,
            started_at: worker.startedAt,
            launcher_script: launcher.script,
            worker_env_keys: Object.keys(workerEnv).sort(),
        };
    } catch (error) {
        return {
            accepted: false,
            reason: "worker_spawn_failed",
            lane_id: laneId,
            queue_shard: queueShard || null,
            desired_worker_count: desiredWorkerCount,
            error: error instanceof Error ? error.message : String(error),
        };
    }
}
