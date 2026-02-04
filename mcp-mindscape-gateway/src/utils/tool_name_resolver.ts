/**
 * ToolNameResolver - Tool naming resolver
 *
 * Resolves tool naming pack duplication issues.
 * Backend tools may come in various formats, Gateway unifies them.
 */
export interface ToolIdentity {
  pack: string;      // e.g., "wordpress"
  action: string;    // e.g., "get_page_content"
  canonical: string; // e.g., "wordpress.get_page_content"
}

export interface RawTool {
  name: string;
  pack?: string;
  code?: string;
  full_name?: string;
  provider?: string;
  [key: string]: any;
}

export class ToolNameResolver {
  private knownPacks: Set<string> = new Set([
    "wordpress", "creative", "seo", "analytics", "system", "default"
  ]);

  constructor(packs?: string[]) {
    if (packs) {
      this.knownPacks = new Set(packs);
    }
  }

  /**
   * Resolve canonical identity from backend tool
   */
  resolve(tool: RawTool): ToolIdentity {
    // Priority 1: If full_name exists, use it directly
    if (tool.full_name) {
      return this.parseFullName(tool.full_name);
    }

    // Priority 2: If name already contains pack prefix
    const parsedFromName = this.tryParsePackFromName(tool.name);
    if (parsedFromName) {
      if (tool.pack && tool.pack !== parsedFromName.pack) {
        console.warn(
          `Tool naming conflict: name="${tool.name}" implies pack="${parsedFromName.pack}", ` +
          `but explicit pack="${tool.pack}". Using pack from name.`
        );
      }
      return parsedFromName;
    }

    // Priority 3: Use explicit pack + name
    if (tool.pack) {
      return {
        pack: tool.pack,
        action: tool.name,
        canonical: `${tool.pack}.${tool.name}`
      };
    }

    // Priority 4: Use code if exists
    if (tool.code) {
      const parsedFromCode = this.tryParsePackFromName(tool.code);
      if (parsedFromCode) {
        return parsedFromCode;
      }
    }

    // Fallback: Use default pack
    return {
      pack: "default",
      action: tool.name,
      canonical: `default.${tool.name}`
    };
  }

  /**
   * Try to parse pack from name (if name starts with known pack)
   */
  private tryParsePackFromName(name: string): ToolIdentity | null {
    for (const pack of this.knownPacks) {
      if (name.startsWith(`${pack}.`)) {
        const action = name.substring(pack.length + 1);
        return {
          pack,
          action,
          canonical: name
        };
      }
    }
    return null;
  }

  /**
   * Parse full name (e.g., "wordpress.get_page_content")
   */
  private parseFullName(fullName: string): ToolIdentity {
    const dotIndex = fullName.indexOf(".");
    if (dotIndex === -1) {
      return {
        pack: "default",
        action: fullName,
        canonical: `default.${fullName}`
      };
    }
    const pack = fullName.substring(0, dotIndex);
    const action = fullName.substring(dotIndex + 1);
    return { pack, action, canonical: fullName };
  }

  /**
   * Generate MCP tool name (with layer prefix).
   * Note: MCP tool names only allow [a-zA-Z0-9_-], no dots.
   */
  toMcpName(identity: ToolIdentity, layer: "tool" | "playbook" | "run"): string {
    const safeName = identity.canonical.replace(/\./g, "_");
    return `mindscape_${layer}_${safeName}`;
  }

  /**
   * Parse back from MCP tool name to identity
   */
  fromMcpName(mcpName: string): { layer: string; identity: ToolIdentity } | null {
    const match = mcpName.match(/^mindscape_(tool|playbook|run|lens)_(.+)$/);
    if (!match) return null;

    const [, layer, rest] = match;
    const firstUnderscoreIndex = rest.indexOf("_");
    let canonical: string;
    if (firstUnderscoreIndex !== -1) {
      const pack = rest.substring(0, firstUnderscoreIndex);
      const action = rest.substring(firstUnderscoreIndex + 1);
      canonical = `${pack}.${action}`;
    } else {
      canonical = rest;
    }
    const identity = this.parseFullName(canonical);
    return { layer, identity };
  }

  /**
   * Update known pack list
   */
  updateKnownPacks(packs: string[]): void {
    this.knownPacks = new Set(packs);
  }
}
