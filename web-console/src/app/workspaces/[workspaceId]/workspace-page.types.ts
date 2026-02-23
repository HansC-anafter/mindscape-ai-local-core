import { WorkspaceMode } from '../../../components/WorkspaceModeSelector';

export interface DataSource {
    local_folder?: string;
    obsidian_vault?: string;
    wordpress?: string;
    rag_source?: string;
}

export interface AssociatedIntent {
    id: string;
    title: string;
    tags?: string[];
    status?: string;
    priority?: string;
}

export type ExecutionMode = 'qa' | 'execution' | 'hybrid' | 'meeting' | null;
export type ExecutionPriority = 'low' | 'medium' | 'high' | null;

export interface Workspace {
    id: string;
    title: string;
    description?: string;
    primary_project_id?: string;
    default_playbook_id?: string;
    default_locale?: string;
    mode?: WorkspaceMode;
    execution_mode?: ExecutionMode;
    expected_artifacts?: string[];
    execution_priority?: ExecutionPriority;
    data_sources?: DataSource | null;
    associated_intent?: AssociatedIntent | null;
    storage_base_path?: string;
    artifacts_dir?: string;
    storage_config?: any;
    playbook_storage_config?: Record<string, { base_path?: string; artifacts_dir?: string }>;
}
