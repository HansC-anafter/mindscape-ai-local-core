export interface ExecutionContext {
  actor_id: string;

  workspace_id: string;

  tags?: Record<string, string>;

  authToken?: string;
}

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
