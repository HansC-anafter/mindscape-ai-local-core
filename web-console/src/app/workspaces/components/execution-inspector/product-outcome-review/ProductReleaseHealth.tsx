import type { ProductIterationReviewSummary } from './types';

export function ProductReleaseHealth({
  release,
}: {
  release: ProductIterationReviewSummary['product_release'];
}) {
  return (
    <section aria-labelledby="product-release-health-heading">
      <h4 id="product-release-health-heading" className="text-sm font-semibold">
        Product release health
      </h4>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        <dt>Release state</dt><dd>{release.state}</dd>
        <dt>Release workflow</dt>
        <dd className="break-all">{release.release_workflow_id ?? 'not_started'}</dd>
        <dt>Health receipt</dt>
        <dd>{release.health ? 'recorded' : 'not_started'}</dd>
        <dt>Lifecycle receipt</dt>
        <dd>{release.lifecycle ? 'recorded' : 'not_started'}</dd>
      </dl>
    </section>
  );
}
