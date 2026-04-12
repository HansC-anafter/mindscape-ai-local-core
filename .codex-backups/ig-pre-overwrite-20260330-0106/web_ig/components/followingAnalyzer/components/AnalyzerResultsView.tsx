import React from 'react';

import type { AnalysisResult } from '../types';

export function AnalyzerResultsView(props: {
  result: AnalysisResult;
  onExportCSV: () => void;
}) {
  const { result, onExportCSV } = props;

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="space-y-6">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-semibold">Analysis Results</h3>
          <button
            onClick={onExportCSV}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            Export CSV
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl font-bold">{result.summary.total_accounts}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Total Accounts</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl font-bold">{result.summary.verified_accounts}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Verified</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl font-bold">{result.summary.accounts_with_bio}</div>
            <div className="text-sm text-gray-600 dark:text-gray-400">With Bio</div>
          </div>
          <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl font-bold">
              {result.summary.accounts_with_page_stats}
            </div>
            <div className="text-sm text-gray-600 dark:text-gray-400">Page Stats</div>
          </div>
        </div>

        <div className="border rounded-lg overflow-hidden">
          <div className="overflow-x-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 dark:bg-gray-800 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left">Username</th>
                  <th className="px-4 py-2 text-left">Display Name</th>
                  <th className="px-4 py-2 text-left">Bio</th>
                  <th className="px-4 py-2 text-center">Verified</th>
                  <th className="px-4 py-2 text-left">Stats</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {result.accounts.map((account, index) => (
                  <tr key={index} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-4 py-2">
                      <a
                        href={account.account_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        {account.username}
                      </a>
                    </td>
                    <td className="px-4 py-2">{account.display_name}</td>
                    <td className="px-4 py-2 max-w-xs truncate">{account.bio || '-'}</td>
                    <td className="px-4 py-2 text-center">
                      {account.is_verified ? 'Verified' : '-'}
                    </td>
                    <td className="px-4 py-2">
                      {account.follower_count_text && (
                        <div className="text-xs">
                          {account.follower_count_text} • {account.following_count_text} •{' '}
                          {account.post_count_text}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

