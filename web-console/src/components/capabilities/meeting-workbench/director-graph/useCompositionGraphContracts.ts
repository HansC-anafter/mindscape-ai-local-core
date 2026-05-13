import { useEffect, useMemo, useState } from 'react';

import {
  fetchCompositionGraphContracts,
  type CompositionGraphContract,
  type CompositionGraphDiagnostic,
  type CompositionGraphNodeType,
} from '@/lib/composition-graph';

export function getCoreObjectReferenceNodeType(): CompositionGraphNodeType {
  return {
    id: 'object_reference',
    label: 'Object Reference',
    source: 'core',
    category: 'context',
    description: 'Generic reference to a canonical Addressable Object.',
    output_ports: [
      {
        id: 'object',
        direction: 'output',
        label: 'Object',
        data_type: 'object_ref',
      },
    ],
    payload_schema: {
      type: 'object',
      required: ['ref'],
      properties: {
        ref: {
          type: 'object',
          required: ['uri', 'owner_pack', 'object_kind', 'object_id'],
          properties: {
            uri: { type: 'string' },
            owner_pack: { type: 'string' },
            object_kind: { type: 'string' },
            object_id: { type: 'string' },
            workspace_id: { type: 'string' },
          },
          additionalProperties: true,
        },
      },
      additionalProperties: true,
    },
  };
}

export function useCompositionGraphContracts({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const [contracts, setContracts] = useState<CompositionGraphContract[]>([]);
  const [diagnostics, setDiagnostics] = useState<CompositionGraphDiagnostic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchCompositionGraphContracts(apiUrl, workspaceId)
      .then((response) => {
        if (cancelled) {
          return;
        }
        setContracts(response.contracts || []);
        setDiagnostics(response.diagnostics || []);
      })
      .catch((cause) => {
        if (cancelled) {
          return;
        }
        setError(cause instanceof Error ? cause.message : 'Failed to load composition graph contracts.');
        setContracts([]);
        setDiagnostics([]);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [apiUrl, workspaceId]);

  const nodeTypes = useMemo(
    () => [
      getCoreObjectReferenceNodeType(),
      ...contracts.flatMap((contract) => contract.node_types || []),
    ],
    [contracts],
  );

  return {
    contracts,
    diagnostics,
    error,
    loading,
    nodeTypes,
  };
}
