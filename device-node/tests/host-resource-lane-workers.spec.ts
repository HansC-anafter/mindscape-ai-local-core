import test from "node:test";
import assert from "node:assert/strict";

import { hostResourceLaneWorkersSet } from "../src/capabilities/host-resource-lane-workers.js";

test("hostResourceLaneWorkersSet requires lane id before worker lifecycle checks", async () => {
    assert.deepEqual(
        await hostResourceLaneWorkersSet({ desired_worker_count: 1 }),
        {
            accepted: false,
            reason: "lane_id_required",
        },
    );
});

test("hostResourceLaneWorkersSet rejects multiple workers at device-node boundary", async () => {
    assert.deepEqual(
        await hostResourceLaneWorkersSet({
            lane_id: "runner:vision",
            desired_worker_count: 2,
        }),
        {
            accepted: false,
            reason: "desired_worker_count_exceeds_device_node_limit",
            lane_id: "runner:vision",
            desired_worker_count: 2,
            max_worker_count: 1,
        },
    );
});

test("hostResourceLaneWorkersSet rejects unsupported runtime adapter before launcher lookup", async () => {
    assert.deepEqual(
        await hostResourceLaneWorkersSet({
            lane_id: "runner:vision",
            desired_worker_count: 1,
            worker_env: {
                LOCAL_CORE_RUNTIME_ADAPTER_ID: "other_runtime",
            },
        }),
        {
            accepted: false,
            reason: "unsupported_worker_runtime_adapter",
            lane_id: "runner:vision",
            runtime_adapter_id: "other_runtime",
        },
    );
});

test("hostResourceLaneWorkersSet requires MLX port before launcher lookup", async () => {
    assert.deepEqual(
        await hostResourceLaneWorkersSet({
            lane_id: "runner:vision",
            desired_worker_count: 1,
            worker_env: {
                LOCAL_CORE_RUNTIME_ADAPTER_ID: "apple_mlx_vlm",
            },
        }),
        {
            accepted: false,
            reason: "mlx_port_required",
            lane_id: "runner:vision",
        },
    );
});

test("hostResourceLaneWorkersSet requires MLX model before launcher lookup", async () => {
    assert.deepEqual(
        await hostResourceLaneWorkersSet({
            lane_id: "runner:vision",
            desired_worker_count: 1,
            worker_env: {
                LOCAL_CORE_RUNTIME_ADAPTER_ID: "apple_mlx_vlm",
                MLX_PORT: "8123",
            },
        }),
        {
            accepted: false,
            reason: "mlx_model_required",
            lane_id: "runner:vision",
            port: 8123,
        },
    );
});
