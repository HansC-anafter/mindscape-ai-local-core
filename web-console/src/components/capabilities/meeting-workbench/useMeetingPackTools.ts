import { useEffect, useState } from 'react';

import type { MeetingPackTool } from './meetingWorkbenchTypes';
import { isRecord } from './meetingWorkbenchUtils';

interface UseMeetingPackToolsArgs {
  apiUrl: string;
}

export interface MeetingPackToolsState {
  packTools: MeetingPackTool[];
  packToolsLoading: boolean;
  packToolsError: string | null;
}

export function useMeetingPackTools({ apiUrl }: UseMeetingPackToolsArgs): MeetingPackToolsState {
  const [packTools, setPackTools] = useState<MeetingPackTool[]>([]);
  const [packToolsLoading, setPackToolsLoading] = useState(false);
  const [packToolsError, setPackToolsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchPackTools() {
      setPackToolsLoading(true);
      setPackToolsError(null);

      try {
        const query = 'scope=all&target_language=zh-TW&profile_id=default-user';
        const sameOriginUrl = `/api/v1/playbooks/?${query}`;
        const primaryUrl = `${apiUrl}/api/v1/playbooks/?${query}`;
        const urls = primaryUrl === sameOriginUrl ? [sameOriginUrl] : [primaryUrl, sameOriginUrl];
        let data: unknown = null;
        let lastError: unknown = null;

        for (const url of urls) {
          try {
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(`Failed to fetch playbooks: ${response.status}`);
            }
            data = await response.json();
            lastError = null;
            break;
          } catch (error) {
            lastError = error;
          }
        }

        if (lastError) {
          throw lastError;
        }

        if (cancelled) {
          return;
        }

        const playbooks = Array.isArray(data) ? data.filter(isRecord) : [];
        const mappedTools = playbooks
          .map((playbook): MeetingPackTool | null => {
            const id = typeof playbook.playbook_code === 'string' ? playbook.playbook_code : '';
            if (!id) {
              return null;
            }

            const requiredTools = Array.isArray(playbook.required_tools)
              ? playbook.required_tools.filter((tool): tool is string => typeof tool === 'string')
              : [];
            const capabilityCode =
              typeof playbook.capability_code === 'string' && playbook.capability_code.trim()
                ? playbook.capability_code
                : null;

            return {
              id,
              label: typeof playbook.name === 'string' && playbook.name.trim() ? playbook.name : id,
              description:
                typeof playbook.description === 'string' && playbook.description.trim()
                  ? playbook.description
                  : 'Workspace playbook tool',
              capabilityCode,
              requiredTools,
            };
          })
          .filter((tool): tool is MeetingPackTool => Boolean(tool))
          .filter((tool) => Boolean(tool.capabilityCode) || tool.requiredTools.length > 0)
          .slice(0, 40);

        setPackTools(mappedTools);
      } catch (error) {
        if (!cancelled) {
          setPackTools([]);
          setPackToolsError(error instanceof Error ? error.message : 'Failed to load pack tools.');
        }
      } finally {
        if (!cancelled) {
          setPackToolsLoading(false);
        }
      }
    }

    void fetchPackTools();

    return () => {
      cancelled = true;
    };
  }, [apiUrl]);

  return {
    packTools,
    packToolsLoading,
    packToolsError,
  };
}
