'use client';

import React from 'react';
import { t } from '../../../../lib/i18n';
import {
    DEFAULT_ALLOWED_HOSTS,
    DEFAULT_ALLOWED_PROVIDERS,
    MODEL_PROVIDER_OPTIONS,
    SECRETS_API_OPTIONS,
} from './aiTeamGovernancePanelData';

export function ModelPolicySettings() {
    const [allowedProviders, setAllowedProviders] = React.useState<string[]>([...DEFAULT_ALLOWED_PROVIDERS]);

    const toggleProvider = (id: string) => {
        setAllowedProviders(prev =>
            prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
        );
    };

    const isLocalOnly = allowedProviders.every(p =>
        MODEL_PROVIDER_OPTIONS.find(pr => pr.id === p)?.type === 'local'
    );

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('modelPolicy' as any) || 'Model Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('modelPolicyDescription' as any) || 'Configure the allowlist of model providers available to external agents.'}
                </p>
            </div>

            {isLocalOnly && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                        <span className="text-sm font-medium">Local-only mode is enabled</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        External agents can only use local models and cannot access cloud model APIs.
                    </p>
                </div>
            )}

            <div className="space-y-2">
                <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    Local Model Providers
                </h4>
                {MODEL_PROVIDER_OPTIONS.filter(p => p.type === 'local').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {provider.icon}
                            </span>
                            <span className="text-sm text-gray-900 dark:text-gray-100">{provider.name}</span>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedProviders.includes(provider.id)}
                            onChange={() => toggleProvider(provider.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            <div className="space-y-2">
                <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    Cloud Model Providers
                </h4>
                {MODEL_PROVIDER_OPTIONS.filter(p => p.type === 'cloud').map(provider => (
                    <label
                        key={provider.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {provider.icon}
                            </span>
                            <span className="text-sm text-gray-900 dark:text-gray-100">{provider.name}</span>
                            <span className="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 rounded">
                                Cloud
                            </span>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedProviders.includes(provider.id)}
                            onChange={() => toggleProvider(provider.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}

export function NetworkPolicySettings() {
    const [allowedHosts, setAllowedHosts] = React.useState<string[]>([...DEFAULT_ALLOWED_HOSTS]);
    const [newHost, setNewHost] = React.useState('');

    const addHost = () => {
        if (newHost && !allowedHosts.includes(newHost)) {
            setAllowedHosts([...allowedHosts, newHost]);
            setNewHost('');
        }
    };

    const removeHost = (host: string) => {
        setAllowedHosts(allowedHosts.filter(h => h !== host));
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('networkPolicy' as any) || 'Network Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('networkPolicyDescription' as any) || 'Configure the external network endpoints agents are allowed to access.'}
                </p>
            </div>

            <div className="flex gap-2">
                <input
                    type="text"
                    value={newHost}
                    onChange={(e) => setNewHost(e.target.value)}
                    placeholder="Example: api.example.com"
                    className="flex-1 px-3 py-2 text-sm border dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <button
                    onClick={addHost}
                    className="px-4 py-2 bg-accent text-white rounded-lg hover:bg-accent-hover transition-colors"
                >
                    Add
                </button>
            </div>

            <div className="space-y-2">
                {allowedHosts.map((host) => (
                    <div
                        key={host}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800"
                    >
                        <span className="text-sm text-gray-900 dark:text-gray-100">{host}</span>
                        <button
                            onClick={() => removeHost(host)}
                            className="text-sm text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
                        >
                            Remove
                        </button>
                    </div>
                ))}
            </div>

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}

export function SecretsPolicySettings() {
    const [allowedApis, setAllowedApis] = React.useState<string[]>([]);

    const toggleApi = (id: string) => {
        setAllowedApis(prev =>
            prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
        );
    };

    return (
        <div className="space-y-6">
            <div>
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                    {t('secretsPolicy' as any) || 'Secrets Policy'}
                </h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
                    {t('secretsPolicyDescription' as any) || 'Configure which API endpoints may receive injected credentials.'}
                </p>
            </div>

            <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                <div className="flex items-center gap-2 text-yellow-800 dark:text-yellow-300">
                    <span className="text-sm font-medium">Security Notice</span>
                </div>
                <p className="text-xs text-yellow-700 dark:text-yellow-400 mt-1">
                    Enabled API endpoints allow external agents to use the corresponding API credentials. Choose carefully.
                </p>
            </div>

            <div className="space-y-2">
                {SECRETS_API_OPTIONS.map(api => (
                    <label
                        key={api.id}
                        className="flex items-center justify-between p-3 border dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                        <div className="flex items-center gap-2">
                            <span className="flex h-7 w-7 items-center justify-center rounded bg-gray-100 text-xs font-semibold text-gray-700 dark:bg-gray-700 dark:text-gray-200">
                                {api.icon}
                            </span>
                            <div>
                                <span className="text-sm text-gray-900 dark:text-gray-100">{api.name}</span>
                                <p className="text-xs text-gray-500 dark:text-gray-400">{api.id}</p>
                            </div>
                        </div>
                        <input
                            type="checkbox"
                            checked={allowedApis.includes(api.id)}
                            onChange={() => toggleApi(api.id)}
                            className="rounded border-gray-300 text-accent focus:ring-accent"
                        />
                    </label>
                ))}
            </div>

            {allowedApis.length === 0 && (
                <div className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                    <div className="flex items-center gap-2 text-green-800 dark:text-green-300">
                        <span className="text-sm font-medium">Isolated Mode</span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-400 mt-1">
                        No API credential injection is currently allowed, so external agents cannot access cloud services.
                    </p>
                </div>
            )}

            <div className="pt-4 border-t dark:border-gray-700">
                <button className="px-4 py-2 bg-accent text-white rounded hover:bg-accent-hover transition-colors">
                    Save Settings
                </button>
            </div>
        </div>
    );
}
