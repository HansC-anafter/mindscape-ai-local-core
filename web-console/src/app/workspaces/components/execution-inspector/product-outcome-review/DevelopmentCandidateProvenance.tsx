import type { ProductArm } from './types';

export function DevelopmentCandidateProvenance({
  arms,
}: {
  arms: ProductArm[];
}) {
  return (
    <section aria-labelledby="candidate-provenance-heading">
      <h4 id="candidate-provenance-heading" className="text-sm font-semibold">
        Development candidate provenance
      </h4>
      <div className="mt-2 space-y-2">
        {arms.map((arm) => (
          <dl
            key={arm.arm_id}
            className="grid grid-cols-2 gap-1 rounded border p-2 text-xs"
          >
            <dt>Arm</dt><dd>{arm.arm_id}</dd>
            <dt>Capability</dt>
            <dd>{arm.capability_identity.capability_code}</dd>
            <dt>Pack version</dt>
            <dd>{arm.capability_identity.pack_version}</dd>
            <dt>Attestation</dt>
            <dd className="break-all">{arm.development_attestation_id}</dd>
            <dt>Attestation hash</dt>
            <dd className="break-all">
              {arm.development_attestation_sha256}
            </dd>
            <dt>Compatibility</dt>
            <dd>{arm.consumer_compatibility_class}</dd>
            <dt>Configuration</dt>
            <dd className="break-all">{arm.configuration_fingerprint}</dd>
            <dt>Environment</dt>
            <dd className="break-all">{arm.environment_fingerprint}</dd>
            <dt>Data</dt>
            <dd className="break-all">{arm.data_fingerprint}</dd>
          </dl>
        ))}
      </div>
    </section>
  );
}
