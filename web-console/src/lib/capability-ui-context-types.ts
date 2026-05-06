export type CapabilityComponentModule = Record<string, any>;

export type CapabilityComponentModuleLoad =
  | CapabilityComponentModule
  | Promise<CapabilityComponentModule>
  | (() => Promise<CapabilityComponentModule>);

export interface CapabilityComponentsContext {
  (key: string): CapabilityComponentModuleLoad;
  keys: () => string[];
  resolve?: (request: string) => string;
  id?: string;
}
