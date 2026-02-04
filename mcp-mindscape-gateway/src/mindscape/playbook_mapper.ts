/**
 * Playbook to MCP Tool Mapper
 */
import { MindscapeClient, Playbook } from "./client.js";
import { ToolNameResolver, ToolIdentity } from "../utils/tool_name_resolver.js";
import { wrapToolSchema } from "../utils/schema.js";

export interface McpTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, any>;
    required?: string[];
  };
  _mindscape?: {
    layer: string;
    pack: string;
    [key: string]: any;
  };
}

export class PlaybookMapper {
  constructor(
    private client: MindscapeClient,
    private nameResolver: ToolNameResolver
  ) { }

  /**
   * Convert Playbook to MCP Tool.
   *
   * Final format: mindscape.playbook.<pack>.<code>
   * - pack from playbook.pack or playbook.capability
   * - code from playbook.playbook_code
   */
  toMcpTool(playbook: Playbook): McpTool {
    const identity = this._resolveIdentity(playbook);
    const mcpName = this.nameResolver.toMcpName(identity, "playbook");

    return {
      name: mcpName,
      description: this._buildDescription(playbook, identity),
      inputSchema: wrapToolSchema((playbook.input_schema || {}) as Record<string, any>, {
        includeWorkspaceId: true,
        includeConfirmToken: false
      }) as any,
      _mindscape: {
        layer: "macro",
        pack: identity.pack,
        action: identity.action,
        canonical: identity.canonical,
        playbook_code: playbook.playbook_code,
        capability: playbook.capability
      }
    };
  }

  /**
   * Resolve Playbook canonical identity
   */
  private _resolveIdentity(playbook: Playbook): ToolIdentity {
    const rawTool = {
      name: playbook.playbook_code,
      pack: playbook.pack || playbook.capability,
      full_name: playbook.pack
        ? `${playbook.pack}.${this._stripPackPrefix(playbook.playbook_code, playbook.pack)}`
        : undefined
    };

    return this.nameResolver.resolve(rawTool);
  }

  /**
   * Strip existing pack prefix to avoid duplication
   */
  private _stripPackPrefix(code: string, pack: string): string {
    if (code.startsWith(`${pack}.`)) {
      return code.substring(pack.length + 1);
    }
    return code;
  }

  private _buildDescription(playbook: Playbook, identity: ToolIdentity): string {
    return `[Macro Tool] ${playbook.display_name || playbook.playbook_code}\n\n` +
      `${playbook.description || "No description"}\n\n` +
      `Pack: ${identity.pack}\n` +
      `Capability: ${playbook.capability}\n` +
      `Canonical: ${identity.canonical}\n\n` +
      `This tool runs a complete Playbook workflow with full orchestration, trace, and governance.`;
  }
}
