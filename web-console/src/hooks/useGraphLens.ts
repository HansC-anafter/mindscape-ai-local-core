import { useSigma } from '@react-sigma/core';
import { useCallback } from 'react';
import { TYPE_COLORS } from '@/lib/mock-graph-data';

export function useGraphLens() {
  const sigma = useSigma();

  const applyLens = useCallback((lens: 'all' | 'direction' | 'action') => {
    const graph = sigma.getGraph();

    graph.forEachNode((nodeId, attributes) => {
      const isMatch = lens === 'all' || attributes.category === lens;

      graph.setNodeAttribute(nodeId, 'color',
        isMatch ? TYPE_COLORS[attributes.nodeType] : '#d1d5db'
      );
      graph.setNodeAttribute(nodeId, 'size',
        isMatch ? (attributes.originalSize || 15) : 8
      );
      graph.setNodeAttribute(nodeId, 'zIndex',
        isMatch ? 1 : 0
      );
    });

    graph.forEachEdge((edgeId, attributes, source, target) => {
      const sourceMatch = lens === 'all' || graph.getNodeAttribute(source, 'category') === lens;
      const targetMatch = lens === 'all' || graph.getNodeAttribute(target, 'category') === lens;
      const isMatch = sourceMatch && targetMatch;

      graph.setEdgeAttribute(edgeId, 'color',
        isMatch ? 'rgba(99, 102, 241, 0.6)' : 'rgba(226, 232, 240, 0.2)'
      );
    });

    sigma.refresh();
  }, [sigma]);

  return { applyLens };
}

