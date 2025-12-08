/**
 * Resource Binding-related i18n message keys
 * Resource bindings, data source overlay, tool overlay
 */

export const resourceBindingKeys = {
  resourceBindings: true,
  resourceBindingsDescription: true,
  addBinding: true,
  editBinding: true,
  deleteBinding: true,
  resourceType: true,
  resourceId: true,
  overrides: true,
  noResourceBindings: true,
  noResourceBindingsDescription: true,
  deleteResourceBinding: true,
  deleteResourceBindingConfirm: true,

  // Data Source Overlay
  dataSourceOverlaySettings: true,
  dataSourceOverlayDescription: true,
  addDataSource: true,
  noDataSourceBindings: true,
  noDataSourceBindingsDescription: true,
  disableDataSourceBinding: true,
  disableDataSourceBindingConfirm: true,
  availableDataSources: true,
  enableDataSourceInWorkspace: true,

  // Tool Overlay
  toolOverlaySettings: true,
  toolOverlayDescription: true,
  toolWhitelist: true,
  toolWhitelistDescription: true,
  searchTools: true,
  noToolsFound: true,
  allToolsAllowed: true,
  toolsSelected: true,
  dangerLevelOverride: true,
  dangerLevelOverrideDescription: true,
  noOverride: true,
  useOriginal: true,
  overrideWillApply: true,
  cannotSetDangerLevel: true,
  mustBeMoreRestrictive: true,
  enableDisableTools: true,
  enableDisableToolsDescription: true,
  enableToolsInWorkspace: true,
  saveSettings: true,
  toolOverlaySaved: true,
} as const;

