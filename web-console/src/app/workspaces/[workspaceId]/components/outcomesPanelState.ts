import { parseServerTimestamp } from '@/lib/time';

import type {
  Artifact,
  ArtifactDisplayInfo,
  MatchingCapabilityComponent,
  SandboxOpenTarget,
} from './outcomesPanelTypes';

export const getArtifactIcon = (artifactType: string): string => {
  const iconMap: Record<string, string> = {
    checklist: 'LIST',
    draft: 'DOC',
    config: 'CFG',
    canva: 'CAN',
    audio: 'AUD',
    docx: 'DOCX',
  };
  return iconMap[artifactType] || 'ITEM';
};

export const artifactsMatchComponent = (artifacts: Artifact[], component: any): boolean => {
  if (!artifacts || artifacts.length === 0) {
    return false;
  }

  if (
    typeof component?.code === 'string' &&
    (
      component.code.endsWith('Page') ||
      component.code.endsWith('StudioPage') ||
      component.code.endsWith('Workbench')
    )
  ) {
    return false;
  }

  if (Array.isArray(component.artifact_types) && component.artifact_types.length > 0) {
    return artifacts.some((artifact) =>
      component.artifact_types.includes(artifact.artifact_type)
    );
  }

  if (Array.isArray(component.playbook_codes) && component.playbook_codes.length > 0) {
    return artifacts.some((artifact) =>
      component.playbook_codes.includes(artifact.playbook_code)
    );
  }

  return false;
};

export const collectMatchingComponents = (
  artifacts: Artifact[],
  installedCapabilities: any[],
): MatchingCapabilityComponent[] => {
  const nextMatchingComponents: MatchingCapabilityComponent[] = [];
  for (const capability of installedCapabilities) {
    if (capability.ui_components && capability.ui_components.length > 0) {
      for (const componentInfo of capability.ui_components) {
        if (artifactsMatchComponent(artifacts, componentInfo)) {
          nextMatchingComponents.push({
            key: `${capability.code}:${componentInfo.code}`,
            capabilityCode: capability.code,
            componentCode: componentInfo.code,
            description: componentInfo.description,
          });
        }
      }
    }
  }
  return nextMatchingComponents;
};

const isRecord = (value: unknown): value is Record<string, any> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const resolveArtifactDisplayInfo = (artifact: Artifact): ArtifactDisplayInfo => {
  const content = isRecord(artifact.content) ? artifact.content : null;
  const metadata = isRecord(artifact.metadata) ? artifact.metadata : null;
  const filePath = (artifact as any).file_path ||
    artifact.storage_ref ||
    (content ? (content.file_path || content.file_name) : null) ||
    null;
  const fileName = content && content.file_name ? content.file_name : artifact.title;
  const executionId = (artifact as any).execution_id ||
    (metadata && (metadata.execution_id || metadata.navigate_to)) ||
    null;
  const createdDate = parseServerTimestamp(artifact.created_at);
  const formattedDate = createdDate ? createdDate.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }) : '';

  return {
    filePath,
    fileName,
    executionId,
    formattedDate,
  };
};

export const resolveSandboxOpenTarget = (
  artifact: Artifact,
  executionId: string | null,
): SandboxOpenTarget | null => {
  const metadata = isRecord(artifact.metadata) ? artifact.metadata : null;
  const actualFilePath = (artifact as any).file_path || (metadata && metadata.actual_file_path);
  const execId = executionId || (metadata && metadata.execution_id);

  if (!actualFilePath || !execId) {
    return null;
  }

  const sandboxMatch = String(actualFilePath).match(/project_repo\/([^/]+)\/current\/(.+)$/);
  if (sandboxMatch) {
    return {
      sandboxId: sandboxMatch[1],
      relativeFilePath: sandboxMatch[2],
      executionId: String(execId),
    };
  }

  const fallbackMatch = String(actualFilePath).match(/sandboxes\/[^/]+\/[^/]+\/([^/]+)\/current\/(.+)$/);
  if (fallbackMatch) {
    return {
      sandboxId: fallbackMatch[1],
      relativeFilePath: fallbackMatch[2],
      executionId: String(execId),
    };
  }

  return null;
};

export const extractSandboxIdFromPath = (filePath: string | null): string | null => {
  if (!filePath) {
    return null;
  }
  const sandboxMatch = filePath.match(/sandboxes\/([^/]+)/);
  return sandboxMatch ? sandboxMatch[1] : null;
};
