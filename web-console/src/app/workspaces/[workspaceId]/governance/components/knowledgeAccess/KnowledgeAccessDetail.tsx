import type { KnowledgeAccessDetail as Detail } from './types';
import type {
  KnowledgeProjectionAction,
  KnowledgeProjectionActionReceipt,
} from './types';

type Props = {
  detail: Detail;
  onEdit: () => void;
  onAction: (action: KnowledgeProjectionAction) => void;
  actionReceipt: KnowledgeProjectionActionReceipt | null;
  actionPending: boolean;
};

export function KnowledgeAccessDetail({
  detail,
  onEdit,
  onAction,
  actionReceipt,
  actionPending,
}: Props) {
  return (
    <div className="space-y-5" data-testid="knowledge-access-detail">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="break-all text-base font-semibold text-gray-900 dark:text-gray-100">
            {detail.resource.source_ref}
          </h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {detail.resource.owner_capability_code} · {detail.resource.source_kind} · ACL r
            {detail.resource.authz_revision}
          </p>
        </div>
        <button
          type="button"
          onClick={onEdit}
          disabled={detail.grants_truncated}
          className="rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Edit grants
        </button>
      </div>

      {detail.mutation?.graph_reindex_required && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
          ACL updated. Graph-derived community reports are unavailable until this exact source is reindexed.
        </div>
      )}

      <section className="rounded border border-gray-200 p-3 dark:border-gray-700">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Projection actions
        </h4>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Each action is revision-checked and admitted to the existing knowledge indexing lane.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(detail.resource.active
            ? (['reindex', 'retry', 'revoke'] as const)
            : (['restore'] as const)
          ).map((action) => (
            <button
              key={action}
              type="button"
              disabled={actionPending}
              onClick={() => onAction(action)}
              className="rounded border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 disabled:opacity-50 dark:border-gray-600 dark:text-gray-200"
            >
              {action}
            </button>
          ))}
        </div>
        {actionReceipt && (
          <p className="mt-3 break-all text-xs text-emerald-700 dark:text-emerald-300">
            {actionReceipt.action}: {actionReceipt.admission.state}
            {actionReceipt.admission.task_id
              ? ` · ${actionReceipt.admission.task_id}`
              : ''}
          </p>
        )}
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          Human grants
        </h4>
        <div className="overflow-x-auto rounded border border-gray-200 dark:border-gray-700">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2">Principal</th>
                <th className="px-3 py-2">Relation</th>
                <th className="px-3 py-2">Effect</th>
              </tr>
            </thead>
            <tbody>
              {detail.grants.map((grant) => (
                <tr
                  key={`${grant.principal_type}:${grant.principal_id}:${grant.relation}:${grant.effect}`}
                  className="border-t border-gray-200 dark:border-gray-700"
                >
                  <td className="break-all px-3 py-2">
                    {grant.principal_type}:{grant.principal_id}
                  </td>
                  <td className="px-3 py-2">{grant.relation}</td>
                  <td className="px-3 py-2">{grant.effect}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          Modality channels
        </h4>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {detail.modality_truth.map((item) => (
            <div
              key={item.modality}
              className="rounded border border-gray-200 p-3 dark:border-gray-700"
            >
              <p className="text-xs font-medium uppercase text-gray-500">{item.modality}</p>
              <p className="mt-1 text-sm font-semibold text-gray-900 dark:text-gray-100">
                {item.state}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {item.channels.length} channel{item.channels.length === 1 ? '' : 's'}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded border border-gray-200 p-3 text-xs dark:border-gray-700">
        <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          Agent policy
        </h4>
        <p className="text-gray-600 dark:text-gray-300">
          Runtime intersection only. Agent roles can narrow human access and can never grant it.
        </p>
        {detail.agent_mask.persisted_masks.length > 0 && (
          <ul className="mt-2 space-y-1 text-gray-600 dark:text-gray-300">
            {detail.agent_mask.persisted_masks.map((mask) => (
              <li key={`${mask.agent_role}:${mask.effect}`}>
                {mask.agent_role}: {mask.effect}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
