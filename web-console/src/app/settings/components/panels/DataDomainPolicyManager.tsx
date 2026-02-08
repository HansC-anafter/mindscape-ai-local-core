'use client';

import React, { useState } from 'react';
import { t } from '../../../../lib/i18n';

interface DataDomainPolicyManagerProps {
  dataDomainPolicies: {
    sensitive_domains: string[];
    pii_handling_enabled: boolean;
    forbidden_domains: string[];
  };
  onChange: (policies: {
    sensitive_domains: string[];
    pii_handling_enabled: boolean;
    forbidden_domains: string[];
  }) => void;
}

export function DataDomainPolicyManager({
  dataDomainPolicies,
  onChange,
}: DataDomainPolicyManagerProps) {
  const [newSensitiveDomain, setNewSensitiveDomain] = useState('');
  const [newForbiddenDomain, setNewForbiddenDomain] = useState('');

  const handleAddSensitiveDomain = () => {
    if (newSensitiveDomain.trim() && !dataDomainPolicies.sensitive_domains.includes(newSensitiveDomain.trim())) {
      onChange({
        ...dataDomainPolicies,
        sensitive_domains: [...dataDomainPolicies.sensitive_domains, newSensitiveDomain.trim()],
      });
      setNewSensitiveDomain('');
    }
  };

  const handleRemoveSensitiveDomain = (domain: string) => {
    onChange({
      ...dataDomainPolicies,
      sensitive_domains: dataDomainPolicies.sensitive_domains.filter((d) => d !== domain),
    });
  };

  const handleAddForbiddenDomain = () => {
    if (newForbiddenDomain.trim() && !dataDomainPolicies.forbidden_domains.includes(newForbiddenDomain.trim())) {
      onChange({
        ...dataDomainPolicies,
        forbidden_domains: [...dataDomainPolicies.forbidden_domains, newForbiddenDomain.trim()],
      });
      setNewForbiddenDomain('');
    }
  };

  const handleRemoveForbiddenDomain = (domain: string) => {
    onChange({
      ...dataDomainPolicies,
      forbidden_domains: dataDomainPolicies.forbidden_domains.filter((d) => d !== domain),
    });
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-4">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {t('dataDomainPolicies' as any)}
        </h4>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {t('dataDomainPoliciesDescription' as any)}
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t('sensitiveDomains' as any)}
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={newSensitiveDomain}
              onChange={(e) => setNewSensitiveDomain(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAddSensitiveDomain()}
              placeholder={t('enterDomainName' as any)}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={handleAddSensitiveDomain}
              className="px-3 py-2 text-sm bg-yellow-600 dark:bg-yellow-700 text-white rounded hover:bg-yellow-700 dark:hover:bg-yellow-600 transition-colors"
            >
              {t('add' as any)}
            </button>
          </div>
          {dataDomainPolicies.sensitive_domains.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {dataDomainPolicies.sensitive_domains.map((domain) => (
                <span
                  key={domain}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 rounded text-xs"
                >
                  {domain}
                  <button
                    type="button"
                    onClick={() => handleRemoveSensitiveDomain(domain)}
                    className="hover:text-yellow-900 dark:hover:text-yellow-100"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400 italic">
              {t('noSensitiveDomains' as any)}
            </p>
          )}
        </div>

        <div>
          <div className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
            {t('forbiddenDomains' as any)}
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={newForbiddenDomain}
              onChange={(e) => setNewForbiddenDomain(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAddForbiddenDomain()}
              placeholder={t('enterDomainName' as any)}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            />
            <button
              type="button"
              onClick={handleAddForbiddenDomain}
              className="px-3 py-2 text-sm bg-red-600 dark:bg-red-700 text-white rounded hover:bg-red-700 dark:hover:bg-red-600 transition-colors"
            >
              {t('add' as any)}
            </button>
          </div>
          {dataDomainPolicies.forbidden_domains.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {dataDomainPolicies.forbidden_domains.map((domain) => (
                <span
                  key={domain}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 rounded text-xs"
                >
                  {domain}
                  <button
                    type="button"
                    onClick={() => handleRemoveForbiddenDomain(domain)}
                    className="hover:text-red-900 dark:hover:text-red-100"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400 italic">
              {t('noForbiddenDomains' as any)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

