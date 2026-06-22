import type { TrustLevel } from "../governance/permission-map.js";

export interface ToolDefinition {
    name: string;
    description: string;
    inputSchema: object;
    handler: (args: Record<string, unknown>) => Promise<unknown>;
    trustLevel: TrustLevel;
}
