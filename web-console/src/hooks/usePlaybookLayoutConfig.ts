/**
 * usePlaybookLayoutConfig - Hook to get UI layout config for a playbook
 *
 * Loads UI layout configuration from registered playbook package.
 */

import { useState, useEffect } from 'react';
import { getPlaybookRegistry, UILayoutConfig } from '@/playbook';

interface PlaybookLayoutConfig {
  playbook_code: string;
  version: string;
  ui_layout: UILayoutConfig;
}

export function usePlaybookLayoutConfig(playbookCode: string | null) {
  const [config, setConfig] = useState<PlaybookLayoutConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!playbookCode) {
      setConfig(null);
      setLoading(false);
      return;
    }

    const registry = getPlaybookRegistry();
    const playbook = registry.get(playbookCode);

    if (playbook && playbook.uiLayout) {
      setConfig({
        playbook_code: playbookCode,
        version: playbook.version,
        ui_layout: playbook.uiLayout
      });
    } else {
      setConfig(getDefaultLayout(playbookCode));
    }

    setLoading(false);
  }, [playbookCode]);

  return { config, loading };
}

function getDefaultLayout(playbookCode: string): PlaybookLayoutConfig {
  return {
    playbook_code: playbookCode,
    version: '1.0',
    ui_layout: {
      type: 'default',
      main_surface: {
        layout: 'single_column',
        components: []
      }
    }
  };
}

