import { openObsApp } from "./capture-relay-control/host-actions.js";
import {
    buildRelayUrls,
    normalizeStreamName,
    resolveObsAppPath,
    resolveRelayBinary,
} from "./capture-relay-control/host-discovery.js";
import { configureObs } from "./capture-relay-control/obs-control.js";
import { inferPublisherState } from "./capture-relay-control/publisher-state.js";
import {
    getLiveMediaReceiverStatus,
    startLiveMediaReceiver,
    stopLiveMediaReceiver,
} from "./capture-relay-control/live-media-receiver.js";
import {
    buildStatus,
    installMediaMtx,
    startRelay,
    stopRelay,
} from "./capture-relay-control/relay-process.js";
import type {
    CaptureRelayAction,
    CaptureRelayArgs,
    RelayPublisherState,
    RelayUrls,
} from "./capture-relay-control/types.js";

export {
    buildRelayUrls,
    inferPublisherState,
    normalizeStreamName,
    resolveObsAppPath,
    resolveRelayBinary,
};
export type { CaptureRelayAction, CaptureRelayArgs, RelayPublisherState, RelayUrls };

const SUPPORTED_ACTIONS: CaptureRelayAction[] = [
    "status",
    "install_mediamtx",
    "start",
    "stop",
    "open_obs",
    "configure_obs",
    "receiver_start",
    "receiver_status",
    "receiver_stop",
];

export async function captureRelayControl(
    rawArgs: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const args = rawArgs as CaptureRelayArgs;
    const action = (String(args.action || "status").trim() || "status") as CaptureRelayAction;
    if (!SUPPORTED_ACTIONS.includes(action)) {
        return {
            schema_version: "capture_relay_control.v1",
            action,
            status: "rejected",
            reason: "unsupported_action",
        };
    }
    if (action === "install_mediamtx") {
        return installMediaMtx(args);
    }
    if (action === "start") {
        const result = await startRelay(args);
        if (args.open_obs) {
            return { ...result, obs_open: await openObsApp() };
        }
        return result;
    }
    if (action === "stop") {
        return stopRelay(args);
    }
    if (action === "open_obs") {
        return buildStatus("open_obs", args, { obs_open: await openObsApp() });
    }
    if (action === "configure_obs") {
        return configureObs(args);
    }
    if (action === "receiver_start") {
        return startLiveMediaReceiver(args.receiver_descriptor, Number(args.timeout_ms || 10000));
    }
    if (action === "receiver_status") {
        return getLiveMediaReceiverStatus(String(args.media_session_id || ""));
    }
    if (action === "receiver_stop") {
        return await stopLiveMediaReceiver(
            String(args.media_session_id || ""),
            String(args.receiver_identity || ""),
            Number(args.timeout_ms || 10000),
        );
    }
    return buildStatus("status", args);
}

export default captureRelayControl;
