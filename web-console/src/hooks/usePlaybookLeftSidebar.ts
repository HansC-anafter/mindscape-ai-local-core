/**
 * usePlaybookLeftSidebar - Hook to get left sidebar config for a playbook
 *
 * Returns left sidebar configuration from registered playbook package.
 */

import { useState, useEffect } from 'react';
import { getPlaybookRegistry } from '@/playbook';

interface LeftSidebarConfig {
  type: string;
  component: string;
  config: Record<string, any>;
}

export function usePlaybookLeftSidebar(playbookCode: string | null) {
  const [config, setConfig] = useState<LeftSidebarConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!playbookCode) {
      setConfig(null);
      setLoading(false);
      return;
    }

    const registry = getPlaybookRegistry();
    const playbook = registry.get(playbookCode);

    if (playbook?.uiLayout?.left_sidebar) {
      setConfig(playbook.uiLayout.left_sidebar);
    } else {
      setConfig(null);
    }

    setLoading(false);
  }, [playbookCode]);

  return { config, loading };
}

