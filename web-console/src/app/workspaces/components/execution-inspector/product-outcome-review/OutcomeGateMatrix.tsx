import type { GateResult } from './types';

export function OutcomeGateMatrix({ gates }: { gates: GateResult[] }) {
  return (
    <section aria-labelledby="outcome-gates-heading">
      <h4 id="outcome-gates-heading" className="text-sm font-semibold">
        Outcome gate matrix
      </h4>
      {gates.length === 0 ? (
        <p className="mt-2 text-xs text-gray-500">
          No signed evaluation is available.
        </p>
      ) : (
        <table className="mt-2 w-full text-left text-xs">
          <thead><tr><th>Gate</th><th>Status</th><th>Evidence</th></tr></thead>
          <tbody>
            {gates.map((gate) => (
              <tr key={gate.gate_id}>
                <td>{gate.gate_id}</td>
                <td>{gate.status}</td>
                <td className="break-all">{gate.evidence_hash}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
