import React from 'react';

import type { ConnectedAccount } from '../types';

export function ConnectedAccountsCard(props: {
  accounts: ConnectedAccount[];
}) {
  const { accounts } = props;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Connected accounts</h3>
      </div>
      {accounts.length === 0 ? (
        <div className="text-sm text-gray-500 dark:text-gray-400">
          No connected accounts in this environment.
        </div>
      ) : (
        <div className="space-y-2">
          {accounts.map((account) => (
            <div
              key={account.channel_config_id}
              className="p-3 bg-gray-50 dark:bg-gray-900/30 rounded border border-gray-200 dark:border-gray-700"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{account.channel_name}</div>
                  {account.username && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">@{account.username}</div>
                  )}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{account.status}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

