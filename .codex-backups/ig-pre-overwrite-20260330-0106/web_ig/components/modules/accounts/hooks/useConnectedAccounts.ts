import { useCallback, useEffect, useMemo, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { ConnectedAccount } from '../types';
import { fetchSiteHubInstagramChannels } from '../api';

export function useConnectedAccounts(params: { apiUrl: string; workspaceId: string }) {
  const { apiUrl, workspaceId } = params;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount[]>([]);

  const refresh = useCallback(async () => {
    try {
      const response = await fetchSiteHubInstagramChannels(client, workspaceId);
      if (!response.ok) {
        setConnectedAccounts([]);
        return;
      }

      const data = await response.json();
      // channel-bindings API returns { bindings: [...] }
      const igBindings = (data.bindings || []).filter(
        (b: any) => b.channel_type === 'instagram'
      );
      const accounts: ConnectedAccount[] = igBindings.map((binding: any) => ({
        channel_config_id: binding.channel_id || binding.id,
        channel_name: binding.channel_name || binding.channel_id || `Channel ${binding.id}`,
        channel_type: 'instagram',
        status: binding.status === 'active' ? 'connected' : 'expired',
        expires_at: undefined,
        permissions: [],
        reauth_url: undefined,
        page_id: undefined,
        username: binding.channel_name,
      }));

      setConnectedAccounts(accounts);
    } catch {
      setConnectedAccounts([]);
    }
  }, [client, workspaceId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Always enabled: channel-bindings is a local-core API
  return { connectedAccounts, refresh, enabled: true };
}

