/**
 * Fixed launchd control for the Mindscape CLI bridge supervisor.
 *
 * This intentionally exposes only the known ai.mindscape.cli-bridge service.
 * It is not a generic shell surface.
 */

import * as os from "os";
import * as path from "path";
import {
    controlLaunchAgentService,
    type LaunchAgentAction,
    type LaunchAgentDescriptor,
} from "../services/mindscape-launch-agent-control.js";

const LABEL = "ai.mindscape.cli-bridge";
const PLIST_PATH = path.join(os.homedir(), "Library", "LaunchAgents", `${LABEL}.plist`);

const CLI_BRIDGE_DESCRIPTOR: LaunchAgentDescriptor = {
    service: "cli_bridge",
    label: LABEL,
    plistPath: PLIST_PATH,
    unsupportedMessage: "LaunchAgent control is only available from the macOS host Device Node.",
    runningMessage: "CLI bridge LaunchAgent is running.",
    stoppedMessage: "CLI bridge LaunchAgent is installed but not running.",
    missingMessage: "CLI bridge LaunchAgent plist is not installed.",
};

function requestedAction(raw: unknown): LaunchAgentAction {
    const value = typeof raw === "string" ? raw.trim().toLowerCase() : "status";
    if (value === "start" || value === "restart") {
        return value;
    }
    return "status";
}

export async function cliBridgeServiceControl(rawArgs: Record<string, unknown>): Promise<Record<string, unknown>> {
    return controlLaunchAgentService(CLI_BRIDGE_DESCRIPTOR, requestedAction(rawArgs.action));
}
