/**
 * ExecutionContext - Core domain abstraction for execution context
 *
 * This type represents the execution context in a way that works for both
 * Local and Cloud environments without exposing cloud-specific concepts.
 */

export interface ExecutionContext {
  /**
   * Actor ID - The entity performing the action
   * In local mode: typically "local-user"
   * In cloud mode: user ID from authentication
   */
  actor_id: string;

  /**
   * Workspace ID - The workspace where the action occurs
   */
  workspace_id: string;

  /**
   * Tags - Optional key-value dictionary for additional context
   *
   * Local mode: { mode: "local" }
   * Cloud mode: { mode: "cloud", tenant_id: "...", group_id: "...", plan: "..." }
   *
   * Core services don't interpret tags - they just pass it through.
   * Adapters and external services can read/write tags as needed.
   */
  tags?: Record<string, string>;

  /**
   * Auth token for API calls (Cloud mode only).
   * Populated by ExecutionContextProvider from session/cookie.
   * Local mode: always undefined.
   */
  authToken?: string;
}

/**
 * Create a default ExecutionContext for local mode
 */
export function createLocalExecutionContext(
  workspaceId: string,
  actorId: string = 'local-user'
): ExecutionContext {
  return {
    actor_id: actorId,
    workspace_id: workspaceId,
    tags: {
      mode: 'local'
    }
  };
}

