import type { DeviceNodeStatus } from './types';

interface LocalContentHeaderProps {
    status: DeviceNodeStatus;
}

export function LocalContentHeader({ status }: LocalContentHeaderProps) {
    return (
        <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">本機內容存取</h1>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        管理 Device Node 可存取的檔案、記事本和檔案類型
                    </p>
                </div>
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${status.connected
                    ? 'bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400'
                    : 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400'
                    }`}>
                    <span className={`w-2 h-2 rounded-full ${status.connected ? 'bg-green-500' : 'bg-red-500'}`} />
                    {status.connected ? 'Device Node 已連線' : 'Device Node 未連線'}
                </div>
            </div>
        </div>
    );
}
