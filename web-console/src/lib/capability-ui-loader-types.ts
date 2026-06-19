export interface UIComponentInfo {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
  asset_url?: string;
  integrity?: string;
  runtime?: string;
  legacy_context?: boolean;
  bytes?: number;
  asset_path?: string;
}
