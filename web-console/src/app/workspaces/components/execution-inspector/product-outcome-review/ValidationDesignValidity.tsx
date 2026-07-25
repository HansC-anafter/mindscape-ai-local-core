export function ValidationDesignValidity({
  validationDesign,
  evaluator,
}: {
  validationDesign: Record<string, unknown>;
  evaluator: {
    evaluator_id: string;
    version: string;
    contract_hash: string;
  };
}) {
  return (
    <section aria-labelledby="validation-validity-heading">
      <h4 id="validation-validity-heading" className="text-sm font-semibold">
        Validation design and evaluator validity
      </h4>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs">
        {Object.entries(validationDesign).map(([key, value]) => (
          <div key={key} className="contents">
            <dt>{key.replaceAll('_', ' ')}</dt>
            <dd>{Array.isArray(value) ? value.join(', ') : String(value)}</dd>
          </div>
        ))}
        <dt>Evaluator</dt>
        <dd>{evaluator.evaluator_id} · {evaluator.version}</dd>
        <dt>Evaluator contract</dt>
        <dd className="break-all">{evaluator.contract_hash}</dd>
      </dl>
    </section>
  );
}
