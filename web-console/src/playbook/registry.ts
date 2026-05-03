import type { ComponentType } from 'react';

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
    [componentName: string]: ComponentType<any>;
  };
}

export class PlaybookRegistry {
  private playbooks: Map<string, PlaybookPackage> = new Map();

  register(playbook: PlaybookPackage): void {
    this.playbooks.set(playbook.playbookCode, playbook);
  }

  registerComponent(
    playbookCode: string,
    componentName: string,
    component: ComponentType<any>
  ): void {
    let playbook = this.playbooks.get(playbookCode);
    if (!playbook) {
      playbook = {
        playbookCode,
        version: '0.0.0',
        components: {},
      };
      this.playbooks.set(playbookCode, playbook);
    }

    if (!playbook.components) {
      playbook.components = {};
    }

    playbook.components[componentName] = component;
  }

  get(playbookCode: string): PlaybookPackage | undefined {
    return this.playbooks.get(playbookCode);
  }

  list(): PlaybookPackage[] {
    return Array.from(this.playbooks.values());
  }

  getUILayout(playbookCode: string): UILayoutConfig | undefined {
    const playbook = this.get(playbookCode);
    return playbook?.uiLayout;
  }

  getComponent(
    playbookCode: string,
    componentName: string
  ): ComponentType<any> | undefined {
    const playbook = this.get(playbookCode);
    return playbook?.components?.[componentName];
  }

  has(playbookCode: string): boolean {
    return this.playbooks.has(playbookCode);
  }

  unregister(playbookCode: string): boolean {
    return this.playbooks.delete(playbookCode);
  }
}
