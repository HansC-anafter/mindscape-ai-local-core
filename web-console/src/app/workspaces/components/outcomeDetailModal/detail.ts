import type { Artifact } from './types';

export interface ArtifactDetail extends Partial<Artifact> {
  description?: string;
  file_path?: string;
}

export const mergeArtifactDetail = (base: Artifact, detail: ArtifactDetail): Artifact => ({
  ...base,
  ...detail,
  summary: detail.summary ?? detail.description ?? base.summary,
  storage_ref: detail.storage_ref ?? detail.file_path ?? base.storage_ref,
  primary_action_type: detail.primary_action_type ?? base.primary_action_type,
  metadata: detail.metadata ?? base.metadata ?? {},
  content: detail.content ?? base.content,
});
