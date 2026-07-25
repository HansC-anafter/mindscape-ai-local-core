import type { ProductIterationReviewSummary } from './types';

export function ExperienceSummary({
  summary,
}: {
  summary: ProductIterationReviewSummary['experience_summary'];
}) {
  return (
    <section aria-labelledby="experience-summary-heading">
      <h4 id="experience-summary-heading" className="text-sm font-semibold">
        Experience summary
      </h4>
      {!summary ? (
        <p className="mt-2 text-xs text-gray-500">
          No projection-only experience summary is available.
        </p>
      ) : (
        <>
          <p className="mt-2 text-xs text-gray-500">
            Authority: {summary.authority}
          </p>
          <ul className="mt-2 space-y-2 text-xs">
            {summary.claims.map((claim) => (
              <li key={claim.claim_id}>
                <p>{claim.text}</p>
                <p className="break-all text-gray-500">
                  Sources: {claim.source_observation_ids.join(', ')}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
