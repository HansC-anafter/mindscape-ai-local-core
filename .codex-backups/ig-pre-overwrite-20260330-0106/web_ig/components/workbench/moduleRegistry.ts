import {
  BarChart3,
  BookOpen,
  Briefcase,
  CheckSquare,
  Download,
  FolderOpen,
  KeyRound,
  MessageSquare,
  Pin,
  Sparkles,
  Upload,
  Users,
} from 'lucide-react';

import type { WorkbenchModuleType } from './types';

export interface WorkbenchModuleDef {
  id: WorkbenchModuleType;
  label: string;
  icon: any;
  color: string;
}

export const WORKBENCH_MODULES: WorkbenchModuleDef[] = [
  { id: 'discovery', label: 'Discovery', icon: Users, color: 'blue' },
  { id: 'references', label: 'References', icon: Pin, color: 'rose' },
  { id: 'managed', label: 'Managed', icon: Briefcase, color: 'emerald' },
  { id: 'plan', label: 'Plan', icon: BookOpen, color: 'purple' },
  { id: 'produce', label: 'Produce', icon: Sparkles, color: 'green' },
  { id: 'assets', label: 'Assets', icon: FolderOpen, color: 'orange' },
  { id: 'review', label: 'Review', icon: CheckSquare, color: 'yellow' },
  { id: 'export', label: 'Export', icon: Download, color: 'blue' },
  { id: 'publish', label: 'Publish', icon: Upload, color: 'red' },
  { id: 'measure', label: 'Measure', icon: BarChart3, color: 'indigo' },
  { id: 'engage', label: 'Engage', icon: MessageSquare, color: 'pink' },
  { id: 'access', label: 'Access', icon: KeyRound, color: 'violet' },
];
