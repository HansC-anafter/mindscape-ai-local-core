'use client';

import { FormEvent, useState } from 'react';

import { useLocaleContext } from '@/lib/i18n';
import { useAccessScope } from './useAccessScope';

const COPY = {
  en: {
    members: 'Members',
    invites: 'Pending invitations',
    email: 'Email',
    invite: 'Create secure invite link',
    loading: 'Loading access…',
    empty: 'No members in this scope.',
    remote: 'Remote capability access is managed separately in Pack → Remote access.',
    token: 'Copy this link now. It will not be shown again.',
    revoke: 'Revoke',
  },
  'zh-TW': {
    members: '成員',
    invites: '待接受邀請',
    email: '電子郵件',
    invite: '建立安全邀請連結',
    loading: '正在載入權限…',
    empty: '此範圍目前沒有成員。',
    remote: '遠端能力需另於「Pack → Remote access」管理。',
    token: '請立即複製此連結；離開後不會再次顯示。',
    revoke: '撤銷',
  },
  ja: {
    members: 'メンバー',
    invites: '保留中の招待',
    email: 'メール',
    invite: '安全な招待リンクを作成',
    loading: 'アクセスを読み込み中…',
    empty: 'このスコープにはメンバーがいません。',
    remote: 'リモート機能は Pack → Remote access で別途管理します。',
    token: 'このリンクを今コピーしてください。再表示されません。',
    revoke: '取り消す',
  },
} as const;

const WORKSPACE_ROLES = [
  'workspace_owner',
  'workspace_admin',
  'workspace_editor',
  'workspace_viewer',
];

export function AccessScopeManagementPanel({
  apiUrl,
  endpoint,
  workspaceId,
  scopeType,
}: {
  apiUrl: string;
  endpoint: string;
  workspaceId?: string;
  scopeType: 'local_core' | 'workspace';
}) {
  const { locale } = useLocaleContext();
  const copy = COPY[locale as keyof typeof COPY] || COPY.en;
  const access = useAccessScope({ apiUrl, endpoint, workspaceId });
  const [email, setEmail] = useState('');
  const [roleKey, setRoleKey] = useState(
    scopeType === 'local_core'
      ? 'local_core_super_admin'
      : 'workspace_editor',
  );
  const [submitting, setSubmitting] = useState(false);
  const inviteOrigin = 'https://remote-workbench.mindscapeai.app';

  const onInvite = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await access.invite(email, roleKey);
      setEmail('');
    } finally {
      setSubmitting(false);
    }
  };

  if (access.loading) {
    return <p className="text-sm text-gray-500">{copy.loading}</p>;
  }
  if (access.error) {
    return <p role="alert" className="text-sm text-red-600">{access.error}</p>;
  }

  return (
    <div className="space-y-4" data-testid="access-scope-management">
      <section>
        <h3 className="text-sm font-semibold">{copy.members}</h3>
        <div className="mt-2 space-y-2">
          {access.projection?.members.length ? access.projection.members.map((member) => (
            <div
              key={member.principal_id}
              className="rounded border border-gray-200 p-2 text-xs dark:border-gray-700"
            >
              <div className="break-all font-medium">
                {member.email || member.identities[0]?.verified_email || member.principal_id}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {scopeType === 'workspace' ? (
                  <select
                    aria-label={`Role for ${member.email || member.principal_id}`}
                    value={member.role_key}
                    onChange={(event) => void access.changeRole(
                      member.principal_id,
                      event.target.value,
                    )}
                    className="rounded border border-gray-300 bg-white px-2 py-1 dark:border-gray-700 dark:bg-gray-900"
                  >
                    {WORKSPACE_ROLES.map((role) => (
                      <option key={role} value={role}>{role}</option>
                    ))}
                  </select>
                ) : (
                  <span>{member.role_key}</span>
                )}
                <button
                  type="button"
                  className="rounded border border-red-300 px-2 py-1 text-red-700"
                  onClick={() => void access.revoke(member.principal_id)}
                >
                  {copy.revoke}
                </button>
              </div>
            </div>
          )) : <p className="mt-2 text-xs text-gray-500">{copy.empty}</p>}
        </div>
      </section>

      <form className="space-y-2" onSubmit={onInvite}>
        <label className="block text-xs font-medium">
          {copy.email}
          <input
            required
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded border border-gray-300 bg-white px-2 py-2 dark:border-gray-700 dark:bg-gray-900"
          />
        </label>
        {scopeType === 'workspace' ? (
          <select
            aria-label="Invitation role"
            value={roleKey}
            onChange={(event) => setRoleKey(event.target.value)}
            className="w-full rounded border border-gray-300 bg-white px-2 py-2 text-xs dark:border-gray-700 dark:bg-gray-900"
          >
            {WORKSPACE_ROLES.map((role) => (
              <option key={role} value={role}>{role}</option>
            ))}
          </select>
        ) : null}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {copy.invite}
        </button>
      </form>

      {access.invitationToken ? (
        <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950">
          <p>{copy.token}</p>
          <code className="mt-1 block break-all select-all">
            {`${inviteOrigin}/access/invitations/accept#token=${access.invitationToken}`}
          </code>
          <button
            type="button"
            className="mt-2 underline"
            onClick={access.clearInvitationToken}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      <section>
        <h3 className="text-sm font-semibold">{copy.invites}</h3>
        <ul className="mt-2 space-y-1 text-xs">
          {access.projection?.invitations.map((invitation) => (
            <li key={invitation.invitation_id}>
              {invitation.email} · {invitation.role_key} · {invitation.status}
            </li>
          ))}
        </ul>
      </section>
      {scopeType === 'workspace' ? (
        <p className="text-xs text-gray-500">{copy.remote}</p>
      ) : null}
    </div>
  );
}
