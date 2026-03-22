# GPU Executor Node

This guide describes the Phase A deployment shape for a dedicated GPU executor node.

## Goal

Run a **headless `local-core` backend** on a dedicated GPU VM so the node can:

- connect back to the execution control plane via `CloudConnector`
- execute remote `job_type="tool"` requests
- expose installed capability tools such as `core_llm.multimodal_analyze`

Phase A is intentionally narrow:

- keep `preprocess` and `backfill` on the main workstation runtime
- remote only the heavy multimodal step
- do **not** move whole-playbook execution to the GPU node yet

## Node Shape

The GPU executor node runs:

- `backend`
- `postgres`
- `redis`
- an external or colocated OpenAI-compatible VLM endpoint

The GPU executor node does **not** run:

- `frontend`
- workspace UI / workbench
- `device-node`
- `runner` in Phase A

## Prerequisites

- Docker Engine with `docker compose`
- a GPU VM with the required CUDA / model-serving stack already prepared
- a reachable `site-hub` execution control plane
- a valid connector auth token for websocket registration
- `.mindpack` artifacts copied onto the VM

Use a **dedicated `local-core` checkout on the GPU VM**. This compose file writes runtime state to local `./data` and `./logs`, so it should not share a workstation checkout or database volume root.

Phase A required pack set:

- `core_llm.mindpack`

## 1. Prepare Environment

Copy the example env file:

```bash
cp .env.gpu-executor.example .env.gpu-executor
```

Set at least:

- `EXECUTION_CONTROL_API_URL`
- `SITE_KEY`
- `TENANT_ID`
- `DEVICE_ID`
- `CLOUD_PROVIDER_TOKEN` or `CLOUD_API_TOKEN`
- `VISION_MODEL_BASE_URL`

Notes:

- `VISION_MODEL_BASE_URL` should point to an **OpenAI-compatible** multimodal endpoint.
- `EXECUTION_CONTROL_WS_URL` is optional; if empty, `CloudConnector` derives it from the API URL.
- `DEVICE_ID` should be stable per VM so routing and audit trails remain readable.

## 2. Start the Headless Stack

```bash
docker compose \
  --env-file .env.gpu-executor \
  -f docker-compose.gpu-executor.yml \
  up -d --build
```

This starts only the executor runtime services. It does not start the workstation UI stack.

## 3. Install the Phase A Pack Set

Use the bootstrap script after the backend is healthy:

```bash
./scripts/bootstrap_gpu_executor.sh /absolute/path/to/core_llm.mindpack
```

What the script does:

1. waits for `GET /health`
2. installs each provided `.mindpack` through `/api/v1/capability-packs/install-from-file`
3. verifies `/api/v1/tools/` contains `core_llm.multimodal_analyze`

If you need to reinstall over an existing node, keep the default:

```bash
ALLOW_OVERWRITE=true
```

## 4. Verify Node Readiness

Minimum checks:

```bash
curl -sS http://127.0.0.1:8200/health
curl -sS http://127.0.0.1:8200/api/v1/tools/ | python3 -c 'import json,sys; print(any((item.get("tool_id")=="core_llm.multimodal_analyze") for item in json.load(sys.stdin)))'
docker compose -f docker-compose.gpu-executor.yml logs --tail 120 backend
```

Readiness indicators:

- backend health returns `healthy`
- `core_llm.multimodal_analyze` appears in the tool list
- logs show `Cloud Connector initialized and connecting...`
- the node registers to the execution control plane with the configured `DEVICE_ID`

## 5. Use with IG Phase A

Keep the workstation-side flow as:

- local `preprocess`
- remote `vision_analyze`
- local `backfill`

Recommended env on the main workstation runtime:

```bash
IG_ANALYZE_VISION_EXECUTION_BACKEND=remote
IG_ANALYZE_VISION_TARGET_DEVICE_ID=<gpu-vm-device-id>
```

Phase A success means only the multimodal tool call is offloaded. Do not remote the entire IG playbook yet.

## Troubleshooting

### Tool does not appear after pack install

- verify the `.mindpack` actually contains `core_llm/manifest.yaml`
- check install response from `/api/v1/capability-packs/install-from-file`
- inspect backend logs for manifest validation or runtime asset install failures

### Node connects but multimodal execution fails

- verify `VISION_MODEL_BASE_URL` points to a working OpenAI-compatible endpoint
- verify the model endpoint accepts `/v1/chat/completions`
- verify the remote node can reach that endpoint from inside the backend container

### Do I need to install `ig` on the GPU VM?

No for Phase A.

The current remote slice is only:

- `tool_name = core_llm.multimodal_analyze`

So the GPU node only needs the `core_llm` capability pack plus its model endpoint.
