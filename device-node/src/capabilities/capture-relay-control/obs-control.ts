import {
    DEFAULT_OBS_WEBSOCKET_PORT,
    DEFAULT_RTMP_PORT,
    DEFAULT_RTSP_PORT,
} from "./constants.js";
import {
    buildRelayUrls,
    normalizePort,
    normalizeStreamName,
} from "./host-discovery.js";
import { createObsRpcClient } from "./obs-rpc.js";
import {
    buildStatus,
    isTcpPortOpen,
    sleepMs,
} from "./relay-process.js";
import type { CaptureRelayArgs, ObsRpcClient } from "./types.js";

function normalizeObsEntityName(value: unknown, fallback: string): string {
    const normalized = String(value || "")
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 80);
    return normalized || fallback;
}

export async function configureObs(args: CaptureRelayArgs): Promise<Record<string, unknown>> {
    const streamName = normalizeStreamName(args.stream_name);
    const rtmpPort = normalizePort(args.rtmp_port, DEFAULT_RTMP_PORT);
    const rtspPort = normalizePort(args.rtsp_port, DEFAULT_RTSP_PORT);
    const urls = buildRelayUrls(streamName, rtmpPort, rtspPort);
    const host = String(args.obs_websocket_host || "127.0.0.1");
    const port = normalizePort(args.obs_websocket_port, DEFAULT_OBS_WEBSOCKET_PORT);
    const timeoutMs = Math.min(Math.max(Number(args.timeout_ms || 8000), 1000), 15000);
    const sceneName = normalizeObsEntityName(args.scene_name, "Mindscape External Camera");
    const sourceName = normalizeObsEntityName(args.source_name, "Mindscape RTSP Source");
    const startVirtualCamera = args.start_virtual_camera !== false;
    const steps: string[] = [];

    if (!(await isTcpPortOpen(host, port))) {
        return buildStatus("configure_obs", args, {
            configure_result: "blocked",
            reason: "obs_websocket_unreachable",
            obs_setup: {
                scene_name: sceneName,
                source_name: sourceName,
                read_url: urls.read_url,
                steps,
            },
        });
    }

    let client: ObsRpcClient | null = null;
    try {
        client = await createObsRpcClient(host, port, timeoutMs);
        try {
            await client.request("CreateScene", { sceneName });
            steps.push("scene_created");
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            if (!/already exists|already.*exists|duplicate/i.test(message)) {
                throw error;
            }
            steps.push("scene_reused");
        }

        const inputSettings = {
            input: urls.read_url,
            is_local_file: false,
            looping: true,
            restart_on_activate: true,
            close_when_inactive: false,
            clear_on_media_end: false,
            reconnect_delay_sec: 2,
            buffering_mb: 2,
        };
        const inputList = await client.request("GetInputList");
        const inputs = Array.isArray(inputList.inputs) ? inputList.inputs as Array<Record<string, unknown>> : [];
        const existingInput = inputs.some((input) => input.inputName === sourceName);
        if (existingInput) {
            await client.request("SetInputSettings", {
                inputName: sourceName,
                inputSettings,
                overlay: true,
            });
            steps.push("source_updated");
        } else {
            await client.request("CreateInput", {
                sceneName,
                inputName: sourceName,
                inputKind: "ffmpeg_source",
                inputSettings,
                sceneItemEnabled: true,
            });
            steps.push("source_created");
        }

        await client.request("SetCurrentProgramScene", { sceneName });
        steps.push("program_scene_selected");

        let virtualCameraStatus: Record<string, unknown> | null = null;
        if (startVirtualCamera) {
            try {
                await client.request("StartVirtualCam");
                steps.push("virtual_camera_started");
                virtualCameraStatus = { started: true };
                await sleepMs(800);
            } catch (error) {
                steps.push("virtual_camera_start_blocked");
                virtualCameraStatus = {
                    started: false,
                    reason: error instanceof Error ? error.message : String(error),
                };
            }
        }
        for (let attempt = 0; attempt < 3; attempt += 1) {
            try {
                const status = await client.request("GetVirtualCamStatus");
                virtualCameraStatus = {
                    ...(virtualCameraStatus || {}),
                    active: status.outputActive,
                };
                if (status.outputActive === true || !startVirtualCamera) {
                    break;
                }
                await sleepMs(500);
            } catch {
                // OBS versions differ here; the setup result is still useful without this readback.
                break;
            }
        }

        const virtualCameraActive = virtualCameraStatus?.active === true;
        const virtualCameraBlocked = startVirtualCamera
            && !virtualCameraActive
            && (virtualCameraStatus?.started === false || virtualCameraStatus?.active === false);
        return buildStatus("configure_obs", args, {
            configure_result: virtualCameraBlocked
                ? "partial"
                : "configured",
            obs_setup: {
                scene_name: sceneName,
                source_name: sourceName,
                read_url: urls.read_url,
                steps,
                virtual_camera: virtualCameraStatus,
            },
        });
    } catch (error) {
        return buildStatus("configure_obs", args, {
            configure_result: "failed",
            reason: error instanceof Error ? error.message : String(error),
            obs_setup: {
                scene_name: sceneName,
                source_name: sourceName,
                read_url: urls.read_url,
                steps,
            },
        });
    } finally {
        client?.close();
    }
}
