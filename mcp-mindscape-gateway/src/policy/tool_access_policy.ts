/**
 * ToolAccessPolicy - Governance routing rules
 *
 * Defines which tools are allowed as primitive, which must be governed,
 * and which are internal-only.
 */
export type AccessLevel = "primitive" | "governed" | "internal";

export interface ToolAccessRule {
  pattern: string | RegExp;
  level: AccessLevel;
  reason?: string;
  requiresConfirmation?: boolean;
  requiresPreview?: boolean;
  maxCallsPerMinute?: number;
}

export interface AccessDecision {
  allowed: boolean;
  level: AccessLevel;
  reason: string;
  constraints?: {
    requiresConfirmation?: boolean;
    requiresPreview?: boolean;
    maxCallsPerMinute?: number;
  };
}

export class ToolAccessPolicy {
  private rules: ToolAccessRule[] = [];

  constructor() {
    this.initDefaultRules();
  }

  private initDefaultRules(): void {
    this.rules = [
      // ============================================
      // Internal-only system tools
      // ============================================
      {
        pattern: /^mindscape_(tool|run)_system_/,
        level: "internal",
        reason: "System tools are internal only"
      },
      {
        pattern: /^mindscape_(tool|run)_\w+_(migrate|debug|admin)/,
        level: "internal",
        reason: "Migration/debug/admin tools are internal only"
      },
      {
        pattern: /^mindscape_(tool|run)_\w+_internal_/,
        level: "internal",
        reason: "Tools prefixed with internal_ are not exposed"
      },

      // ============================================
      // High-risk operations requiring governance
      // ============================================
      {
        pattern: /^mindscape_(tool|run)_\w+_(delete|remove|drop|truncate)/,
        level: "governed",
        reason: "Delete operations require confirmation",
        requiresConfirmation: true,
        requiresPreview: true
      },
      {
        pattern: /^mindscape_(tool|run)_\w+_(update|modify|replace|overwrite)/,
        level: "governed",
        reason: "Mutating operations require confirmation",
        requiresConfirmation: true,
        requiresPreview: true
      },
      {
        pattern: /^mindscape_(tool|run)_\w+_(publish|deploy|release)/,
        level: "governed",
        reason: "Publishing operations require confirmation",
        requiresConfirmation: true
      },
      {
        pattern: /^mindscape_(tool|run)_\w+_(batch_|bulk_)/,
        level: "governed",
        reason: "Batch operations require confirmation",
        requiresConfirmation: true,
        requiresPreview: true
      },
      {
        pattern: /^mindscape_(tool|run)_creative_/,
        level: "governed",
        reason: "Creative tools affect local files",
        requiresConfirmation: true
      },

      // ============================================
      // Low-risk read-only operations (primitive)
      // ============================================
      {
        pattern: /^mindscape_tool_\w+_(get|list|read|fetch|query|search|check|validate)/,
        level: "primitive",
        reason: "Read-only operations are safe"
      },
      {
        pattern: /^mindscape_tool_\w+_(preview|status|info|metadata)/,
        level: "primitive",
        reason: "Informational operations are safe"
      },

      // ============================================
      // Playbooks default to governed (orchestration)
      // ============================================
      {
        pattern: /^mindscape_playbook_/,
        level: "governed",
        reason: "Playbooks are orchestration workflows"
      },

      // ============================================
      // Default rule (fallback)
      // ============================================
      {
        pattern: /.*/,
        level: "governed",
        reason: "Unknown tools default to governed for safety"
      }
    ];
  }

  /**
   * Determine tool access level
   */
  getAccessLevel(mcpToolName: string): AccessDecision {
    for (const rule of this.rules) {
      const matches = typeof rule.pattern === "string"
        ? mcpToolName === rule.pattern
        : rule.pattern.test(mcpToolName);

      if (matches) {
        return {
          allowed: rule.level !== "internal",
          level: rule.level,
          reason: rule.reason || "Matched policy rule",
          constraints: {
            requiresConfirmation: rule.requiresConfirmation,
            requiresPreview: rule.requiresPreview,
            maxCallsPerMinute: rule.maxCallsPerMinute
          }
        };
      }
    }

    return {
      allowed: false,
      level: "internal",
      reason: "No matching rule (this should not happen)"
    };
  }

  /**
   * Filter tools/list results, remove internal tools
   */
  filterToolsForExternalAccess(tools: any[]): any[] {
    return tools.filter(tool => {
      const decision = this.getAccessLevel(tool.name);
      return decision.allowed;
    });
  }

  /**
   * Check if tool can execute as primitive
   */
  canExecuteAsPrimitive(mcpToolName: string): boolean {
    const decision = this.getAccessLevel(mcpToolName);
    return decision.allowed && decision.level === "primitive";
  }

  /**
   * Get tool constraints
   */
  getConstraints(mcpToolName: string): AccessDecision["constraints"] {
    return this.getAccessLevel(mcpToolName).constraints;
  }

  /**
   * Add custom rule (inserted at front, highest priority)
   */
  addRule(rule: ToolAccessRule): void {
    this.rules.unshift(rule);
  }

  /**
   * Load rules from config
   */
  loadRulesFromConfig(configRules: ToolAccessRule[]): void {
    this.rules = [...configRules, ...this.rules];
  }
}

export const toolAccessPolicy = new ToolAccessPolicy();
