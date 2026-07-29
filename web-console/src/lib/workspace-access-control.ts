export type AccessScopeType = 'local_core' | 'workspace';

export interface AccessMember {
  principal_id: string;
  email: string | null;
  role_key: string;
  expires_at: string | null;
  identities: Array<{
    provider: string;
    issuer: string;
    subject: string;
    verified_email: string | null;
  }>;
}

export interface AccessInvitation {
  invitation_id: string;
  email: string;
  role_key: string;
  status: 'pending' | 'accepted' | 'expired' | 'revoked';
  expires_at: string;
  created_at?: string;
}

export interface AccessScopeProjection {
  scope_type: AccessScopeType;
  scope_id: string;
  revision: number;
  members: AccessMember[];
  invitations: AccessInvitation[];
  audit_events: Array<{
    event_id: string;
    action: string;
    actor_principal_id: string;
    target_principal_id: string | null;
    created_at: string;
  }>;
  role_catalog_version: string;
}

export interface InvitationCreated extends AccessInvitation {
  invitation_token: string;
  revision: number;
  scope_type: AccessScopeType;
  scope_id: string;
}

async function readJson(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(payload?.detail || 'access_control_request_failed'));
  }
  return payload;
}

export async function fetchAccessScope(
  apiUrl: string,
  endpoint: string,
  signal: AbortSignal,
): Promise<AccessScopeProjection> {
  const response = await fetch(`${apiUrl}${endpoint}`, {
    headers: { accept: 'application/json' },
    cache: 'no-store',
    signal,
  });
  return readJson(response);
}

export async function createAccessInvitation(
  apiUrl: string,
  endpoint: string,
  input: {
    email: string;
    role_key: string;
    expected_revision: number;
  },
): Promise<InvitationCreated> {
  const response = await fetch(`${apiUrl}${endpoint}/invitations`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'application/json' },
    cache: 'no-store',
    body: JSON.stringify({ ...input, expires_in_days: 7 }),
  });
  return readJson(response);
}

export async function changeWorkspaceMemberRole(
  apiUrl: string,
  workspaceId: string,
  principalId: string,
  roleKey: string,
  expectedRevision: number,
): Promise<{ revision: number }> {
  const response = await fetch(
    `${apiUrl}/api/v1/access-control/workspaces/${encodeURIComponent(workspaceId)}`
      + `/members/${encodeURIComponent(principalId)}`,
    {
      method: 'PUT',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({
        role_key: roleKey,
        expected_revision: expectedRevision,
      }),
    },
  );
  return readJson(response);
}

export async function revokeWorkspaceMember(
  apiUrl: string,
  workspaceId: string,
  principalId: string,
  expectedRevision: number,
): Promise<{ revision: number }> {
  const params = new URLSearchParams({
    expected_revision: String(expectedRevision),
  });
  const response = await fetch(
    `${apiUrl}/api/v1/access-control/workspaces/${encodeURIComponent(workspaceId)}`
      + `/members/${encodeURIComponent(principalId)}?${params.toString()}`,
    { method: 'DELETE', headers: { accept: 'application/json' } },
  );
  return readJson(response);
}

export async function revokeLocalCoreMember(
  apiUrl: string,
  principalId: string,
  expectedRevision: number,
): Promise<{ revision: number }> {
  const params = new URLSearchParams({
    expected_revision: String(expectedRevision),
  });
  const response = await fetch(
    `${apiUrl}/api/v1/access-control/local-core/members/`
      + `${encodeURIComponent(principalId)}?${params.toString()}`,
    { method: 'DELETE', headers: { accept: 'application/json' } },
  );
  return readJson(response);
}
