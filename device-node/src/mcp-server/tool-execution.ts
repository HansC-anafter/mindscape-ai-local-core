import type { PermissionMap } from "../governance/permission-map.js";
import type { ToolDefinition } from "./tool-definition.js";

export interface ToolExecutionBridge {
    requestConfirmation(request: {
        tool: string;
        arguments: Record<string, unknown>;
        trustLevel: ToolDefinition["trustLevel"];
        preview?: string;
    }): Promise<boolean>;
    reportAuditEvent(event: {
        tool: string;
        arguments: Record<string, unknown>;
        result: "success" | "error";
        error?: string;
        trustLevel: ToolDefinition["trustLevel"];
    }): Promise<void>;
}

export async function executeGovernedTool(
    input: {
        name: string;
        args: Record<string, unknown>;
        tool: ToolDefinition;
        permissionMap: PermissionMap;
        bridge?: ToolExecutionBridge;
    },
): Promise<unknown> {
    const permissionCheck = await input.permissionMap.checkPermission(
        input.name,
        input.args,
    );
    if (!permissionCheck.allowed) {
        throw new Error(`Permission denied: ${permissionCheck.reason}`);
    }
    if (permissionCheck.requiresConfirmation) {
        if (!input.bridge) {
            throw new Error("Permission denied: confirmation bridge unavailable");
        }
        const confirmed = await input.bridge.requestConfirmation({
            tool: input.name,
            arguments: input.args,
            trustLevel: input.tool.trustLevel,
            preview: permissionCheck.preview,
        });
        if (!confirmed) {
            throw new Error("User denied the operation");
        }
    }
    try {
        const result = await input.tool.handler(input.args);
        if (input.bridge) {
            await input.bridge.reportAuditEvent({
                tool: input.name,
                arguments: input.args,
                result: "success",
                trustLevel: input.tool.trustLevel,
            });
        }
        return result;
    } catch (error) {
        if (input.bridge) {
            await input.bridge.reportAuditEvent({
                tool: input.name,
                arguments: input.args,
                result: "error",
                error: error instanceof Error ? error.message : String(error),
                trustLevel: input.tool.trustLevel,
            });
        }
        throw error;
    }
}
