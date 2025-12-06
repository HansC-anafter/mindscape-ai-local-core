/**
 * PlaybookRegistry - Frontend registry for playbook UI components and layouts
 *
 * This registry manages playbook UI components and layout configurations
 * that are loaded from independent playbook repositories.
 *
 * Backend PlaybookRegistry (Python) handles playbook.json/playbook.md definitions.
 * This Frontend PlaybookRegistry (TypeScript) handles UI components and layouts.
 */

import { React.ComponentType } from 'react';

export interface UILayoutConfig {
  type: 'book_writing' | 'course_writing' | 'proposal_drafting' | 'default';
  left_sidebar?: {
    type: string;
    component: string;
    config: Record<string, any>;
  };
  main_surface: {
    layout: 'three_column' | 'two_column' | 'single_column';
    components: Array<{
      type: string;
      position: string;
      config: Record<string, any>;
    }>;
  };
}

export interface PlaybookSpec {
  version: string;
  playbook_code: string;
  kind: string;
  [key: string]: any;
}

export interface PlaybookPackage {
  playbookCode: string;
  version: string;
  playbookSpec?: PlaybookSpec;
  uiLayout?: UILayoutConfig;
  components?: {
    [componentName: string]: React.ComponentType<any>;
  };
}

/**
 * PlaybookRegistry - Registry for playbook UI components
 */
export class PlaybookRegistry {
  private playbooks: Map<string, PlaybookPackage> = new Map();

  /**
   * Register a playbook package
   */
  register(playbook: PlaybookPackage): void {
    if (this.playbooks.has(playbook.playbookCode)) {
      console.warn(
        `Playbook ${playbook.playbookCode} is already registered. Overwriting...`
      );
    }
    this.playbooks.set(playbook.playbookCode, playbook);
  }

  /**
   * Get a playbook package by code
   */
  get(playbookCode: string): PlaybookPackage | undefined {
    return this.playbooks.get(playbookCode);
  }

  /**
   * List all registered playbooks
   */
  list(): PlaybookPackage[] {
    return Array.from(this.playbooks.values());
  }

  /**
   * Get UI layout config for a playbook
   */
  getUILayout(playbookCode: string): UILayoutConfig | undefined {
    const playbook = this.get(playbookCode);
    return playbook?.uiLayout;
  }

  /**
   * Get a component by playbook code and component name
   */
  getComponent(
    playbookCode: string,
    componentName: string
  ): React.ComponentType<any> | undefined {
    const playbook = this.get(playbookCode);
    return playbook?.components?.[componentName];
  }

  /**
   * Check if a playbook is registered
   */
  has(playbookCode: string): boolean {
    return this.playbooks.has(playbookCode);
  }

  /**
   * Unregister a playbook
   */
  unregister(playbookCode: string): boolean {
    return this.playbooks.delete(playbookCode);
  }
}

