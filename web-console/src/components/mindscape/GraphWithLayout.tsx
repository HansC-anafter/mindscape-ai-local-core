'use client';

import React, { useEffect } from 'react';
import { useWorkerLayoutForceAtlas2 } from '@react-sigma/layout-forceatlas2';

interface ForceAtlas2LayoutProps {
  autoStart?: boolean;
  duration?: number;
}

export function ForceAtlas2Layout({ autoStart = true, duration = 5000 }: ForceAtlas2LayoutProps) {
  const { start, stop, isRunning } = useWorkerLayoutForceAtlas2({
    settings: {
      gravity: 0.05, // Very low gravity to allow nodes to spread out naturally
      scalingRatio: 30, // Moderate scaling for good spacing without being too aggressive
      strongGravityMode: false, // Disable strong gravity
      slowDown: 1, // Fast convergence
      barnesHutOptimize: true,
      barnesHutTheta: 0.5,
    },
  });

  useEffect(() => {
    if (autoStart && start) {
      start();
      const timeout = setTimeout(() => {
        if (stop) stop();
      }, duration);
      return () => {
        clearTimeout(timeout);
        if (stop) stop();
      };
    }
  }, [start, stop, autoStart, duration]);

  return null;
}


