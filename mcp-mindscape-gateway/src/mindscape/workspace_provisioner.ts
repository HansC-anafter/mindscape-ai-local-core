/**
 * Auto-Provision Workspace for MCP Gateway
 *
 * Automatically creates or finds workspaces so external AI tools
 * don't need to know workspace_id in advance.
 */
import { MindscapeClient } from "./client.js";
import { config } from "../config.js";

export interface Workspace {
    id: string;
    title: string;
    owner_user_id: string;
    description?: string;
}

export interface CreateWorkspaceParams {
    title: string;
    owner_user_id: string;
    description?: string;
}

export class WorkspaceProvisioner {
    private cachedWorkspaceId: string | null = null;

    constructor(private client: MindscapeClient) { }

    /**
     * Get or create workspace.
     *
     * Logic:
     * 1. If config.workspaceId is set -> use it
     * 2. If cached -> return cache
     * 3. Search existing workspace -> use if found
     * 4. If autoProvision enabled -> create new workspace
     */
    async getOrCreateWorkspace(): Promise<string> {
        if (config.workspaceId) {
            return config.workspaceId;
        }

        if (this.cachedWorkspaceId) {
            return this.cachedWorkspaceId;
        }

        try {
            const existing = await this.client.findWorkspaceByTitle(
                config.defaultWorkspaceTitle,
                config.profileId
            );

            if (existing) {
                this.cachedWorkspaceId = existing.id;
                console.error(`[Provisioner] Found existing workspace: ${existing.id} (${existing.title})`);
                return existing.id;
            }
        } catch (err) {
            console.error("[Provisioner] Failed to search for existing workspace:", err);
        }

        if (config.autoProvision) {
            try {
                const created = await this.client.createWorkspace({
                    title: config.defaultWorkspaceTitle,
                    owner_user_id: config.profileId,
                    description: "Auto-provisioned by MCP Gateway"
                });
                this.cachedWorkspaceId = created.id;
                console.error(`[Provisioner] Created new workspace: ${created.id} (${created.title})`);
                return created.id;
            } catch (err) {
                console.error("[Provisioner] Failed to create workspace:", err);
                throw new Error("Failed to auto-provision workspace");
            }
        }

        throw new Error(
            "No workspace configured and auto-provision disabled. " +
            "Set MINDSCAPE_WORKSPACE_ID or enable MINDSCAPE_AUTO_PROVISION."
        );
    }

    /**
     * Clear cache (for testing or re-provisioning)
     */
    clearCache(): void {
        this.cachedWorkspaceId = null;
    }

    /**
     * Get cached workspace ID without triggering provision
     */
    getCachedWorkspaceId(): string | null {
        return this.cachedWorkspaceId || config.workspaceId || null;
    }

    // ============================================
    // Multi-Workspace Mode Support
    // ============================================

    /**
     * Get or create workspace by surface_user_id (multi_workspace mode).
     * This allows each external user to have their own workspace.
     *
     * @param surfaceUserId External surface user identifier (e.g., LINE user ID)
     * @param surfaceType External surface type (e.g., "line", "discord")
     */
    async getWorkspaceForSurfaceUser(
        surfaceUserId: string,
        surfaceType: string = "external"
    ): Promise<string> {
        const workspaceTitle = `${surfaceType}:${surfaceUserId}`;

        try {
            const existing = await this.client.findWorkspaceByTitle(
                workspaceTitle,
                config.profileId
            );

            if (existing) {
                console.error(`[Provisioner] Found workspace for ${surfaceType} user ${surfaceUserId}: ${existing.id}`);
                return existing.id;
            }
        } catch (err) {
            console.error("[Provisioner] Failed to search workspace for surface user:", err);
        }

        if (config.autoProvision) {
            try {
                const created = await this.client.createWorkspace({
                    title: workspaceTitle,
                    owner_user_id: config.profileId,
                    description: `Auto-provisioned for ${surfaceType} user: ${surfaceUserId}`
                });
                console.error(`[Provisioner] Created workspace for ${surfaceType} user ${surfaceUserId}: ${created.id}`);
                return created.id;
            } catch (err) {
                console.error("[Provisioner] Failed to create workspace for surface user:", err);
                throw new Error(`Failed to provision workspace for ${surfaceType} user`);
            }
        }

        throw new Error(
            `No workspace found for ${surfaceType} user ${surfaceUserId} and auto-provision disabled`
        );
    }

    /**
     * Intelligently resolve workspace ID (unified entry point).
     *
     * Based on gatewayMode and input parameters:
     * - single_workspace: use default workspace
     * - multi_workspace: resolve by surface_user_id or workspace_id parameter
     */
    async resolveWorkspace(params?: {
        workspace_id?: string;
        surface_user_id?: string;
        surface_type?: string;
    }): Promise<string> {
        if (params?.workspace_id) {
            return params.workspace_id;
        }

        if (config.gatewayMode === "multi_workspace" && params?.surface_user_id) {
            return this.getWorkspaceForSurfaceUser(
                params.surface_user_id,
                params.surface_type || "external"
            );
        }

        return this.getOrCreateWorkspace();
    }
}
