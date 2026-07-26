import type {
  ProductHostAdmissionDetail,
} from '@/lib/workspace-product-configuration-api';

export function HostAdmissionDetails({
  details,
}: {
  details: ProductHostAdmissionDetail[];
}) {
  if (details.length === 0) return null;
  return (
    <details className="mt-3 text-xs text-gray-600 dark:text-gray-400">
      <summary className="cursor-pointer font-medium">
        Device host bindings ({details.filter((item) => item.admitted).length}/{details.length} admitted)
      </summary>
      <ul className="mt-2 space-y-2">
        {details.map((detail) => (
          <li key={`${detail.pack_code}:${detail.requirement_code}:${detail.operation}`}>
            <div>
              {detail.pack_code} · {detail.operation} · {detail.admitted ? 'admitted' : 'blocked'}
            </div>
            {detail.binding_id ? (
              <div className="text-gray-500">
                binding {detail.binding_id}
                {detail.binding_generation ? `@${detail.binding_generation}` : ''}
              </div>
            ) : null}
            {detail.blockers.length > 0 ? (
              <div className="text-amber-700 dark:text-amber-300">
                {detail.blockers.join(', ')}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
