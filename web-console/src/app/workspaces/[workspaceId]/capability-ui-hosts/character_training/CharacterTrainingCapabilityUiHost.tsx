'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as CharacterTrainingCandidateWorkbenchPageModule0 from '@/app/capabilities/character_training/components/CharacterTrainingCandidateWorkbenchPage';
import * as CharacterTrainingRegistryWorkbenchPageModule1 from '@/app/capabilities/character_training/components/CharacterTrainingRegistryWorkbenchPage';
import * as CharacterTrainingReviewWorkbenchPageModule2 from '@/app/capabilities/character_training/components/CharacterTrainingReviewWorkbenchPage';

const componentModules: Record<string, Record<string, unknown>> = {
  "CharacterTrainingCandidateWorkbenchPage": CharacterTrainingCandidateWorkbenchPageModule0 as Record<string, unknown>,
  "CharacterTrainingRegistryWorkbenchPage": CharacterTrainingRegistryWorkbenchPageModule1 as Record<string, unknown>,
  "CharacterTrainingReviewWorkbenchPage": CharacterTrainingReviewWorkbenchPageModule2 as Record<string, unknown>,
};

export default function CharacterTrainingCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
