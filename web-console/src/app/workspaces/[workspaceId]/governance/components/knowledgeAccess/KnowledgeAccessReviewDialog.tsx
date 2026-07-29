'use client';

import { useMemo, useState } from 'react';

import type {
  KnowledgeAccessDetail,
  KnowledgeAccessReplacement,
  KnowledgeAgentMask,
  KnowledgeGrant,
} from './types';

type Props = {
  detail: KnowledgeAccessDetail;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (command: KnowledgeAccessReplacement) => Promise<void>;
};

const EMPTY_GRANT: KnowledgeGrant = {
  principal_type: 'user',
  principal_id: '',
  relation: 'reader',
  effect: 'allow',
};
const EMPTY_AGENT_MASK: KnowledgeAgentMask = {
  agent_role: '',
  effect: 'deny',
};

export function KnowledgeAccessReviewDialog({
  detail,
  saving,
  onCancel,
  onSubmit,
}: Props) {
  const [grants, setGrants] = useState<KnowledgeGrant[]>(() =>
    detail.grants.map((grant) => ({ ...grant }))
  );
  const [acknowledged, setAcknowledged] = useState(false);
  const [agentMasks, setAgentMasks] = useState<KnowledgeAgentMask[]>(() =>
    detail.agent_mask.persisted_masks.map((mask) => ({ ...mask }))
  );
  const before = useMemo(
    () =>
      JSON.stringify({
        grants: detail.grants,
        agent_masks: detail.agent_mask.persisted_masks,
      }),
    [detail.agent_mask.persisted_masks, detail.grants]
  );
  const after = useMemo(
    () => JSON.stringify({ grants, agent_masks: agentMasks }),
    [agentMasks, grants]
  );
  const changed = before !== after;
  const valid =
    grants.length > 0 &&
    grants.every((grant) => grant.principal_id.trim()) &&
    agentMasks.every((mask) => mask.agent_role.trim());

  const update = (index: number, patch: Partial<KnowledgeGrant>) => {
    setGrants((current) =>
      current.map((grant, position) =>
        position === index ? { ...grant, ...patch } : grant
      )
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    >
      <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl dark:bg-gray-900">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Review complete ACL replacement
        </h3>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
          This replaces every current grant at ACL revision {detail.resource.authz_revision}. It is not a partial patch.
        </p>

        <div className="mt-4 space-y-2">
          {grants.map((grant, index) => (
            <div
              key={`${index}:${grant.principal_type}:${grant.principal_id}`}
              className="grid gap-2 rounded border border-gray-200 p-3 md:grid-cols-[140px_1fr_120px_100px_auto] dark:border-gray-700"
            >
              <select
                aria-label={`Principal type ${index + 1}`}
                value={grant.principal_type}
                onChange={(event) =>
                  update(index, {
                    principal_type: event.target.value as KnowledgeGrant['principal_type'],
                  })
                }
                className="rounded border border-gray-300 bg-white px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              >
                <option value="user">user</option>
                <option value="workspace_role">workspace_role</option>
                <option value="group_role">group_role</option>
                <option value="service">service</option>
              </select>
              <input
                aria-label={`Principal id ${index + 1}`}
                value={grant.principal_id}
                onChange={(event) => update(index, { principal_id: event.target.value })}
                placeholder="principal id"
                className="rounded border border-gray-300 px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              />
              <select
                aria-label={`Relation ${index + 1}`}
                value={grant.relation}
                onChange={(event) =>
                  update(index, {
                    relation: event.target.value as KnowledgeGrant['relation'],
                  })
                }
                className="rounded border border-gray-300 bg-white px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              >
                <option value="reader">reader</option>
                <option value="editor">editor</option>
                <option value="owner">owner</option>
                <option value="ingester">ingester</option>
              </select>
              <select
                aria-label={`Effect ${index + 1}`}
                value={grant.effect}
                onChange={(event) =>
                  update(index, {
                    effect: event.target.value as KnowledgeGrant['effect'],
                  })
                }
                className="rounded border border-gray-300 bg-white px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
              >
                <option value="allow">allow</option>
                <option value="deny">deny</option>
              </select>
              <button
                type="button"
                onClick={() =>
                  setGrants((current) =>
                    current.filter((_, position) => position !== index)
                  )
                }
                className="rounded border border-red-300 px-2 py-2 text-sm text-red-700 dark:border-red-700 dark:text-red-300"
              >
                Remove
              </button>
            </div>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setGrants((current) => [...current, { ...EMPTY_GRANT }])}
          className="mt-3 rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600"
        >
          Add grant
        </button>

        <div className="mt-5 border-t border-gray-200 pt-4 dark:border-gray-700">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Agent narrowing masks
          </h4>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Empty means no extra agent narrowing. An allow list narrows to those roles; deny always wins.
          </p>
          <div className="mt-3 space-y-2">
            {agentMasks.map((mask, index) => (
              <div
                key={`${index}:${mask.agent_role}:${mask.effect}`}
                className="grid gap-2 rounded border border-gray-200 p-3 md:grid-cols-[1fr_120px_auto] dark:border-gray-700"
              >
                <input
                  aria-label={`Agent role ${index + 1}`}
                  value={mask.agent_role}
                  onChange={(event) =>
                    setAgentMasks((current) =>
                      current.map((item, position) =>
                        position === index
                          ? { ...item, agent_role: event.target.value }
                          : item
                      )
                    )
                  }
                  placeholder="server-bound agent role"
                  className="rounded border border-gray-300 px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                />
                <select
                  aria-label={`Agent effect ${index + 1}`}
                  value={mask.effect}
                  onChange={(event) =>
                    setAgentMasks((current) =>
                      current.map((item, position) =>
                        position === index
                          ? {
                              ...item,
                              effect: event.target.value as KnowledgeAgentMask['effect'],
                            }
                          : item
                      )
                    )
                  }
                  className="rounded border border-gray-300 bg-white px-2 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
                >
                  <option value="allow">allow</option>
                  <option value="deny">deny</option>
                </select>
                <button
                  type="button"
                  onClick={() =>
                    setAgentMasks((current) =>
                      current.filter((_, position) => position !== index)
                    )
                  }
                  className="rounded border border-red-300 px-2 py-2 text-sm text-red-700 dark:border-red-700 dark:text-red-300"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={() =>
              setAgentMasks((current) => [
                ...current,
                { ...EMPTY_AGENT_MASK },
              ])
            }
            className="mt-3 rounded border border-gray-300 px-3 py-2 text-sm dark:border-gray-600"
          >
            Add agent mask
          </button>
        </div>

        <label className="mt-5 flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
            className="mt-1"
          />
          I acknowledge this is a complete replacement. A stale revision will be rejected without changing the current snapshot.
        </label>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded border border-gray-300 px-4 py-2 text-sm dark:border-gray-600"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!changed || !valid || !acknowledged || saving}
            onClick={() =>
              void onSubmit({
                expected_authz_revision: detail.resource.authz_revision,
                acknowledge_complete_replacement: true,
                grants,
                agent_masks: agentMasks,
              })
            }
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Replace grants'}
          </button>
        </div>
      </div>
    </div>
  );
}
