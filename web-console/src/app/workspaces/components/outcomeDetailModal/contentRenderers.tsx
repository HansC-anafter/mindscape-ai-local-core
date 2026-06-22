import Image from 'next/image';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { markdownComponents } from './markdownComponents';
import type { Artifact } from './types';

interface OutcomeContentProps {
  activeArtifact: Artifact;
  detailLoading: boolean;
  onOpenExternal: () => void | Promise<void>;
}

const renderDraftContent = (activeArtifact: Artifact) => {
  const content = activeArtifact.content?.content || activeArtifact.summary || '';
  return (
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
};

const renderChecklistContent = (activeArtifact: Artifact) => {
  const tasks = activeArtifact.content?.tasks || [];
  return (
    <div className="space-y-2">
      <h3 className="text-lg font-semibold mb-4 dark:text-gray-100">Task List</h3>
      {tasks.length === 0 ? (
        <p className="text-gray-500 dark:text-gray-400">No tasks yet</p>
      ) : (
        <div className="space-y-2">
          {tasks.map((task: any, index: number) => (
            <div key={task.id || index} className="flex items-start gap-2 p-2 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800">
              <input
                type="checkbox"
                checked={task.completed || false}
                readOnly
                className="mt-1"
              />
              <div className="flex-1">
                <div className="font-medium dark:text-gray-100">{task.title}</div>
                {task.description && (
                  <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">{task.description}</div>
                )}
                {task.priority && (
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
                    {task.priority}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const renderConfigContent = (activeArtifact: Artifact) => (
  <div className="space-y-2">
    <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded overflow-x-auto text-xs text-gray-900 dark:text-gray-100">
      {JSON.stringify(activeArtifact.content, null, 2)}
    </pre>
  </div>
);

const renderCanvaContent = (
  activeArtifact: Artifact,
  onOpenExternal: OutcomeContentProps['onOpenExternal']
) => {
  const canvaUrl = activeArtifact.content?.canva_url || activeArtifact.storage_ref;
  const thumbnailUrl = activeArtifact.content?.thumbnail_url;
  return (
    <div className="space-y-4">
      {thumbnailUrl && (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
          <Image
            src={thumbnailUrl}
            alt={activeArtifact.title}
            width={960}
            height={540}
            className="w-full h-auto"
            unoptimized
          />
        </div>
      )}
      {canvaUrl && (
        <button
          onClick={onOpenExternal}
          className="px-4 py-2 bg-green-600 dark:bg-green-700 text-white rounded hover:bg-green-700 dark:hover:bg-green-600 transition-colors"
        >
          Open in Canva
        </button>
      )}
    </div>
  );
};

const renderAudioContent = (activeArtifact: Artifact) => {
  const audioPath = activeArtifact.content?.audio_file_path || activeArtifact.storage_ref;
  const transcript = activeArtifact.content?.transcript;
  return (
    <div className="space-y-4">
      {audioPath && (
        <div>
          <audio controls className="w-full">
            <source src={audioPath} type="audio/mpeg" />
            <source src={audioPath} type="audio/wav" />
            Your browser does not support audio playback.
          </audio>
        </div>
      )}
      {transcript && (
        <div className="mt-4">
          <h3 className="text-lg font-semibold mb-2 dark:text-gray-100">Transcript</h3>
          <div className="bg-gray-50 dark:bg-gray-800 p-4 rounded border border-gray-200 dark:border-gray-700">
            <p className="whitespace-pre-wrap text-sm dark:text-gray-300">{transcript}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export function OutcomeContent({
  activeArtifact,
  detailLoading,
  onOpenExternal,
}: OutcomeContentProps) {
  if (detailLoading && !activeArtifact.content) {
    return <div className="text-sm text-gray-500 dark:text-gray-400">Loading outcome content...</div>;
  }

  switch (activeArtifact.artifact_type) {
    case 'draft':
      return renderDraftContent(activeArtifact);
    case 'checklist':
      return renderChecklistContent(activeArtifact);
    case 'config':
      return renderConfigContent(activeArtifact);
    case 'canva':
      return renderCanvaContent(activeArtifact, onOpenExternal);
    case 'audio':
      return renderAudioContent(activeArtifact);
    default:
      return renderConfigContent(activeArtifact);
  }
}
