'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  AccessScopeProjection,
  changeWorkspaceMemberRole,
  createAccessInvitation,
  fetchAccessScope,
  revokeLocalCoreMember,
  revokeWorkspaceMember,
} from '@/lib/workspace-access-control';

export function useAccessScope({
  apiUrl,
  endpoint,
  workspaceId,
}: {
  apiUrl: string;
  endpoint: string;
  workspaceId?: string;
}) {
  const [projection, setProjection] = useState<AccessScopeProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [invitationToken, setInvitationToken] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchAccessScope(apiUrl, endpoint, controller.signal)
      .then((next) => {
        setProjection(next);
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : 'access_load_failed');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [apiUrl, endpoint]);

  const invite = useCallback(async (email: string, roleKey: string) => {
    if (!projection) return;
    const created = await createAccessInvitation(apiUrl, endpoint, {
      email,
      role_key: roleKey,
      expected_revision: projection.revision,
    });
    setInvitationToken(created.invitation_token);
    setProjection((current) => current && ({
      ...current,
      revision: created.revision,
      invitations: [
        {
          invitation_id: created.invitation_id,
          email: created.email,
          role_key: created.role_key,
          status: 'pending' as const,
          expires_at: created.expires_at,
        },
        ...current.invitations,
      ].slice(0, 64),
    }));
  }, [apiUrl, endpoint, projection]);

  const changeRole = useCallback(async (principalId: string, roleKey: string) => {
    if (!projection || !workspaceId) return;
    const result = await changeWorkspaceMemberRole(
      apiUrl,
      workspaceId,
      principalId,
      roleKey,
      projection.revision,
    );
    setProjection((current) => current && ({
      ...current,
      revision: result.revision,
      members: current.members.map((member) => (
        member.principal_id === principalId
          ? { ...member, role_key: roleKey }
          : member
      )),
    }));
  }, [apiUrl, projection, workspaceId]);

  const revoke = useCallback(async (principalId: string) => {
    if (!projection) return;
    const result = workspaceId
      ? await revokeWorkspaceMember(
          apiUrl,
          workspaceId,
          principalId,
          projection.revision,
        )
      : await revokeLocalCoreMember(
          apiUrl,
          principalId,
          projection.revision,
        );
    setProjection((current) => current && ({
      ...current,
      revision: result.revision,
      members: current.members.filter(
        (member) => member.principal_id !== principalId,
      ),
    }));
  }, [apiUrl, projection, workspaceId]);

  return {
    projection,
    loading,
    error,
    invitationToken,
    clearInvitationToken: () => setInvitationToken(null),
    invite,
    changeRole,
    revoke,
  };
}
